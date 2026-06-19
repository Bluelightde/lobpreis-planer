"""Layout: Zonen-Zuordnung und Box-Positionen.

Die Buehnenskizze (layout aus berechne_layout) ist die **einzige Quelle der Wahrheit**.
Alles Weitere (Excel, Scene) wird aus den X-Positionen relativ zur Buehnenmitte abgeleitet.
"""

from typing import Any

from lp_personen import _singt, label_fuer_person


def zuordnen(
    personen: list[dict[str, Any]],
    bcfg: dict[str, Any],
    sing_rollen: list[str],
    modus: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Zonen-Layout. Pro Person genau ein Platz:
       - Leiter (leiter_rolle)                 -> VORNE, ganz links.
       - Solo/Geige OHNE Gesang                -> SOLO-PLATZ (neben SB1).
       - Drums/Bass (immer=true)               -> HINTEN, auch wenn sie singen.
       - E-Git/A-Git/Piano/Synth, NICHT singend-> HINTEN.
       - alle uebrigen (singen / keine feste Pos) -> VORNE.

       Rueckgabe-dict:
         vorne:  Liste von Personen (links -> rechts, Leiter zuerst)
         hinten: Liste von (person, instrument)
         solo:   Liste von Personen am Solo-Platz
    """
    modus = modus or {}
    sing_vorne: bool = modus.get("singende_instrumentalisten_vorne", True)
    leiter_links: bool = modus.get("leiter_links", True)
    reine_mitte: bool = modus.get("reine_saenger_mitte", True)

    sing: set[str] = set(sing_rollen)
    leiter_rolle: str = bcfg["leiter_rolle"]
    solo_rollen: set[str] = set(bcfg["solo_platz"]["rollen"])
    backline: dict[str, Any] = bcfg["backline"]
    blorder: list[str] = bcfg["backline_reihenfolge"]
    saenger_anzahl: int = sum(1 for p in personen if _singt(p, sing))

    vorne: list[dict[str, Any]] = []
    hinten: list[tuple[dict[str, Any], str]] = []
    solo: list[dict[str, Any]] = []
    belegt: set[str] = set()

    for p in personen:
        rollen: set[str] = set(p["rollen"])
        if leiter_rolle in rollen:
            vorne.append(p)
            continue
        if (rollen & solo_rollen) and not _singt(p, sing):
            solo.append(p)
            continue
        platz: str | None = None
        for instr in blorder:
            if instr in rollen and instr not in belegt:
                bl: dict[str, Any] = backline[instr]
                ab: int | None = bl.get("backline_ab_saengern")
                # immer / ab vielen Saengern / Modus 'singende Instrumentalisten NICHT vorne'
                erzwungen: bool = (bl.get("immer", False)
                             or (ab is not None and saenger_anzahl >= ab)
                             or not sing_vorne)
                if erzwungen or not _singt(p, sing):
                    platz = instr
                    break
        if platz:
            belegt.add(platz)
            hinten.append((p, platz))
        else:
            vorne.append(p)

    # "Ausweichen": EIN nicht singendes Backline-Instrument (A-Git/E-Git) auf den
    # Geige-/Solo-Platz (links neben SB1) verschieben -- aber NUR wenn
    #   (a) dort keine nicht-singende Geige steht (Platz frei), und
    #   (b) eine bestimmte Rolle (Standard: Synth) in der Besetzung ist -- dann ist
    #       die rechte Seite voll und ein Instrument soll nach links ausweichen.
    ausweich_rolle: str | None = bcfg.get("ausweichen_nur_mit_rolle")
    rolle_da: bool = (not ausweich_rolle) or any(ausweich_rolle in p["rollen"] for p in personen)
    if rolle_da and not solo:
        for instr, bl in backline.items():
            if not (isinstance(bl, dict) and bl.get("ausweichen_solo_platz")):
                continue
            treffer = next((pi for pi in hinten if pi[1] == instr), None)
            if treffer:
                hinten.remove(treffer)
                solo.append(treffer[0])
                break

    # Anordnung der ersten Reihe (per Modus steuerbar)
    instr_rollen: set[str] = set(bcfg.get("instrument_rollen", []))

    def hat_instrument(p: dict[str, Any]) -> bool:
        return bool(set(p["rollen"]) & instr_rollen)

    leiter: list[dict[str, Any]] = [p for p in vorne if leiter_rolle in p["rollen"]] if leiter_links else []
    rest: list[dict[str, Any]] = [p for p in vorne if p not in leiter]
    if reine_mitte:
        pur: list[dict[str, Any]] = [p for p in rest if not hat_instrument(p)]
        instr: list[dict[str, Any]] = [p for p in rest if hat_instrument(p)]
        half: int = len(instr) // 2
        vorne_sortiert: list[dict[str, Any]] = leiter + instr[:half] + pur + instr[half:]
    else:
        vorne_sortiert = leiter + rest
    return {"vorne": vorne_sortiert, "hinten": hinten, "solo": solo}


def _label_breite(
    label: str,
    fontsize: int = 20,
    char: float = 0.7,
    pad: int = 32
) -> float:
    """Schaetzt die noetige Box-Breite fuer ein (mehrzeiliges) Label.
       char=0.7 und pad=32 geben etwas mehr Reserve, damit der Text
       auch bei laengeren Namen/Rollen nicht ueber den Box-Rand ragt."""
    zeilen: list[str] = (label or "").split("\n")
    maxlen: int = max((len(z) for z in zeilen), default=0)
    return maxlen * fontsize * char + pad


def berechne_layout(
    zuord: dict[str, Any],
    bcfg: dict[str, Any],
    buehne_rect: dict[str, float],
    lbl: Any = None,
    stapel: bool = False
) -> list[dict[str, Any]]:
    """Berechnet die Box-Positionen aller Personen (eine Quelle fuer Skizze UND
       Excel). Box-Breite waechst dynamisch mit dem Label-Inhalt.
       Rueckgabe: Liste von {person, instrument, zone, x, y, w, h, cx}."""
    plan: list[dict[str, Any]] = []
    wachstum: int = bcfg.get("box_wachstum", 130)

    def breite(p: dict[str, Any], base_w: float, max_w: float) -> float:
        if not lbl:
            return base_w
        return max(base_w, min(max_w, _label_breite(lbl(p))))

    ud: dict[str, Any] = bcfg.get("unter_drums", {})
    ud_rollen: list[str] = ud.get("rollen", [])
    backline_cfg: dict[str, Any] = bcfg["backline"]
    drums: dict[str, Any] = backline_cfg.get("Drums", {})
    unter_drums: list[tuple[dict[str, Any], str]] = [
        (p, instr) for p, instr in zuord["hinten"] if instr in ud_rollen
    ]
    unter_drums.sort(key=lambda pi: ud_rollen.index(pi[1]))
    stapel_y: float = drums.get("y", 225) + drums.get("h", 130) + ud.get("offset_y", 13)
    udw: float = ud.get("w", 150)
    udh: float = ud.get("h", 58)
    udx: float = drums.get("x", 760) + (drums.get("w", 270) - udw) / 2

    # unter_drums-Instrumente entweder UEBEREINANDER stapeln (stapel=True, nur fuer
    # die Einstellungs-Skizze -> z-Stapel mit Ebenen-Schalter) oder NEBENEINANDER mit
    # etwas Abstand (Standard, Hauptseite); die Reihe endet unter der Drums-Mitte.
    versatz: float = ud.get("stapel_versatz", 6)
    gap: float = ud.get("abstand", 16)
    n_ud: int = len(unter_drums)
    stapel_index: dict[str, int] = {instr: i for i, (_p, instr) in enumerate(unter_drums)}
    # Anker des ganzen Clusters: per Drag verschiebbar (Schluessel "Stapel") -> EIN
    # Override fuer die Gruppe statt pro Instrument, damit nichts einzeln gepinnt wird.
    st_ov: dict[str, float] = bcfg.get("positionen", {}).get("Stapel", {})
    basis_x: float = st_ov.get("x", udx)
    basis_y: float = st_ov.get("y", stapel_y)
    stapel_pos: dict[str, dict[str, float]] = {}
    for i, (p, instr) in enumerate(unter_drums):
        if stapel:
            x_ud: float = basis_x + i * versatz
            y_ud: float = basis_y + i * versatz
        else:
            x_ud = basis_x - (n_ud - 1 - i) * (udw + gap)
            y_ud = basis_y
        stapel_pos[instr] = {"x": x_ud, "y": y_ud, "w": udw, "h": udh}

    # Per Drag gesetzte Positions-Ueberschreibungen (Schluessel -> {x, y})
    pos_ov: dict[str, dict[str, float]] = bcfg.get("positionen", {})

    # Hinten + Solo: Box waechst zentriert um ihren Mittelpunkt (bis base+wachstum)
    def platziere_fest(
        p: dict[str, Any],
        pos: dict[str, float],
        zone: str,
        instr: str | None,
        key: str | None
    ) -> None:
        cx0: float = pos["x"] + pos["w"] / 2
        w: float = breite(p, pos["w"], pos["w"] + wachstum)
        x: float = cx0 - w / 2
        y: float = pos["y"]
        ov: dict[str, float] | None = pos_ov.get(key) if key else None
        if ov and ov.get("x") is not None:  # gezogene Position gewinnt
            x, y = ov["x"], ov.get("y", y)
        plan.append({"person": p, "instrument": instr, "zone": zone, "key": key,
                     "x": x, "y": y, "w": w, "h": pos["h"]})

    for p, instr in zuord["hinten"]:
        platziere_fest(p, stapel_pos.get(instr) or bcfg["backline"][instr],
                       "hinten", instr, instr)
        if stapel and instr in stapel_index:
            plan[-1]["stapel"] = "drums"
            plan[-1]["stapel_index"] = stapel_index[instr]
    sp: dict[str, Any] = bcfg["solo_platz"]
    sp_ov: dict[str, float] = pos_ov.get("Solo", {})
    sp_x: float = sp_ov.get("x", sp["x"])
    sp_y: float = sp_ov.get("y", sp["y"])
    for i, p in enumerate(zuord["solo"]):
        pos: dict[str, float] = {"x": sp_x, "y": sp_y + i * sp.get("stapel_dy", 70),
                                  "w": sp["w"], "h": sp["h"]}
        platziere_fest(p, pos, "solo", None, "Solo" if i == 0 else None)

    vcfg: dict[str, Any] = bcfg["vorne"]
    n: int = len(zuord["vorne"])
    if n:
        bx: float = buehne_rect["x"]
        bw: float = buehne_rect["width"]
        spalte: float = (bw - 2 * vcfg["rand"]) / n
        max_w: float = spalte - vcfg["luecke"]
        if vcfg.get("max_box_w"):  # konfigurierte Obergrenze der Box-Breite
            max_w = min(max_w, vcfg["max_box_w"])
        min_w: float = min(vcfg.get("min_box_w", 130), max_w)
        for i, p in enumerate(zuord["vorne"]):
            key: str = f"vorne_{i}"
            # Einzelposition aus den Einstellungen (pos_ov) oder Standard (berechnet)
            v_pos: dict[str, float] = pos_ov.get(key) or pos_ov.get("vorne") or {}
            v_y: float = v_pos.get("y", vcfg["y"])

            cx: float = bx + vcfg["rand"] + spalte * i + spalte / 2
            v_x: float = v_pos.get("x", cx - breite(p, min_w, max_w) / 2)

            w: float = breite(p, min_w, max_w)
            plan.append({"person": p, "instrument": None, "zone": "vorne", "key": key,
                         "x": v_x, "y": v_y, "w": w, "h": vcfg["h"]})
    for e in plan:
        e["cx"] = e["x"] + e["w"] / 2
    return plan
