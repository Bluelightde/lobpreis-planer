"""X32-Szene (.scn) an die Besetzung anpassen und SVG-Vorschau rendern."""

import math
import os
import re
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from lp_konfig import VORLAGEN_DIR
from lp_personen import anzeige_name


# ---------------------------------------------------------------------------
# X32-Szene (.scn)
# ---------------------------------------------------------------------------

class SceneFehler(Exception):
    """Fehler beim Patchen der SCN-Vorlage (z.B. erwartete Zeile nicht gefunden)."""
    pass


def _scn_patch(text: str, pat: re.Pattern[str], ersatz: str,
               beschreibung: str, ch: int) -> tuple[str, int]:
    """Führt pat.sub aus und zählt die Treffer. Wirft SceneFehler wenn
       kein einziger Treffer (die Vorlagen-Zeile fehlt oder das Format hat
       sich geändert)."""
    funde: list[re.Match[str]] = list(pat.finditer(text))
    if not funde:
        raise SceneFehler(
            f"Kein Treffer für {beschreibung} Kanal/Bus {ch}: "
            f"Pattern passt nicht auf die SCN-Vorlage – Format hat sich "
            f"möglicherweise geändert.")
    return pat.sub(ersatz, text), len(funde)

def _scn_set_name(text: str, ch: int, name: str) -> tuple[str, int]:
    """Setzt den (ersten) Namen in der Zeile /ch/NN/config "..." ... ."""
    pat: re.Pattern[str] = re.compile(r'^(/ch/%02d/config )"[^"]*"' % ch, re.M)
    sauber: str = (name or "").replace('"', "")
    return _scn_patch(text, pat, r'\1"' + sauber + '"', "Kanal-Name setzen", ch)


def _scn_set_source(text: str, ch: int, src: int) -> tuple[str, int]:
    """Setzt das letzte Feld (Source) in /ch/NN/config "Name" Icon Color SOURCE."""
    pat: re.Pattern[str] = re.compile(
        r'^(/ch/%02d/config "[^"]*" \S+ \S+) \S+' % ch, re.M)
    return _scn_patch(text, pat, r'\1 ' + str(int(src)), "Kanal-Source setzen", ch)


def _scn_set_bus_name(text: str, bus: int, name: str) -> tuple[str, int]:
    pat: re.Pattern[str] = re.compile(r'^(/bus/%02d/config )"[^"]*"' % bus, re.M)
    sauber: str = (name or "").replace('"', "")
    return _scn_patch(text, pat, r'\1"' + sauber + '"', "Bus-Name setzen", bus)

def scene_anwenden(
    text: str,
    cfg: dict[str, Any],
    voc_names: dict[int, str] | None = None,
    quellen: dict[int, int] | None = None,
    busse: list[dict[str, Any]] | None = None,
    spitznamen: dict[str, str] | None = None
) -> tuple[str, dict[str, Any]]:
    """Wendet alle Scene-Patches (Kanal-Namen, Sources, Bus-Namen) auf
       einen bereits geladenen Vorlage-Text an. Reine Patch-Funktion --
       laedt die Vorlage NICHT selbst, damit sie sowohl fuer die
       Erstgenerierung (erzeuge_scene) als auch fuer den Regenerate-Pfad
       (lobpreis_planer.regeneriere_excel_und_scene) nutzbar ist.

       Args:
         text:          kompletter .scn-Vorlagetext (von erzeuge_scene geladen
                        oder vom Regenerate-Client als 'basis' mitgeschickt).
         cfg:           Konfig (fuer voc_kanaele, kanal_zu_excelzeile, etc.).
         voc_names:     {voc_index: rohname} -- falls None, bleibt alles leer.
         quellen:       {excel_zeile: a_nummer} -- None = keine Patches.
         busse:         Liste von {bus, name} -- None = keine Patches.
         spitznamen:    Optional, fuer anzeige_name().

       Gibt (text, bericht) zurueck. Wirft SceneFehler bei Patch-Fehlern.
    """
    scfg: dict[str, Any] = cfg.get("scene") or {}
    fmt: str = cfg.get("excel", {}).get("namensformat", "vorname")
    voc_names = voc_names or {}
    quellen = quellen or {}
    busse = busse or []
    bericht: dict[str, Any] = {"voc": [], "quellen": [], "busse": [], "engpass": []}

    # 1) Gesangskanaele beschriften
    for i, ch in enumerate(scfg.get("voc_kanaele", [])):
        roh: str | None = voc_names.get(i + 1)
        nm: str = anzeige_name(roh, spitznamen, fmt) if roh else ""
        text, _ = _scn_set_name(text, ch, nm)
        bericht["voc"].append({"kanal": ch, "voc": i + 1, "name": nm or None})

    # 2) Kanal-Source aus den berechneten Excel-D-Werten (A-Nummern)
    for ch_str, zeile in scfg.get("kanal_zu_excelzeile", {}).items():
        src: int | None = quellen.get(zeile) if quellen.get(zeile) is not None \
            else quellen.get(str(zeile))
        if src is None:
            # kein Eingang (abwesend / 'aus') -> Kanal-Source auf 0 (aus)
            text, _ = _scn_set_source(text, int(ch_str), 0)
            continue
        text, _ = _scn_set_source(text, int(ch_str), src)
        bericht["quellen"].append({"kanal": int(ch_str), "source": int(src)})
        if int(src) > 32:  # SB2 hat nur 16 Eingaenge (A17-A32) -> Engpass
            bericht["engpass"].append({"kanal": int(ch_str), "source": int(src)})

    # 3) Bus-Namen aus den Monitoren (Spalte J/K)
    for b in busse:
        text, _ = _scn_set_bus_name(text, int(b["bus"]), b["name"])
        bericht["busse"].append({"bus": int(b["bus"]), "name": b["name"]})

    return text, bericht


def erzeuge_scene(
    eintraege: list[dict[str, Any]],
    cfg: dict[str, Any],
    spitznamen: dict[str, str] | None = None,
    excel_bericht: dict[str, Any] | None = None
) -> tuple[str | None, dict[str, Any]]:
    """Passt die X32-Szene an:
       - Gesangskanaele (Vox1-4) -> Saengernamen,
       - Kanal-Source aus Excel-Spalte D (A-Nummer, via excel_bericht['quellen']),
       - Bus-Namen aus den Monitoren (excel_bericht['busse']).
       Rueckgabe: (text, bericht) oder (None, {}), wenn keine Vorlage da ist.

       Intern: laedt die .scn-Vorlage und delegiert das Patchen an
       scene_anwenden -- dadurch kann dieselbe Patch-Logik im
       Regenerate-Pfad wiederverwendet werden, ohne die Vorlage nochmal
       zu laden (der Client schickt den Basis-Text mit)."""
    scfg: dict[str, Any] | None = cfg.get("scene")
    if not scfg:
        return None, {}
    pfad: str = os.path.join(VORLAGEN_DIR, scfg.get("vorlage", ""))
    if not os.path.isfile(pfad):
        return None, {}
    with open(pfad, encoding="utf-8", errors="replace") as f:
        text: str = f.read()

    eb: dict[str, Any] = excel_bericht or {}

    # Gesangs-Namen in der Reihenfolge des Excel-Berichts (folgt der Skizze,
    # links -> rechts). 'roh' ist der unformatierte Name; scene_anwenden
    # wendet anzeige_name darauf an. Einzige Quelle der Voc-Reihenfolge.
    voc_names: dict[int, str] = {
        v["voc"]: v["roh"] for v in eb.get("voc", [])
        if v.get("roh")
    }

    quellen: dict[int, int] = eb.get("quellen", {})
    busse: list[dict[str, Any]] = eb.get("busse", [])
    text, bericht = scene_anwenden(text, cfg, voc_names, quellen, busse, spitznamen)
    return text, bericht


# ---------------------------------------------------------------------------
# SVG-Vorschau
# ---------------------------------------------------------------------------

def _rot(
    cx: float, cy: float, x: float, y: float, winkel: float
) -> tuple[float, float]:
    s: float = math.sin(winkel)
    c: float = math.cos(winkel)
    dx: float = x - cx
    dy: float = y - cy
    return cx + dx * c - dy * s, cy + dx * s + dy * c


def render_svg(doc: dict[str, Any], keys: dict[str, str] | None = None,
               stacks: dict[str, tuple[str, int]] | None = None) -> str:
    """Erzeugt eine schlichte SVG-Vorschau der Buehnenskizze aus den Elementen.
       keys: dict rect-id -> Box-Schluessel (fuer Drag&Drop im UI).
       stacks: dict rect-id -> (Stapel-Gruppe, Ebenen-Index) fuer den z-Stapel."""
    keys = keys or {}
    stacks = stacks or {}
    els: list[dict[str, Any]] = [e for e in doc.get("elements", []) if not e.get("isDeleted")]

    # Begrenzungen ermitteln
    xs: list[float] = []
    ys: list[float] = []
    for e in els:
        x: float = e.get("x", 0)
        y: float = e.get("y", 0)
        w: float = e.get("width", 0)
        h: float = e.get("height", 0)
        xs += [x, x + w]
        ys += [y, y + h]
    if not xs:
        return "<svg xmlns='http://www.w3.org/2000/svg'></svg>"
    minx: float = min(xs)
    maxx: float = max(xs)
    miny: float = min(ys)
    maxy: float = max(ys)
    pad: int = 30
    vb_w: float = (maxx - minx) + 2 * pad
    vb_h: float = (maxy - miny) + 2 * pad

    out: list[str] = [
        f"<svg xmlns='http://www.w3.org/2000/svg' "
        f"viewBox='{minx-pad:.0f} {miny-pad:.0f} {vb_w:.0f} {vb_h:.0f}' "
        f"font-family='Segoe UI, Arial, sans-serif'>",
        f"<rect class='svg-bg' x='{minx-pad:.0f}' y='{miny-pad:.0f}' "
        f"width='{vb_w:.0f}' height='{vb_h:.0f}' fill='#ffffff'/>",
    ]

    def stroke(e: dict[str, Any]) -> str:
        return e.get("strokeColor") or "#1e1e1e"

    def fuellung(e: dict[str, Any], ersatz: str) -> str:
        bg: str | None = e.get("backgroundColor")
        if not bg or bg == "transparent":
            return ersatz
        return bg

    for e in els:
        t: str | None = e.get("type")
        x: float = e.get("x", 0)
        y: float = e.get("y", 0)
        w: float = e.get("width", 0)
        h: float = e.get("height", 0)
        ang: float = e.get("angle", 0) or 0
        cx: float = x + w / 2
        cy: float = y + h / 2
        transform: str = (
            f" transform='rotate({math.degrees(ang):.2f} {cx:.1f} {cy:.1f})'" if ang else ""
        )
        key: str | None = keys.get(e.get("id")) or keys.get(e.get("containerId"))
        dkey: str = f" data-key='{xml_escape(str(key))}'" if key else ""
        st: tuple[str, int] | None = stacks.get(e.get("id")) or stacks.get(e.get("containerId"))
        dstack: str = f" data-stack='{xml_escape(st[0])}' data-layer='{st[1]}'" if st else ""
        if t == "rectangle":
            ist_rahmen: bool = w > 800 or h > 400
            fill: str = "none" if ist_rahmen else fuellung(e, "#f3f6fb")
            cls: str = "svg-frame" if ist_rahmen else "svg-box"
            if key:
                cls += " ziehbar"
            out.append(
                f"<rect class='{cls}' x='{x:.1f}' y='{y:.1f}' width='{w:.1f}' height='{h:.1f}' "
                f"rx='8' fill='{fill}' stroke='{stroke(e)}' stroke-width='1.5'{transform}{dkey}{dstack}/>"
            )
        elif t == "ellipse":
            out.append(
                f"<ellipse class='svg-kreis' cx='{cx:.1f}' cy='{cy:.1f}' "
                f"rx='{w/2:.1f}' ry='{h/2:.1f}' "
                f"fill='{fuellung(e, '#eef3ff')}' stroke='{stroke(e)}' "
                f"stroke-width='1.5'{transform}/>"
            )
        elif t == "line":
            pts: list[list[float]] = e.get("points") or []
            if len(pts) >= 2:
                d: str = " ".join(f"{x+px:.1f},{y+py:.1f}" for px, py in pts)
                out.append(
                    f"<polyline class='svg-linie{' ziehbar' if key else ''}' points='{d}' fill='none' "
                    f"stroke='{stroke(e)}' stroke-width='1.2'{transform}{dkey}/>"
                )
        elif t == "text":
            txt: str = e.get("text", "")
            fs: int = e.get("fontSize", 16)
            zeilen: list[str] = txt.split("\n")
            gesamt_h: float = len(zeilen) * fs * 1.25
            start_y: float = cy - gesamt_h / 2 + fs
            for i, zeile in enumerate(zeilen):
                ty: float = start_y + i * fs * 1.25
                gewicht: str = "600" if i == 0 else "400"
                farbe: str = "#1e1e1e" if i == 0 else "#555"
                cls = "svg-haupt" if i == 0 else "svg-rolle"
                if key:
                    cls += " ziehbar"
                out.append(
                    f"<text class='{cls}' x='{cx:.1f}' y='{ty:.1f}' "
                    f"font-size='{fs}' font-weight='{gewicht}' "
                    f"fill='{farbe}' text-anchor='middle'{transform}{dkey}{dstack}>"
                    f"{xml_escape(zeile)}</text>"
                )
    out.append("</svg>")
    return "".join(out)
