"""Excel-Belegungsplan: X32-Template klonen und per ElementTree Zellen setzen.

Auto-Balance: Jede Stagebox hat 16 Eingänge. Gruppen, die der Bühnenmitte am
nächsten stehen, werden bei Überlauf auf die andere Box verschoben.
Drums/Bass (immer: true) bleiben fix.

Regeneration: `setzwerte_zu_xlsx_bytes` ist die Render-Hälfte, die nach
UI-Edits erneut aufgerufen werden kann, ohne `berechne_excel_werte` zu
wiederholen. Siehe `lobpreis_planer.regeneriere_excel_und_scene`.
"""

import io
import os
import re
import zipfile
from typing import Any
from xml.etree import ElementTree as ET

from lp_konfig import M, VORLAGE_EXCEL
from lp_personen import anzeige_name


def _spalte_zu_nr(col: str) -> int:
    n: int = 0
    for c in col:
        n = n * 26 + (ord(c) - ord("A") + 1)
    return n


def _zell_sortkey(ref: str) -> tuple[int, int]:
    m: re.Match[str] | None = re.match(r"([A-Z]+)(\d+)", ref)
    assert m is not None
    return (int(m.group(2)), _spalte_zu_nr(m.group(1)))


def _sheet_datei_fuer_blatt(z: zipfile.ZipFile, blattname: str) -> str | None:
    """Findet die worksheet-XML-Datei zu einem Blattnamen ueber workbook + rels."""
    ns_r: str = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    wb: ET.Element = ET.fromstring(z.read("xl/workbook.xml"))
    rid: str | None = None
    for s in wb.iter(f"{{{M}}}sheet"):
        if s.get("name") == blattname:
            rid = s.get(f"{{{ns_r}}}id")
            break
    if rid is None:
        return None
    rels: ET.Element = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    ns_pkg: str = "http://schemas.openxmlformats.org/package/2006/relationships"
    for rel in rels.iter(f"{{{ns_pkg}}}Relationship"):
        if rel.get("Id") == rid:
            target: str | None = rel.get("Target")
            assert target is not None
            return "xl/" + target.replace("../", "").lstrip("/") \
                if not target.startswith("xl/") else target
    return None


def _fuelle_zelle(c: ET.Element, wert: Any) -> None:
    """Setzt den Inhalt einer <c>-Zelle: '' = leeren, int/float = Zahl, sonst Inline-String.
       Das Style-Attribut (s) bleibt erhalten."""
    M_is: str = f"{{{M}}}is"
    M_t: str = f"{{{M}}}t"
    M_v: str = f"{{{M}}}v"
    for kind in list(c):
        c.remove(kind)
    c.attrib.pop("t", None)
    if wert == "" or wert is None:
        return
    if isinstance(wert, (int, float)):
        # Ganzzahlige Werte ohne ".0" schreiben (5.0 -> "5"), echte Kommazahlen
        # unveraendert lassen (3.5 -> "3.5").
        zahl: float = float(wert)
        v: ET.Element = ET.SubElement(c, M_v)
        v.text = str(int(zahl) if zahl.is_integer() else wert)
    else:
        c.set("t", "inlineStr")
        ET.SubElement(ET.SubElement(c, M_is), M_t).text = str(wert)


def _set_zelle_inline(root: ET.Element, ref: str, wert: Any) -> bool:
    """Setzt Zelle <c r=ref> (Zahl, Inline-String oder leer). Legt sie sortiert an,
       falls sie fehlt. Gibt True zurueck, wenn die Zeile existiert(e)."""
    M_c: str = f"{{{M}}}c"
    M_row: str = f"{{{M}}}row"
    zeilen_nr: str = re.match(r"[A-Z]+(\d+)", ref).group(1)  # type: ignore[union-attr]
    for row in root.iter(M_row):
        if row.get("r") != zeilen_nr:
            continue
        for c in row.findall(M_c):
            if c.get("r") == ref:
                _fuelle_zelle(c, wert)
                return True
        # Zelle fehlt -> neu (sortiert) anlegen
        neu: ET.Element = ET.Element(M_c, {"r": ref})
        _fuelle_zelle(neu, wert)
        for c in row.findall(M_c):
            if _zell_sortkey(c.get("r", "")) > _zell_sortkey(ref):
                row.insert(list(row).index(c), neu)
                break
        else:
            row.append(neu)
        return True
    return False


def berechne_excel_werte(
    eintraege: list[dict[str, Any]],
    personen: list[dict[str, Any]],
    layout: dict[str, Any],
    cfg: dict[str, Any],
    spitznamen: dict[str, str] | None = None,
    solo_personen: dict[str, str] | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Leitet aus der Skizze (layout) die Excel-Zellwerte ab.
       Rueckgabe: (setzwerte, bericht).
       - SB1/SB2-Nummern: jedes vorhandene Instrument je nach X-Position links
         (SB1) oder rechts (SB2) der Buehnenmitte; pro Stagebox in Zeilenreihen-
         folge neu durchnummeriert. Fehlende Instrumente -> geleert.
       - Saenger (Gesang 1..4) -> Vorname in Spalte C (Voc) und Monitor J;
         Seite nach X-Position.
    """
    ecfg: dict[str, Any] = cfg["excel"]
    namensformat: str = ecfg.get("namensformat", "vorname")
    SB1: str = ecfg["sb_spalten"]["SB1"]
    SB2: str = ecfg["sb_spalten"]["SB2"]
    bez: str = ecfg["bezeichnung_spalte"]
    mitte: float = layout["mitte_x"]
    cx_von: dict[str, float | None] = {e["person"]["name"]: e["cx"] for e in layout["plan"]}

    def vn(name: str | None) -> str:
        return anzeige_name(name, spitznamen, namensformat)

    def seite(cx: float | None) -> str | None:
        # Toleranz 1px: exakt mittig stehende Person -> SB1 ("Mitte zur SB1").
        if cx is None:
            return None
        return "SB1" if cx <= mitte + 1.0 else "SB2"

    setz: dict[str, Any] = {}
    zeilen: dict[int, dict[str, Any]] = {}  # zeile -> {"seite", "present"}
    bericht: dict[str, Any] = {"voc": [], "instrumente": [], "ueberzaehlige_saenger": []}

    # --- Saenger: Reihenfolge wie in der Skizze (links -> rechts nach X-Position) ---
    voc_namen: list[str] = []
    for e in eintraege:
        if e["rolle"] == ecfg["voc"]["gesang_rolle"] and e["name"] and e["name"] != "?":
            if e["name"] not in voc_namen:
                voc_namen.append(e["name"])
    # Sortiere nach cx (Skizzen-X, links zuerst); Saenger ohne Skizzen-Position
    # (cx None) ans Ende. .sort() ist stabil -> Gleichstand behaelt Parse-Reihenfolge.
    voc_namen.sort(key=lambda n: (0, cx_von[n]) if cx_von.get(n) is not None else (1, 0.0))
    namen: list[str] = voc_namen
    if len(namen) > len(ecfg["voc"]["zeilen"]):
        bericht["ueberzaehlige_saenger"] = [
            {"nr": i + len(ecfg["voc"]["zeilen"]) + 1, "name": n}
            for i, n in enumerate(namen[len(ecfg["voc"]["zeilen"]):])]
    for i, zeile in enumerate(ecfg["voc"]["zeilen"]):
        name: str | None = namen[i] if i < len(namen) else None
        cx: float | None = cx_von.get(name) if name else None
        s: str | None = seite(cx) if name else None
        zeilen[zeile] = {"seite": s, "present": name is not None, "cx": cx,
                         "label": f"Voc{i+1}", "person": name}
        setz[f"{bez}{zeile}"] = vn(name)
        bericht["voc"].append({"voc": i + 1, "name": vn(name) or None,
                               "seite": s, "roh": name})

    # --- Instrumente ---
    solo_info: dict[str, Any] = cfg.get("solo_instrument", {})
    solo_rolle: str = solo_info.get("rolle", "Solo")
    solo_standard: str = solo_info.get("standard", "Geige")
    sp: dict[str, str] = solo_personen or {}
    for grp in ecfg["instrumente"]:
        si: str | None = grp.get("solo_instrument")

        def passt(p: dict[str, Any], grp: dict[str, Any] = grp,
                  si: str | None = si) -> bool:
            if any(r in p["rollen"] for r in grp["rollen"]):
                return True
            # 'Solo' zaehlt zu dem (person-spezifischen) Solo-Instrument
            if si and solo_rolle in p["rollen"]:
                return sp.get(p["name"], solo_standard) == si
            return False

        person: dict[str, Any] | None = next((p for p in personen if passt(p)), None)
        cx: float | None = cx_von.get(person["name"]) if person else None
        s: str | None = seite(cx) if person else None
        for zeile in grp["zeilen"]:
            zeilen[zeile] = {"seite": s, "present": person is not None,
                             "cx": cx, "label": grp["rollen"][0],
                             "person": person["name"] if person else None}
        bericht["instrumente"].append({
            "rolle": "/".join(grp["rollen"]),
            "person": vn(person["name"]) if person else None,
            "seite": s,
        })

    # --- Technik (immer vorhanden, feste Seite, nicht verschiebbar) ---
    for grp in ecfg.get("technik", []):
        for zeile in grp["zeilen"]:
            zeilen[zeile] = {"seite": grp["seite"], "present": True, "cx": None, "label": None}

    # --- Standardmaessig 'aus': kein Eingang/SB-Platz ---
    for zeile in ecfg.get("aus_zeilen", []):
        zeilen[zeile] = {"seite": None, "present": False, "cx": None, "label": None, "person": None}

    # --- Optionale Track-Eingaenge (Track + Track Klick), per UI-Schalter track_aktiv ---
    #     Jede Track-Zeile kommt auf die Stagebox mit aktuell mehr freiem Platz
    #     (dynamisch). Mit track.dynamisch=false stattdessen fest auf track.seite.
    track: dict[str, Any] = ecfg.get("track") or {}
    track_zeilen: list[int] = track.get("zeilen", [])
    if not ecfg.get("track_aktiv"):
        for zeile in track_zeilen:
            zeilen[zeile] = {"seite": None, "present": False, "cx": None, "label": None, "person": None}
    elif track_zeilen:
        def _belegt(seite_name: str) -> int:
            return sum(1 for i in zeilen.values() if i["present"] and i["seite"] == seite_name)

        # Track + Track (Klick) bleiben ZUSAMMEN: gemeinsam auf die Box mit mehr Platz
        # (dynamisch). Mit track.dynamisch=false stattdessen fest auf track.seite.
        if track.get("dynamisch", True):
            tr_seite: str = "SB1" if _belegt("SB1") <= _belegt("SB2") else "SB2"
        else:
            tr_seite = track.get("seite", "SB2")
        for zeile in track_zeilen:
            zeilen[zeile] = {"seite": tr_seite, "present": True, "cx": None, "label": None}

    # --- Auto-Balance: nie mehr als 16 Eingaenge pro Stagebox ---
    #     verschiebbar = Kanaele mit Position; die der Buehnenmitte am naechsten
    #     stehen werden zuerst auf die andere (freie) Box verschoben.
    kap: int = ecfg.get("stagebox_kapazitaet", 16)
    verschoben: list[dict[str, Any]] = []
    # 'immer hinten'-Leute (Drums/Bass) bleiben fix an ihrer Box (auch ihr Gesang)
    immer_instr: set[str] = {
        n for n, b in cfg["buehne"]["backline"].items()
        if isinstance(b, dict) and b.get("immer")
    }
    fixe_personen: set[str] = {p["name"] for p in personen if set(p["rollen"]) & immer_instr}

    def _seite_rows(seite_name: str) -> list[int]:
        return [z for z, i in zeilen.items() if i["present"] and i["seite"] == seite_name]

    def _balance(von: str, nach: str) -> None:
        # verschiebt ganze Instrument-/Voc-Gruppen (haelt z.B. E-Git L+R zusammen),
        # die der Buehnenmitte am naechsten stehen, bis die Box <= kap hat.
        while len(_seite_rows(von)) > kap and len(_seite_rows(nach)) < kap:
            movable: list[int] = [z for z in _seite_rows(von)
                       if zeilen[z].get("cx") is not None
                       and zeilen[z].get("person") not in fixe_personen]
            if not movable:
                break
            gruppen: dict[tuple[str | None, str | None], list[int]] = {}
            for z in movable:
                gruppen.setdefault((zeilen[z]["person"], zeilen[z]["label"]), []).append(z)
            platz: int = kap - len(_seite_rows(nach))
            passend: list[tuple[tuple[str | None, str | None], list[int]]] = [
                (k, rs) for k, rs in gruppen.items() if len(rs) <= platz
            ]
            if passend:
                k, rs = min(passend, key=lambda kr: abs(zeilen[kr[1][0]]["cx"] - mitte))
            else:  # Notfall: einzelne Zeile (Gruppe passt nicht ganz)
                z: int = min(movable, key=lambda z: abs(zeilen[z]["cx"] - mitte))
                rs = [z]
            for z in rs:
                zeilen[z]["seite"] = nach
            verschoben.append({"label": zeilen[rs[0]]["label"], "von": von,
                               "nach": nach, "anzahl": len(rs)})

    _balance("SB2", "SB1")
    _balance("SB1", "SB2")
    bericht["balance"] = verschoben

    # --- Nummerierung pro Stagebox: Voc zuerst, dann Instrumente, keine Lücken ---
    quellen: dict[int, int] = {}
    voc_zeilen: set[int] = set(ecfg["voc"]["zeilen"])
    # Alle nicht-leeren Zeilen nach Seite sammeln
    for seite_name, spalte in [("SB1", SB1), ("SB2", SB2)]:
        eintraege_sb: list[int] = []
        for zeile in sorted(zeilen):
            info: dict[str, Any] = zeilen[zeile]
            if info["present"] and info["seite"] == seite_name:
                eintraege_sb.append(zeile)
        # Voc zuerst (innerhalb Voc: Zeilen-Reihenfolge 5,6,7,8,9),
 # Instrumente dahinter (Zeilen-Reihenfolge)
        eintraege_sb.sort(key=lambda r: (0 if r in voc_zeilen else 1, r))
        for i, zeile in enumerate(eintraege_sb, start=1):
            setz[f"{spalte}{zeile}"] = i
            andere = SB2 if spalte == SB1 else SB1
            setz[f"{andere}{zeile}"] = ""
            quellen[zeile] = i if seite_name == "SB1" else i + kap
    # Leere Zeilen bereinigen
    for zeile in sorted(zeilen):
        info: dict[str, Any] = zeilen[zeile]
        if not info["present"] or info["seite"] is None:
            setz[f"{SB1}{zeile}"] = ""
            setz[f"{SB2}{zeile}"] = ""
    bericht["quellen"] = quellen

    # --- Monitor-Outputs (Spalte J) nach Skizzen-Seite ---
    #     links -> J5-9, rechts -> J13-18; alle Personen, sortiert hinten->vorne.
    mon: dict[str, Any] = ecfg.get("monitor", {})
    links_z: list[str] = mon.get("links", [])
    rechts_z: list[str] = mon.get("rechts", [])
    # Monitor-Reihenfolge von VORNE nach HINTEN (groesseres y = vorne/Saalseite zuerst)
    links: list[dict[str, Any]] = sorted(
        [e for e in layout["plan"] if seite(e["cx"]) == "SB1"],
        key=lambda e: (-e["y"], e["x"])
    )
    rechts: list[dict[str, Any]] = sorted(
        [e for e in layout["plan"] if seite(e["cx"]) == "SB2"],
        key=lambda e: (-e["y"], e["x"])
    )
    links_bus: list[int] = mon.get("links_bus", [])
    rechts_bus: list[int] = mon.get("rechts_bus", [])
    bericht["monitor"] = {"links": [], "rechts": []}
    bericht["busse"] = []  # Bus-Nr -> Name fuer die Scene
    for zellen, leute, busse, seitenname in (
            (links_z, links, links_bus, "links"), (rechts_z, rechts, rechts_bus, "rechts")):
        for idx, zelle in enumerate(zellen):
            name: str = vn(leute[idx]["person"]["name"]) if idx < len(leute) else ""
            setz[zelle] = name
            if name:
                bericht["monitor"][seitenname].append({"zelle": zelle, "name": name})
                if idx < len(busse):
                    bericht["busse"].append({"bus": busse[idx], "name": name})
        if len(leute) > len(zellen):
            bericht.setdefault("monitor_ueberlauf", []).append(
                {"seite": seitenname, "anzahl": len(leute), "plaetze": len(zellen)})

    # --- alte Beispiel-Namen entfernen ---
    for cell in ecfg.get("alt_namen_leeren", []):
        setz[cell] = ""

    return setz, bericht


def _baue_sb_patchliste(
    setzwerte: dict[str, Any], cfg: dict[str, Any]
) -> None:
    """Schreibt die R/S/Y/Z-Patchliste (Stagebox-Belegung) in setzwerte.

       Liest die C/H-Texte aus der Vorlage (sharedStrings), weil
       berechne_excel_werte die C-Spalte fuer Instrument-Zeilen NICHT
       befuellt (nur Voc hat dort einen Eintrag). Die Patchliste braucht
       aber Label + Mic, um die Stagebox-Spalten R/S/Y/Z zu rendern.

       Fuer den Regenerate-Pfad ist das kein Problem: nach der ersten
       Generierung hat der Browser die stagebox1/2-Liste im Speicher;
       Edits am Label/Mic propagieren via setzwerte (siehe
       regeneriere_excel_und_scene in lobpreis_planer.py), und dieser
       Aufruf liest sie dann direkt.
    """
    ecfg: dict[str, Any] = cfg["excel"]
    SB1: str = ecfg["sb_spalten"]["SB1"]
    SB2: str = ecfg["sb_spalten"]["SB2"]
    blatt: str = ecfg["blatt"]

    quelle: zipfile.ZipFile = zipfile.ZipFile(VORLAGE_EXCEL)
    sheet_datei: str | None = _sheet_datei_fuer_blatt(quelle, blatt)
    if sheet_datei is None:
        quelle.close()
        return
    root: ET.Element = ET.fromstring(quelle.read(sheet_datei))
    ss_list: list[str] = [
        ''.join(t.text or '' for t in si.iter(f"{{{M}}}t"))
        for si in ET.fromstring(quelle.read("xl/sharedStrings.xml"))
    ]
    werte_root: dict[str, ET.Element] = {c.get("r", ""): c for c in root.iter(f"{{{M}}}c")}

    def _txt(ref: str) -> str:
        c: ET.Element | None = werte_root.get(ref)
        if c is None:
            return ""
        inl: ET.Element | None = c.find(f"{{{M}}}is")
        if inl is not None:
            return ''.join(x.text or '' for x in inl.iter(f"{{{M}}}t"))
        v: ET.Element | None = c.find(f"{{{M}}}v")
        if v is None:
            return ""
        return ss_list[int(v.text)] if c.get("t") == "s" else (v.text or "")

    sb1: dict[int, tuple[str, str]] = {}
    sb2: dict[int, tuple[str, str]] = {}
    for r in range(5, 39):
        fv: Any = setzwerte.get(f"{SB1}{r}")
        gv: Any = setzwerte.get(f"{SB2}{r}")
        label: Any = setzwerte.get(f"C{r}")
        if label is None:
            label = _txt(f"C{r}")
        mic: Any = setzwerte.get(f"H{r}")
        if mic is None:
            mic = _txt(f"H{r}")
        if isinstance(fv, int):
            sb1[fv] = (str(label), str(mic))
        elif isinstance(gv, int):
            sb2[gv] = (str(label), str(mic))
    for k in range(1, 17):
        setzwerte[f"R{4+k}"] = sb1.get(k, (" ", " "))[0] or " "
        setzwerte[f"S{4+k}"] = sb1.get(k, (" ", " "))[1] or " "
        setzwerte[f"Y{4+k}"] = sb2.get(k, (" ", " "))[0] or " "
        setzwerte[f"Z{4+k}"] = sb2.get(k, (" ", " "))[1] or " "
    quelle.close()

def _sb_liste(box: dict[int, tuple[str, str]], offset: int) -> list[dict[str, Any]]:
    eintraege: list[dict[str, Any]] = []
    for k in range(1, 17):
        label, mic = box.get(k, ("", ""))
        label = (label or "").strip()
        mic = (mic or "").strip()
        if not label and not mic:
            continue
        eintraege.append({"nr": k, "source": f"A{k + offset}",
                          "label": label, "mic": mic})
    return eintraege


def _rekonstruiere_sb_aus_setzwerte(
    setzwerte: dict[str, Any]
) -> tuple[dict[int, tuple[str, str]], dict[int, tuple[str, str]]]:
    """Rekonstruiert sb1/sb2-Dicts aus den R/S/Y/Z-Eintraegen in setzwerte."""
    sb1: dict[int, tuple[str, str]] = {}
    sb2: dict[int, tuple[str, str]] = {}
    for k in range(1, 17):
        r_val: str = setzwerte.get(f"R{4+k}", " ") or " "
        s_val: str = setzwerte.get(f"S{4+k}", " ") or " "
        y_val: str = setzwerte.get(f"Y{4+k}", " ") or " "
        z_val: str = setzwerte.get(f"Z{4+k}", " ") or " "
        if r_val.strip() and r_val.strip() != " ":
            sb1[k] = (r_val, s_val)
        if y_val.strip() and y_val.strip() != " ":
            sb2[k] = (y_val, z_val)
    return sb1, sb2


def _inputs_reihenfolge(
    setzwerte: dict[str, Any], cfg: dict[str, Any]
) -> list[dict[str, Any]]:
    """Baut die 'inputs'-Liste (Excel-Zeilenreihenfolge) aus setzwerte.

       Wie _baue_sb_patchliste liest auch diese Funktion die C/H-Texte
       aus der Vorlage (sharedStrings) -- berechne_excel_werte befuellt
       die C-Spalte nur fuer Voc, nicht fuer Instrumente. So sind die
       Label/Mic-Felder konsistent mit der SB-Patchliste und mit der
       Frontend-Darstellung.
    """
    ecfg: dict[str, Any] = cfg["excel"]
    SB1: str = ecfg["sb_spalten"]["SB1"]
    SB2: str = ecfg["sb_spalten"]["SB2"]
    blatt: str = ecfg["blatt"]

    quelle: zipfile.ZipFile = zipfile.ZipFile(VORLAGE_EXCEL)
    sheet_datei: str | None = _sheet_datei_fuer_blatt(quelle, blatt)
    ss_list: list[str] = []
    werte_root: dict[str, ET.Element] = {}
    if sheet_datei is not None:
        root: ET.Element = ET.fromstring(quelle.read(sheet_datei))
        ss_list = [
            ''.join(t.text or '' for t in si.iter(f"{{{M}}}t"))
            for si in ET.fromstring(quelle.read("xl/sharedStrings.xml"))
        ]
        werte_root = {c.get("r", ""): c for c in root.iter(f"{{{M}}}c")}

    def _txt(ref: str) -> str:
        c: ET.Element | None = werte_root.get(ref)
        if c is None:
            return ""
        inl: ET.Element | None = c.find(f"{{{M}}}is")
        if inl is not None:
            return ''.join(x.text or '' for x in inl.iter(f"{{{M}}}t"))
        v: ET.Element | None = c.find(f"{{{M}}}v")
        if v is None:
            return ""
        return ss_list[int(v.text)] if c.get("t") == "s" else (v.text or "")

    out: list[dict[str, Any]] = []
    for r in range(5, 39):
        fv: Any = setzwerte.get(f"{SB1}{r}")
        gv: Any = setzwerte.get(f"{SB2}{r}")
        label: Any = setzwerte.get(f"C{r}")
        if label is None:
            label = _txt(f"C{r}")
        mic: Any = setzwerte.get(f"H{r}")
        if mic is None:
            mic = _txt(f"H{r}")
        # Stabile Reihenfolge: alle 32 Excel-Zeilen ausgeben, belegt oder leer.
        # Frueher wurden leere Zeilen uebersprungen -- das hat im UI zu
 # springenden Indizes gefuehrt, sobald die Slot-Belegung sich aenderte.
        out.append({
            "zeile": r,            # Excel-Zeile (5..38) -- stabil
            "label": (str(label) if label is not None else "").strip(),
            "mic": (str(mic) if mic is not None else "").strip(),
            "sb1": fv if isinstance(fv, int) else None,
            "sb2": gv if isinstance(gv, int) else None,
        })
    quelle.close()
    return out


def setzwerte_zu_xlsx_bytes(
    setzwerte: dict[str, Any],
    blatt: str
) -> tuple[bytes, list[str]]:
    """Rendert ein setzwerte-Dict (zell-ref -> wert) in die Excel-Vorlage.

       Reine Render-Funktion: nimmt das bereits berechnete Dict (aus
       berechne_excel_werte oder eine danach editierte Kopie) und baut
       daraus die .xlsx-Bytes. Keine Layout-Logik -- die steckt in
       berechne_excel_werte.

       Zellen, die in der Vorlage nicht existieren, werden in `fehlend`
       gemeldet, aber nicht angelegt (das wuerde die Legende/Header
       zerstoeren).
    """
    ET.register_namespace("", M)
    for pfx, uri in {
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "mc": "http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac",
        "x14ac": "http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac",
        "xr": "http://schemas.microsoft.com/office/spreadsheetml/2014/revision",
        "xr2": "http://schemas.microsoft.com/office/spreadsheetml/2015/revision2",
        "xr3": "http://schemas.microsoft.com/office/spreadsheetml/2016/revision3",
    }.items():
        ET.register_namespace(pfx, uri)

    quelle: zipfile.ZipFile = zipfile.ZipFile(VORLAGE_EXCEL)
    sheet_datei: str | None = _sheet_datei_fuer_blatt(quelle, blatt)
    if sheet_datei is None:
        quelle.close()
        raise SystemExit(f"Blatt '{blatt}' nicht in der Excel-Vorlage gefunden.")

    root: ET.Element = ET.fromstring(quelle.read(sheet_datei))
    # Welche Zellen gibt es in der Vorlage? Nur die anpacken, die da sind.
    vorhandene: set[str] = {
        c.get("r", "") for c in root.iter(f"{{{M}}}c") if c.get("r")
    }
    fehlend: list[str] = []
    for zelle, wert in setzwerte.items():
        if zelle in vorhandene:
            _set_zelle_inline(root, zelle, wert)
        else:
            fehlend.append(zelle)
    # Cachte Formelergebnisse (<v>) entfernen, damit Excel die Werte
    # neu berechnet. Sonst bleiben alte Werte (z.B. D-Spalte "A1")
    # erhalten, auch wenn die referenzierten F/G-Zellen geaendert wurden.
    M_c: str = f"{{{M}}}c"
    M_v: str = f"{{{M}}}v"
    M_f: str = f"{{{M}}}f"
    for cell in root.iter(M_c):
        if cell.find(M_f) is not None:
            old_v: ET.Element | None = cell.find(M_v)
            if old_v is not None:
                cell.remove(old_v)
    neue_xml: bytes = ET.tostring(root, encoding="UTF-8", xml_declaration=True)

    # Neues Archiv im Speicher: alle Dateien kopieren, nur sheet_datei ersetzen.
    puffer: io.BytesIO = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as ziel:
        for item in quelle.infolist():
            daten: bytes = quelle.read(item.filename)
            if item.filename == sheet_datei:
                daten = neue_xml
            ziel.writestr(item, daten)
    quelle.close()
    return puffer.getvalue(), fehlend


def erzeuge_excel_bytes(
    eintraege: list[dict[str, Any]],
    personen: list[dict[str, Any]],
    layout: dict[str, Any],
    cfg: dict[str, Any],
    spitznamen: dict[str, str] | None = None,
    solo_personen: dict[str, str] | None = None
) -> tuple[bytes, dict[str, Any], list[str], dict[str, Any]]:
    """Baut den X32-Belegungsplan. Rueckgabe: (bytes, setzwerte, fehlend, bericht).

       setzwerte: Zell-ref -> Wert (Zahl oder String). Wird sowohl hier als
       auch im Regenerate-Pfad (siehe lobpreis_planer.regeneriere_excel_und_scene)
       wiederverwendet, um nach UI-Edits neue .xlsx-Bytes zu rendern, ohne
       berechne_excel_werte erneut laufen zu lassen.
    """
    ecfg: dict[str, Any] = cfg["excel"]
    blatt: str = ecfg["blatt"]
    setzwerte: dict[str, Any]
    bericht: dict[str, Any]
    setzwerte, bericht = berechne_excel_werte(
        eintraege, personen, layout, cfg, spitznamen, solo_personen)

    # SB1/SB2-Patchliste (R/S bzw. Y/Z) aus der F/G-Zuordnung neu schreiben.
    # (Die Vorlagen-Formeln INDIRECT(...) folgen unserer Zuordnung nicht und
    #  erzeugen sonst doppelte/falsche Eintraege.)
    _baue_sb_patchliste(setzwerte, cfg)

    # Strukturierte Patchliste fuer das UI (Spiegel von setzwerte,
    # leicht lesbar als A-Liste). Stammt aus der SB-Patchliste.
    sb1, sb2 = _rekonstruiere_sb_aus_setzwerte(setzwerte)
    kap_sb: int = ecfg.get("stagebox_kapazitaet", 16)
    bericht["stagebox1"] = _sb_liste(sb1, 0)
    bericht["stagebox2"] = _sb_liste(sb2, kap_sb)
    bericht["inputs"] = _inputs_reihenfolge(setzwerte, cfg)

    bytes_xlsx, fehlend = setzwerte_zu_xlsx_bytes(setzwerte, blatt)
    return bytes_xlsx, setzwerte, fehlend, bericht
