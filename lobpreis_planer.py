#!/usr/bin/env python3
"""Lobpreis-Planer: Skizze + X32-Belegungsplan + X32-Szene aus einer Besetzung.

Pipeline: Text → parse → zuordnen → layout (Quelle der Wahrheit) → .excalidraw → .xlsx → .scn → SVG.
"""

import argparse
import json
import os
import re
import sys
from typing import Any

# -- Sub-Module (nach Pipeline-Stufen gegliedert) --
from lp_konfig import (  # noqa: F401  (re-export für externe Nutzer)
    BASIS, KONFIG, SPITZNAMEN, SOLO_PERSONEN, EINSTELLUNGEN, CHURCHTOOLS, CHURCHTOOLS_ALT,
    VORLAGE_SKIZZE, VORLAGE_EXCEL, VORLAGEN_DIR, AUSGABE, M, KUERZEL,
    _deep_merge, _schreibe_json_atomar, _SCHREIB_LOCK,
    lade_konfig, lade_einstellungen, speichere_einstellungen,
    lade_churchtools, speichere_churchtools,
    lade_spitznamen, speichere_spitznamen,
    lade_solo_personen, speichere_solo_personen,
)
from lp_parsing import parse_besetzung, parse_besetzung_text, personen_aus_eintraegen  # noqa: F401
from lp_personen import vorname, anzeige_name, kurz_rolle, label_fuer_person  # noqa: F401
from lp_layout import zuordnen, berechne_layout  # noqa: F401
from lp_skizze import erzeuge_skizze_doc, vorlage_buehne_groesse  # noqa: F401
from lp_excel import (  # noqa: F401
    _sheet_datei_fuer_blatt, _set_zelle_inline, _fuelle_zelle,
    _spalte_zu_nr, _zell_sortkey,
    berechne_excel_werte, erzeuge_excel_bytes,
    setzwerte_zu_xlsx_bytes,
)
from lp_scene import erzeuge_scene, scene_anwenden, render_svg, SceneFehler  # noqa: F401

# -- Vorlagen-Selbstcheck (hier, weil er lp_konfig + lp_excel braucht) --

class VorlagenFehler(Exception):
    pass


def pruefe_vorlagen(cfg: dict[str, Any] | None = None) -> bool:
    """Prueft, ob die Vorlagen alle in der Konfig erwarteten Element-IDs / Zellen /
       Dateien enthalten. Wirft VorlagenFehler mit klarer Liste -- so faellt eine
       veraenderte/kaputte Vorlage beim Start auf, statt spaeter still falsch zu
       rendern. Gibt bei Erfolg True zurueck."""
    cfg = cfg or lade_konfig()
    fehler: list[str] = []

    # 1) Excalidraw-Skizze: alle referenzierten Element-IDs muessen existieren
    try:
        with open(VORLAGE_SKIZZE, encoding="utf-8") as f:
            doc: dict[str, Any] = json.load(f)
        ids: set[str] = {e.get("id") for e in doc.get("elements", [])}
        bcfg: dict[str, Any] = cfg.get("buehne", {})
        benoetigt: list[str | None] = [
            bcfg.get("buehne_rect_id"),
            (bcfg.get("box_stil") or {}).get("rect_id_vorlage"),
            (bcfg.get("box_stil") or {}).get("text_id_vorlage"),
        ]
        benoetigt += list(bcfg.get("entfernen_rect_ids", []))
        for k in bcfg.get("kreise", []):
            benoetigt += [k.get("ellipse_id_vorlage"), k.get("text_id_vorlage")]
        for rid in benoetigt:
            if rid and rid not in ids:
                fehler.append(f"Excalidraw-Vorlage: Element-ID '{rid}' fehlt "
                              f"({os.path.basename(VORLAGE_SKIZZE)}).")
    except FileNotFoundError:
        fehler.append(f"Excalidraw-Vorlage nicht gefunden: {VORLAGE_SKIZZE}")

    # 2) Excel-Vorlage: Datei + Ziel-Blatt vorhanden
    try:
        import zipfile
        z: zipfile.ZipFile = zipfile.ZipFile(VORLAGE_EXCEL)
        try:
            blatt: str | None = cfg.get("excel", {}).get("blatt")
            if blatt and _sheet_datei_fuer_blatt(z, blatt) is None:
                fehler.append(f"Excel-Vorlage: Blatt '{blatt}' nicht gefunden "
                              f"({os.path.basename(VORLAGE_EXCEL)}).")
        finally:
            z.close()
    except FileNotFoundError:
        fehler.append(f"Excel-Vorlage nicht gefunden: {VORLAGE_EXCEL}")

    # 3) Szene-Vorlage (optional, nur wenn konfiguriert)
    scfg: dict[str, Any] = cfg.get("scene") or {}
    if scfg.get("vorlage"):
        pfad: str = os.path.join(VORLAGEN_DIR, scfg["vorlage"])
        if not os.path.isfile(pfad):
            fehler.append(f"Szene-Vorlage nicht gefunden: {scfg['vorlage']}")

    if fehler:
        raise VorlagenFehler(
            "Vorlagen-Selbstcheck fehlgeschlagen:\n  - " + "\n  - ".join(fehler)
            + "\nVorlagen in vorlagen/ oder die IDs/Zellen in config/mapping.json pruefen.")
    return True


# -- High-Level-Orchestrator --

def plane(
    text: str,
    cfg: dict[str, Any],
    spitznamen: dict[str, str] | None = None,
    solo_personen: dict[str, str] | None = None,
    stapel_skizze: bool = False
) -> dict[str, Any]:
    """Komplette Verarbeitung aus rohem Besetzungs-Text.
       Rueckgabe-dict mit Bericht-Daten, skizze_doc, excel_bytes, svg.
    """
    bcfg: dict[str, Any] = cfg["buehne"]
    rollen_kurz: dict[str, str] = cfg["rollen_kurz"]
    ausblenden: list[str] = cfg.get("label_ausblenden", [])
    # Person-spezifische Solo-Instrumente (editierbar) ueberschreiben die Konfig
    solo_cfg: dict[str, Any] = dict(cfg.get("solo_instrument") or {})
    solo_cfg["personen"] = {**(solo_cfg.get("personen") or {}), **(solo_personen or {})}

    eintraege, kuerzel = parse_besetzung_text(text)
    personen: list[dict[str, Any]] = personen_aus_eintraegen(eintraege, cfg["rollen_reihenfolge"])
    zuord: dict[str, Any] = zuordnen(personen, bcfg, cfg.get("sing_rollen", ["Gesang"]),
                                      cfg.get("modus"))
    doc, layout = erzeuge_skizze_doc(zuord, cfg, spitznamen, return_layout=True,
                                     solo_cfg=solo_cfg, stapel=stapel_skizze)
    excel_bytes, setzwerte, fehlend, excel_bericht = erzeuge_excel_bytes(
        eintraege, personen, layout, cfg, spitznamen, solo_cfg["personen"])
    scene_text, scene_bericht = erzeuge_scene(eintraege, cfg, spitznamen, excel_bericht)
    svg: str = render_svg(doc, layout.get("keys"), layout.get("stacks"))
    excel_bytes = _bette_skizze_in_excel(excel_bytes, json.dumps(doc, ensure_ascii=False))
    def rollen_anzeige(person: dict[str, Any]) -> str:
        return ", ".join(
            dict.fromkeys(
                kurz_rolle(r, person["name"], rollen_kurz, solo_cfg)
                for r in person["rollen"] if r not in ausblenden
            )
        )

    def an(p: dict[str, Any]) -> str:
        return anzeige_name(p["name"], spitznamen)

    vorne: list[dict[str, str]] = [
        {"name": an(p), "voll": p["name"], "rollen": rollen_anzeige(p)}
        for p in zuord["vorne"]
    ]
    hinten: list[dict[str, str]] = [
        {"name": an(p), "voll": p["name"], "instrument": instr,
         "rollen": rollen_anzeige(p)}
        for p, instr in zuord["hinten"]
    ]
    solo: list[dict[str, str]] = [
        {"name": an(p), "voll": p["name"], "rollen": rollen_anzeige(p)}
        for p in zuord["solo"]
    ]

    return {
        "kuerzel": kuerzel,
        "personen": personen,
        "vorne": vorne,
        "hinten": hinten,
        "solo": solo,
        "excel": excel_bericht,
        "setzwerte": setzwerte,   # Zell-ref -> Wert, fuer den Regenerate-Pfad
        "fehlend": fehlend,
        "skizze_doc": doc,
        "excel_bytes": excel_bytes,
        "scene_text": scene_text,
        "scene": scene_bericht,
        "svg": svg,
    }


# -- Regenerate-Pfad: UI-Edits -> neue Excel/Scene-Bytes --

import copy as _copy  # lokaler Alias, damit plane() oben unveraendert bleibt
import io as _io
import zipfile as _zipfile
import xml.etree.ElementTree as _ET


_REL_NS: str = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_DRAW_CT: str = "application/vnd.openxmlformats-officedocument.drawing+xml"
_LEERE_RELS: bytes = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    b'</Relationships>')


def _ct_ergaenze(ct: bytes, draw_part: str) -> bytes:
    """Drawing-Override und excalidraw-Default in [Content_Types].xml sicherstellen."""
    if b'Extension="excalidraw"' not in ct:
        ct = ct.replace(
            b"</Types>",
            b'<Default Extension="excalidraw" ContentType="application/json"/></Types>')
    if ('PartName="/%s"' % draw_part).encode() not in ct:
        ct = ct.replace(
            b"</Types>",
            ('<Override PartName="/%s" ContentType="%s"/>' % (draw_part, _DRAW_CT)).encode()
            + b"</Types>")
    return ct


def _blatt_mit_zeichnung(ws: bytes, rid: str) -> bytes:
    """<drawing>-Verweis (falls fehlend) einfuegen und das Blatt auf eine Druckseite
       skalieren (Fit-to-Page). Macht das Einbetten robust gegen Vorlagen ohne Zeichnung."""
    if b"<drawing " not in ws:
        i: int = ws.find(b"<worksheet")
        j: int = ws.find(b">", i)
        if i != -1 and b"xmlns:r=" not in ws[i:j]:
            ws = ws[:j] + (' xmlns:r="%s"' % _REL_NS).encode() + ws[j:]
        ws = ws.replace(b"</worksheet>",
                        ('<drawing r:id="%s"/></worksheet>' % rid).encode(), 1)
    return (ws.replace(b'fitToPage="false"', b'fitToPage="true"')
              .replace(b'fitToPage="0"', b'fitToPage="1"'))


def _rels_mit_zeichnung(rels: bytes, rid: str, draw_part: str) -> bytes:
    """Drawing-Relationship in eine (ggf. leere) worksheet-rels einfuegen."""
    if ('Id="%s"' % rid).encode() in rels:
        return rels
    target: str = "../" + draw_part[len("xl/"):]
    rel: bytes = ('<Relationship Id="%s" Type="%s/drawing" Target="%s"/>'
                  % (rid, _REL_NS, target)).encode()
    return rels.replace(b"</Relationships>", rel + b"</Relationships>")


def _bette_skizze_in_excel(excel_bytes: bytes, excalidraw_json: str,
                           skizze_blatt: str = "Bühnenaufbau") -> bytes:
    """Bettet die Buehnenskizze als native Excel-Shapes (Rechtecke, Texte, Linien,
       Ellipsen) auf das Blatt `skizze_blatt` ein und skaliert es auf eine Druckseite.
       Die Zeichnung wird bei Bedarf KOMPLETT neu angelegt (Teil + Relationship +
       Content-Type + <drawing>-Element) -- so bleibt das Einbetten heil, auch wenn die
       Vorlage gar keine Zeichnung (mehr) enthaelt (z.B. nach manueller Bearbeitung).
       Die .excalidraw-Datei wird zusaetzlich als Anhang gespeichert."""
    excal_data: dict[str, Any] = json.loads(excalidraw_json)
    elements: list[dict[str, Any]] = [
        e for e in excal_data.get("elements", []) if not e.get("isDeleted")]
    drawing_bytes: bytes = _baue_drawing_xml(elements, 9525).encode("utf-8")

    with _zipfile.ZipFile(_io.BytesIO(excel_bytes), "r") as quelle:
        namen: set[str] = set(quelle.namelist())
        ws_part: str | None = _sheet_datei_fuer_blatt(quelle, skizze_blatt)

        draw_part: str = "xl/drawings/drawing1.xml"
        draw_rid: str = "rId1"
        rels_part: str = ""
        if ws_part:
            ws_xml: str = quelle.read(ws_part).decode("utf-8")
            rels_part = "xl/worksheets/_rels/" + ws_part.rsplit("/", 1)[1] + ".rels"
            rels_xml: str = (quelle.read(rels_part).decode("utf-8")
                             if rels_part in namen else "")
            # Verweist das Blatt bereits auf eine Zeichnung? -> deren Teil/Id nutzen.
            m: re.Match[str] | None = re.search(r'<drawing[^>]*r:id="([^"]+)"', ws_xml)
            mt: re.Match[str] | None = (
                re.search(r'Id="%s"[^>]*Target="([^"]+)"' % re.escape(m.group(1)), rels_xml)
                if m and rels_xml else None)
            if mt:
                draw_rid = m.group(1)  # type: ignore[union-attr]
                ziel_t: str = mt.group(1).replace("../", "")
                draw_part = ziel_t if ziel_t.startswith("xl/") else "xl/" + ziel_t
            else:
                vorhandene: list[int] = [int(x) for x in re.findall(r'Id="rId(\d+)"', rels_xml)]
                draw_rid = "rId%d" % ((max(vorhandene) + 1) if vorhandene else 1)

        puffer: _io.BytesIO = _io.BytesIO()
        with _zipfile.ZipFile(puffer, "w", _zipfile.ZIP_DEFLATED) as ziel:
            for item in quelle.infolist():
                name: str = item.filename
                daten: bytes = quelle.read(name)
                if name == "xl/media/image1.png":
                    continue  # alte Bilddatei wird nicht mehr gebraucht
                if name == draw_part:
                    daten = drawing_bytes  # vorhandene Zeichnung ersetzen
                elif name == "[Content_Types].xml":
                    daten = _ct_ergaenze(daten, draw_part)
                elif ws_part and name == ws_part:
                    daten = _blatt_mit_zeichnung(daten, draw_rid)
                elif ws_part and name == rels_part:
                    daten = _rels_mit_zeichnung(daten, draw_rid, draw_part)
                ziel.writestr(item, daten)
            # In der Vorlage fehlende Teile ergaenzen (z.B. Skizze war geloescht):
            if draw_part not in namen:
                ziel.writestr(_zipfile.ZipInfo(draw_part), drawing_bytes)
            if ws_part and rels_part not in namen:
                ziel.writestr(_zipfile.ZipInfo(rels_part),
                              _rels_mit_zeichnung(_LEERE_RELS, draw_rid, draw_part))
            ziel.writestr(_zipfile.ZipInfo("xl/media/skizze.excalidraw"),
                          excalidraw_json.encode("utf-8"))
    return puffer.getvalue()


def _baue_drawing_xml(elements: list[dict[str, Any]], emu: int) -> str:
    """Erzeugt DrawingML-XML: alle Excalidraw-Elemente als Vektor-Shapes in EINER
       an Zelle A1 verankerten Gruppe (oneCellAnchor). So rendert die Skizze in
       Excel UND LibreOffice und skaliert beim Drucken sauber mit (Fit-to-Page)."""
    xmlns: str = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
    a: str = "http://schemas.openxmlformats.org/drawingml/2006/main"
    r: str = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

    # Begrenzungsrahmen aller Elemente (in Pixel), inkl. Linien-Stuetzpunkte.
    xs: list[float] = []
    ys: list[float] = []
    for e in elements:
        x: float = float(e.get("x", 0))
        y: float = float(e.get("y", 0))
        w: float = float(e.get("width", 0))
        h: float = float(e.get("height", 0))
        xs += [x, x + w]
        ys += [y, y + h]
        if e.get("type") == "line":
            for px, py in (e.get("points") or []):
                xs.append(x + px)
                ys.append(y + py)
    if not xs:
        return f'<xdr:wsDr xmlns:xdr="{xmlns}" xmlns:a="{a}"/>'

    rand: float = 10.0
    minx: float = min(xs) - rand
    miny: float = min(ys) - rand
    gesamt_w: int = int((max(xs) + rand - minx) * emu)
    gesamt_h: int = int((max(ys) + rand - miny) * emu)

    # Kind-Shapes mit auf (0,0) normierten Koordinaten (relativ zum Rahmen).
    shapes: list[str] = []
    sid: int = 2  # id 1 gehoert der Gruppe selbst
    for e in elements:
        t: str | None = e.get("type")
        nx: float = float(e.get("x", 0)) - minx
        ny: float = float(e.get("y", 0)) - miny
        w = float(e.get("width", 0))
        h = float(e.get("height", 0))
        stroke: str = e.get("strokeColor") or "1e1e1e"
        bg: str = e.get("backgroundColor") or ""
        off_x: int = int(nx * emu)
        off_y: int = int(ny * emu)
        cx: int = int(w * emu)
        cy: int = int(h * emu)
        if t == "rectangle":
            shapes.append(_shape_rect(sid, off_x, off_y, cx, cy, stroke, bg))
        elif t == "ellipse":
            shapes.append(_shape_ellipse(sid, off_x, off_y, cx, cy, stroke, bg))
        elif t == "text":
            txt: str = e.get("text", "")
            fs: int = e.get("fontSize", 16)
            shapes.append(_shape_text(sid, off_x, off_y, cx, cy, txt, fs, stroke))
        elif t == "line":
            pts: list[list[float]] = e.get("points") or []
            if len(pts) >= 2:
                shapes.append(_shape_line(sid, nx, ny, pts, emu, stroke))
        sid += 1

    return (
        f'<xdr:wsDr xmlns:xdr="{xmlns}" xmlns:a="{a}" xmlns:r="{r}">'
        f'<xdr:oneCellAnchor>'
        f'<xdr:from><xdr:col>0</xdr:col><xdr:colOff>0</xdr:colOff>'
        f'<xdr:row>0</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>'
        f'<xdr:ext cx="{gesamt_w}" cy="{gesamt_h}"/>'
        f'<xdr:grpSp>'
        f'<xdr:nvGrpSpPr><xdr:cNvPr id="1" name="Buehnenskizze"/>'
        f'<xdr:cNvGrpSpPr/></xdr:nvGrpSpPr>'
        f'<xdr:grpSpPr><a:xfrm><a:off x="0" y="0"/>'
        f'<a:ext cx="{gesamt_w}" cy="{gesamt_h}"/>'
        f'<a:chOff x="0" y="0"/><a:chExt cx="{gesamt_w}" cy="{gesamt_h}"/></a:xfrm>'
        f'</xdr:grpSpPr>'
        f'{"".join(shapes)}'
        f'</xdr:grpSp>'
        f'<xdr:clientData/>'
        f'</xdr:oneCellAnchor></xdr:wsDr>'
    )


def _shape_rect(sid: int, ox: int, oy: int, cx: int, cy: int,
                stroke: str, bg: str) -> str:
    fill: str = ""
    if bg and bg != "transparent":
        fill = f'<a:solidFill><a:srgbClr val="{bg.lstrip("#")}"/></a:solidFill>'
    return (
        f'<xdr:sp><xdr:nvSpPr><xdr:cNvPr id="{sid}" name="R{sid}"/>'
        f'<xdr:cNvSpPr/></xdr:nvSpPr>'
        f'<xdr:spPr><a:xfrm><a:off x="{ox}" y="{oy}"/><a:ext cx="{cx}" cy="{cy}"/>'
        f'</a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        f'{fill}'
        f'<a:ln w="12700"><a:solidFill><a:srgbClr val="{stroke.lstrip("#")}"/></a:solidFill></a:ln>'
        f'</xdr:spPr><xdr:style><a:lnRef idx="0"><a:scrgbClr r="0" g="0" b="0"/>'
        f'</a:lnRef><a:fillRef idx="0"><a:scrgbClr r="0" g="0" b="0"/></a:fillRef>'
        f'<a:effectRef idx="0"><a:scrgbClr r="0" g="0" b="0"/></a:effectRef>'
        f'<a:fontRef idx="minor"><a:schemeClr val="dk1"/></a:fontRef>'
        f'</xdr:style><xdr:txBody><a:bodyPr/><a:p/></xdr:txBody></xdr:sp>'
    )


def _shape_ellipse(sid: int, ox: int, oy: int, cx: int, cy: int,
                   stroke: str, bg: str) -> str:
    fill: str = ""
    if bg and bg != "transparent":
        fill = f'<a:solidFill><a:srgbClr val="{bg.lstrip("#")}"/></a:solidFill>'
    return (
        f'<xdr:sp><xdr:nvSpPr><xdr:cNvPr id="{sid}" name="E{sid}"/>'
        f'<xdr:cNvSpPr/></xdr:nvSpPr>'
        f'<xdr:spPr><a:xfrm><a:off x="{ox}" y="{oy}"/><a:ext cx="{cx}" cy="{cy}"/>'
        f'</a:xfrm><a:prstGeom prst="ellipse"><a:avLst/></a:prstGeom>'
        f'{fill}'
        f'<a:ln w="12700"><a:solidFill><a:srgbClr val="{stroke.lstrip("#")}"/></a:solidFill></a:ln>'
        f'</xdr:spPr></xdr:sp>'
    )


def _shape_line(sid: int, x: int, y: int, pts: list[list[float]],
                emu: int, stroke: str) -> str:
    p0x: int = int((x + pts[0][0]) * emu)
    p0y: int = int((y + pts[0][1]) * emu)
    p1x: int = int((x + pts[1][0]) * emu)
    p1y: int = int((y + pts[1][1]) * emu)
    return (
        f'<xdr:cxnSp><xdr:nvCxnSpPr><xdr:cNvPr id="{sid}" name="L{sid}"/>'
        f'<xdr:cNvCxnSpPr/></xdr:nvCxnSpPr>'
        f'<xdr:spPr><a:xfrm><a:off x="{min(p0x,p1x)}" y="{min(p0y,p1y)}"/>'
        f'<a:ext cx="{abs(p1x-p0x) or 1}" cy="{abs(p1y-p0y) or 1}"/></a:xfrm>'
        f'<a:prstGeom prst="line"><a:avLst/></a:prstGeom>'
        f'<a:ln w="9525"><a:solidFill><a:srgbClr val="{stroke.lstrip("#")}"/></a:solidFill></a:ln>'
        f'</xdr:spPr></xdr:cxnSp>'
    )


def _shape_text(sid: int, ox: int, oy: int, cx: int, cy: int,
                txt: str, fs: int, stroke: str) -> str:
    lines: list[str] = txt.split("\n")
    ps: list[str] = []
    for i, line in enumerate(lines):
        b: str = "1" if i == 0 else "0"
        sz: int = int(fs * 100)  # font size in hundredths of a point
        ps.append(
            f'<a:p><a:pPr algn="ctr"/>'
            f'<a:r><a:rPr lang="de-DE" sz="{sz}" b="{b}">'
            f'<a:solidFill><a:srgbClr val="{stroke.lstrip("#")}"/>'
            f'</a:solidFill></a:rPr><a:t>{_xml_esc(line)}</a:t></a:r></a:p>'
        )
    return (
        f'<xdr:sp><xdr:nvSpPr><xdr:cNvPr id="{sid}" name="T{sid}"/>'
        f'<xdr:cNvSpPr txBox="1"/></xdr:nvSpPr>'
        f'<xdr:spPr><a:xfrm><a:off x="{ox}" y="{oy}"/><a:ext cx="{cx}" cy="{cy}"/>'
        f'</a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        f'<a:noFill/></xdr:spPr>'
        f'<xdr:txBody>'
        f'<a:bodyPr wrap="square" lIns="0" tIns="0" rIns="0" bIns="0" '
        f'anchor="ctr" rtlCol="0"><a:normAutofit/></a:bodyPr>'
        f'{"".join(ps)}</xdr:txBody></xdr:sp>'
    )


def _xml_esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")




def _finde_excelzeile_fuer_input(
    setzwerte: dict[str, Any], sb1: int | None, sb2: int | None,
    SB1: str, SB2: str
) -> int | None:
    """Sucht die Excel-Zeile (5..38), deren F/G den Stagebox-Nummern
       sb1/sb2 entsprechen. None wenn nicht gefunden."""
    if isinstance(sb1, int):
        for r in range(5, 39):
            if setzwerte.get(f"{SB1}{r}") == sb1:
                return r
    if isinstance(sb2, int):
        for r in range(5, 39):
            if setzwerte.get(f"{SB2}{r}") == sb2:
                return r
    return None


def _max_sb_nummer(setzwerte: dict[str, Any], spalte: str) -> int:
    """Hoechste vergebene Nummer in einer F/G-Spalte (fuer Stagebox-Wechsel)."""
    return max(
        (v for v in (setzwerte.get(f"{spalte}{r}") for r in range(5, 39))
         if isinstance(v, int)),
        default=0,
    )


def _bus_zu_j_zelle(
    bus_nr: int, ecfg: dict[str, Any]
) -> str | None:
    """Findet die J-Zelle (Monitor-Output), die zum angegebenen Bus gehoert.
       cfg['excel']['monitor']['links_bus']/[rechts_bus] enthalten die Bus-Nummern
       in Reihenfolge; cfg['excel']['monitor']['links']/[rechts] die J-Zellen."""
    mon: dict[str, Any] = ecfg.get("monitor", {})
    links_bus: list[int] = mon.get("links_bus") or []
    rechts_bus: list[int] = mon.get("rechts_bus") or []
    links: list[str] = mon.get("links") or []
    rechts: list[str] = mon.get("rechts") or []
    if bus_nr in links_bus:
        idx: int = links_bus.index(bus_nr)
        if 0 <= idx < len(links):
            return links[idx]
    if bus_nr in rechts_bus:
        idx = rechts_bus.index(bus_nr)
        if 0 <= idx < len(rechts):
            return rechts[idx]
    return None


def regeneriere_excel_und_scene(
    plane_erg: dict[str, Any],
    cfg: dict[str, Any],
    edits: dict[str, Any] | None = None,
    spitznamen: dict[str, str] | None = None,
    solo_personen: dict[str, str] | None = None
) -> dict[str, Any]:
    """Baut neue Excel-Bytes und Scene-Text, ohne plane() neu durchlaufen
       zu muessen. Erwartet das Ergebnis von plane() (mit 'setzwerte',
       'excel', 'scene_text') und ein 'edits'-Dict mit den Aenderungen
       des Frontends. Rueckgabe:

         {
           "excel_bytes":   bytes,        # neue .xlsx
           "excel":         {inputs, stagebox1/2, voc, busse, quellen, ...},
           "scene_text":    str|None,     # neue .scn (oder None)
           "scene":         {...},        # Bericht-Dict
           "fehlend":       [...],        # nicht beschreibbare Zellen
         }

       edits-Format (alle Felder optional):
         {
           "inputs":  [ {label?, mic?, sb1?, sb2?}, ... ]   # Index = Position
                       in plane_erg['excel']['inputs']. sb1/sb2 editierbar,
                       um den Stagebox-Slot zu wechseln.
           "voc":     { voc_index(int): name(str) },        # Vox1..Vox4 Namen
           "busse":   [ {bus: int, name: str} ]             # Monitor-Busse
         }

       Wichtige Annahmen:
         * Die 'layout'/'cx'-Information aus plane() wird NICHT erneut
           berechnet -- die Stagebox-Seite ergibt sich aus den F/G-Zellen
           in setzwerte. Wenn der User per Drag&Drop eine Box zieht, ruft
           das Frontend /api/erzeugen erneut auf, nicht /api/regenerate.
         * Fuer den Scene-Pfad wird die .scn-Vorlage NEU GELADEN (nicht
           scene_text aus plane_erg, weil der schon gepatcht ist und eine
           Re-Anwendung zu Mehrfach-Patches fuehren wuerde)."""
    from lp_excel import (
        _baue_sb_patchliste, _rekonstruiere_sb_aus_setzwerte,
        _sb_liste, _inputs_reihenfolge,
    )
    edits = edits or {}
    setzwerte: dict[str, Any] = _copy.deepcopy(plane_erg["setzwerte"])
    ecfg: dict[str, Any] = cfg["excel"]
    blatt: str = ecfg["blatt"]
    SB1: str = ecfg["sb_spalten"]["SB1"]
    SB2: str = ecfg["sb_spalten"]["SB2"]
    voc_zeilen: list[int] = ecfg["voc"]["zeilen"]

    # -- 1) Edits anwenden: label/.mic/.sb1/.sb2 --
    # Falls das Frontend basis_inputs mitschickt, ist das die
 # unveraenderliche Referenz (Initial-Stand). Sonst fallback auf
 # plane_erg["excel"]["inputs"], das vom blur-Handler zwischenzeitlich
 # mutiert sein kann.
    basis_inputs: list[dict[str, Any]] = (
        plane_erg["basis_inputs"] if "basis_inputs" in plane_erg
        else plane_erg["excel"].get("inputs", [])
    )
    for i, e in enumerate(edits.get("inputs", [])):
        if i >= len(basis_inputs):
            break
        row: dict[str, Any] = basis_inputs[i]
        sb1_alt: int | None = row.get("sb1")
        sb2_alt: int | None = row.get("sb2")
        # Wenn basis_inputs[i] eine Excel-Zeile mitliefert, nehmen wir die
 # direkt -- das ist stabil und eindeutig (F/G-Spalten-Suche ueber
 # sb1_alt wuerde bei mehreren gleichen Slot-Nummern die falsche Zeile
 # treffen, sobald ein Edit die Spalte verschiebt).
        z: int | None = row.get("zeile")
        if z is None:
            sb1_alt_fb: int | None = row.get("sb1")
            sb2_alt_fb: int | None = row.get("sb2")
            z = _finde_excelzeile_fuer_input(setzwerte, sb1_alt_fb, sb2_alt_fb, SB1, SB2)
        if z is None:
            continue
        # Stagebox-Wechsel (sb1/sb2 editieren) -> alte Zuordnung leeren.
        # Wenn der User eine konkrete Nummer mitgibt (z.B. sb2: 5), wird
        # die direkt gesetzt; sonst (sb2: true) bekommt der Kanal den
        # naechsten freien Slot in der gewuenschten Box.
        if "sb1" in e or "sb2" in e:
            new_sb1: Any = e.get("sb1", sb1_alt)
            new_sb2: Any = e.get("sb2", sb2_alt)
            if isinstance(sb1_alt, int):
                setzwerte[f"{SB1}{z}"] = ""
            if isinstance(sb2_alt, int):
                setzwerte[f"{SB2}{z}"] = ""
            if new_sb1 is not None and new_sb1 is not True:
                setzwerte[f"{SB1}{z}"] = int(new_sb1)
            elif new_sb1 is True:
                setzwerte[f"{SB1}{z}"] = _max_sb_nummer(setzwerte, SB1) + 1
            if new_sb2 is not None and new_sb2 is not True:
                setzwerte[f"{SB2}{z}"] = int(new_sb2)
            elif new_sb2 is True:
                setzwerte[f"{SB2}{z}"] = _max_sb_nummer(setzwerte, SB2) + 1
            # basis_inputs aktualisieren, damit nachfolgende Iterationen
 # die _finde_excelzeile_fuer_input-Suche auf den akkumulierten
 # F/G-Spalten arbeiten. Nur anwenden, wenn sb1/sb2 sich tatsaechlich
 # aendert.
            if new_sb1 is not None and new_sb1 is not True:
                row["sb1"] = int(new_sb1)
            if new_sb2 is not None and new_sb2 is not True:
                row["sb2"] = int(new_sb2)
        # Label/Mic
        if e.get("label") is not None:
            setzwerte[f"C{z}"] = str(e["label"])
        if e.get("mic") is not None:
            setzwerte[f"H{z}"] = str(e["mic"])

    # -- 2) Voc-Name-Edits (key = voc_index "1".."4") --
    for voc_str, name in (edits.get("voc") or {}).items():
        try:
            voc_idx: int = int(voc_str)
        except (TypeError, ValueError):
            continue
        if 1 <= voc_idx <= len(voc_zeilen):
            setzwerte[f"C{voc_zeilen[voc_idx - 1]}"] = str(name)
    # -- 2.5) SB-Slots kompaktieren: Voc zuerst, keine Lücken --
    # Sammle alle belegten Zeilen, sortiere: Voc-Zeilen (5..9) zuerst,
 # dann Instrumente (nach Excel-Zeile). Nummeriere pro Stagebox
 # sequenziell von 1 an neu.
    voc_zeilen_set: set[int] = set(voc_zeilen)
    for seite_spalte in (SB1, SB2):
        eintraege_sb: list[int] = []   # Excel-Zeilen, die diese Box belegt
        for r in range(5, 39):
            if isinstance(setzwerte.get(f"{seite_spalte}{r}"), int):
                eintraege_sb.append(r)
        # Voc zuerst (innerhalb Voc: nach Zeile = 5,6,7,8,9)
 # Instrumente dahinter (nach Zeile)
        eintraege_sb.sort(key=lambda r: (0 if r in voc_zeilen_set else 1, r))
        for i, r in enumerate(eintraege_sb, start=1):
            setzwerte[f"{seite_spalte}{r}"] = i
    # Alte F/G-Werte aufraeumen: Zeilen, die KEINE Nummer mehr haben
 # (weil sie leer sind), explizit auf "" setzen.
    for r in range(5, 39):
        if not isinstance(setzwerte.get(f"{SB1}{r}"), int):
            setzwerte[f"{SB1}{r}"] = ""
        if not isinstance(setzwerte.get(f"{SB2}{r}"), int):
            setzwerte[f"{SB2}{r}"] = ""

    # -- 3) Bus-Name-Edits (J-Zellen + Scene-Patches) --
    bus_edits: dict[int, str] = {
        int(b["bus"]): str(b["name"])
        for b in (edits.get("busse") or [])
        if isinstance(b, dict) and "bus" in b and "name" in b
    }
    for bus_nr, name in bus_edits.items():
        j_cell: str | None = _bus_zu_j_zelle(bus_nr, ecfg)
        if j_cell:
            setzwerte[j_cell] = name

    # -- 4) SB-Patchliste (R/S/Y/Z) neu bauen + Excel-Bytes rendern --
    _baue_sb_patchliste(setzwerte, cfg)
    sb1_dict, sb2_dict = _rekonstruiere_sb_aus_setzwerte(setzwerte)
    bytes_xlsx, fehlend = setzwerte_zu_xlsx_bytes(setzwerte, blatt)
    # Skizze (falls vom Client mitgeschickt) wieder einbetten -- der Render-Pfad
    # oben klont nur das Excel-Template; ohne dies verlöre die .xlsx nach jeder
    # UI-Bearbeitung die Buehnenskizze. _bette_skizze_in_excel setzt dabei auch
    # das Fit-to-Page auf dem Buehnenaufbau-Blatt (Skizze auf einer Seite).
    skizze_data: Any = plane_erg.get("skizze_data")
    if skizze_data:
        if not isinstance(skizze_data, str):
            skizze_data = json.dumps(skizze_data, ensure_ascii=False)
        bytes_xlsx = _bette_skizze_in_excel(bytes_xlsx, skizze_data)

    # -- 5) Bericht-Dict rekonstruieren --
    # Reihenfolge: STABIL nach basis_inputs (Excel-Zeile), nicht nach
 # berechneter setzwerte-Reihenfolge. Sonst springt der Frontend-
 # Index, sobald sich die F/G-Spalten aendern, und Folge-Edits gehen
 # auf den falschen Kanal.
    inputs_nach_zeile: dict[int, dict[str, Any]] = {x["zeile"]: x for x in _inputs_reihenfolge(setzwerte, cfg)}
    neue_inputs: list[dict[str, Any]] = [
        inputs_nach_zeile.get(b.get("zeile"), {**b, "label": "", "mic": "", "sb1": None, "sb2": None})
        for b in basis_inputs
    ]
    excel_bericht: dict[str, Any] = _copy.deepcopy(plane_erg["excel"])
    excel_bericht["inputs"] = neue_inputs
    excel_bericht["stagebox1"] = _sb_liste(sb1_dict, 0)
    excel_bericht["stagebox2"] = _sb_liste(sb2_dict, 16)
    # Bus-Namen-Edits auch im Bericht spiegeln, damit der Client-Roundtrip
    # konsistent ist (Outputs-Tabelle zeigt den editierten Namen weiter an).
    for b in (excel_bericht.get("busse") or []):
        if isinstance(b, dict) and b.get("bus") in bus_edits:
            b["name"] = bus_edits[b["bus"]]
    # Quellen pro Excel-Zeile -> A-Nummer (fuer Scene)
    quellen: dict[int, int] = {}
    for r in range(5, 39):
        fv: Any = setzwerte.get(f"{SB1}{r}")
        gv: Any = setzwerte.get(f"{SB2}{r}")
        if isinstance(fv, int):
            quellen[r] = fv
        elif isinstance(gv, int):
            quellen[r] = gv + 16
    excel_bericht["quellen"] = quellen

    # -- 6) Scene: Vorlage neu laden + Patches anwenden --
    scene_text: str | None = None
    scene_bericht: dict[str, Any] = {}
    scfg: dict[str, Any] = cfg.get("scene") or {}
    if scfg.get("vorlage"):
        pfad: str = os.path.join(VORLAGEN_DIR, scfg["vorlage"])
        if os.path.isfile(pfad):
            with open(pfad, encoding="utf-8", errors="replace") as f:
                basis: str = f.read()
            voc_names: dict[int, str] = {}
            for i, vz in enumerate(voc_zeilen):
                name_roh: Any = setzwerte.get(f"C{vz}")
                voc_names[i + 1] = str(name_roh) if name_roh else ""
            # Vollstaendige Bus-Liste als Basis, Edits nur als Override -- sonst
            # verlieren die nicht-editierten Monitor-Busse beim Neu-Laden der
            # .scn-Vorlage ihre Namen (sie reverten auf die Template-Defaults).
            busse: list[dict[str, Any]] = [
                {"bus": int(b["bus"]), "name": b["name"]}
                for b in (excel_bericht.get("busse") or [])
            ]
            for eintrag in busse:
                if eintrag["bus"] in bus_edits:
                    eintrag["name"] = bus_edits[eintrag["bus"]]
            bekannt: set[int] = {b["bus"] for b in busse}
            busse += [{"bus": n, "name": nm}
                      for n, nm in bus_edits.items() if n not in bekannt]
            scene_text, scene_bericht = scene_anwenden(
                basis, cfg, voc_names, quellen, busse, spitznamen)

    return {
        "excel_bytes": bytes_xlsx,
        "setzwerte": setzwerte,   # zurueck an Client, damit Folge-Edits
                                  # auf dem aktuellen Stand aufsetzen
        "excel": excel_bericht,
        "scene_text": scene_text,
        "scene": scene_bericht,
        "fehlend": fehlend,
    }
# -- CLI --
def main() -> None:
    ap: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Lobpreis-Planer: Skizze + X32-Belegungsplan aus Besetzung.")
    ap.add_argument("besetzung", help="Pfad zur Besetzungs-Textdatei")
    ap.add_argument("--titel", default=None, help="Optionaler Titel (Anzeige im Bericht)")
    ap.add_argument("--konfig", default=KONFIG, help="Pfad zu mapping.json")
    args: argparse.Namespace = ap.parse_args()

    cfg: dict[str, Any] = lade_konfig(args.konfig)
    try:
        pruefe_vorlagen(cfg)
    except VorlagenFehler as e:
        raise SystemExit(str(e))
    spitznamen: dict[str, str] = lade_spitznamen()
    solo_personen: dict[str, str] = lade_solo_personen()
    with open(args.besetzung, encoding="utf-8") as f:
        text: str = f.read()
        # Kuerzel vorab parsen für per-event Solo-Instrument-Overrides
        _, kuerzel = parse_besetzung_text(text)
        sp: dict[str, str] = lade_solo_personen(event_key=kuerzel)
        sp.update(solo_personen)  # explizit geladene gewinnen
        ergebnis: dict[str, Any] = plane(text, cfg, spitznamen, sp)

    # Ausgabename = Dateiname der Besetzung (kollisionsfrei; das Kuerzel ist oft
    # bei allen gleich, z.B. DD1). Das Kuerzel erscheint nur im Bericht.
    name: str = os.path.splitext(os.path.basename(args.besetzung))[0]
    os.makedirs(AUSGABE, exist_ok=True)
    skizze_out: str = os.path.join(AUSGABE, f"{name}_Skizze.excalidraw")
    excel_out: str = os.path.join(AUSGABE, f"{name}_Belegungsplan.xlsx")
    with open(skizze_out, "w", encoding="utf-8") as f:
        json.dump(ergebnis["skizze_doc"], f, ensure_ascii=False, indent=1)
    with open(excel_out, "wb") as f:
        f.write(ergebnis["excel_bytes"])
    scene_out: str | None = None
    if ergebnis.get("scene_text"):
        scene_out = os.path.join(AUSGABE, f"{name}.scn")
        with open(scene_out, "w", encoding="utf-8") as f:
            f.write(ergebnis["scene_text"])

    # Bericht
    print(f"== Lobpreis-Planer == {args.titel or name} (Kuerzel: {ergebnis['kuerzel'] or '-'})")
    print(f"\nPersonen ({len(ergebnis['personen'])}):")
    for p in ergebnis["personen"]:
        print(f"  - {p['name']:28} {', '.join(p['rollen'])}")

    print("\nErste Reihe (vorne, links -> rechts):")
    for b in ergebnis["vorne"]:
        print(f"  - {b['name']:16} ({b['rollen']})")
    if ergebnis["solo"]:
        print("Solo-Platz (neben SB1):")
        for b in ergebnis["solo"]:
            print(f"  - {b['name']:16} ({b['rollen']})")
    print("Hintere Reihe (Instrumente):")
    for b in ergebnis["hinten"]:
        print(f"  - {b['name']:16} {b['instrument']:6} ({b['rollen']})")

    ex: dict[str, Any] = ergebnis["excel"]
    print("\nExcel – Voc (Spalte C + Monitor J):")
    for v in ex["voc"]:
        print(f"  Voc{v['voc']} -> {(v['name'] or '(leer)'):16} {v['seite'] or '-'}")
    print("Excel – Instrumente (Seite nach Skizze):")
    for it in ex["instrumente"]:
        zustand: str = f"{it['seite']} ({it['person']})" if it["seite"] else "nicht in Skizze -> geleert"
        print(f"  {it['rolle']:12} -> {zustand}")
    if ex.get("balance"):
        print("  ⚖ Balance-Anpassung (max. 16/Stagebox):")
        for b in ex["balance"]:
            print(f"    {b['label']}: {b['anzahl']} Kanal/Kanäle {b['von']} -> {b['nach']}")
    if ex["ueberzaehlige_saenger"]:
        for s in ex["ueberzaehlige_saenger"]:
            print(f"  WARNUNG: Saenger {s['nr']} ({s['name']}) hat keinen Voc-Kanal (nur Voc1-4).")
    if ergebnis["fehlend"]:
        print(f"  WARNUNG: Zellen nicht gefunden: {ergebnis['fehlend']}")

    sc: dict[str, Any] = ergebnis.get("scene") or {}
    if sc.get("voc"):
        print("\nX32-Szene – Gesangskanaele:")
        for s in sc["voc"]:
            print(f"  Ch{s['kanal']:02d} (Vox{s['voc']}) -> {s['name'] or '(leer)'}")
    if sc.get("busse"):
        print("X32-Szene – Bus-Namen (Monitore):")
        for b in sc["busse"]:
            print(f"  Bus{b['bus']:02d} -> {b['name']}")
    if sc.get("quellen"):
        q: str = ", ".join(f"Ch{x['kanal']}=A{x['source']}" for x in sc["quellen"])
        print(f"X32-Szene – Sources (aus Excel D): {q}")
    if sc.get("engpass"):
        ks: str = ", ".join(f"Ch{x['kanal']}=A{x['source']}" for x in sc["engpass"])
        print(f"  WARNUNG: SB2-Engpass – Source >32 (max. 16 Eingaenge/Stagebox): {ks}")
        print("           -> in der Skizze etwas von rechts (SB2) nach links (SB1) ziehen.")

    print(f"\nGeschrieben:\n  {skizze_out}\n  {excel_out}")
    if scene_out:
        print(f"  {scene_out}")


if __name__ == "__main__":
    main()
