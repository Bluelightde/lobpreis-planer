"""Excalidraw-Bühnenskizze: Klont die Vorlage und erzeugt Personen-Boxen."""

import copy
import functools
import json
from typing import Any

from lp_konfig import VORLAGE_SKIZZE
from lp_personen import label_fuer_person
from lp_layout import berechne_layout


def _mache_box(
    idx: int, x: float, y: float, w: float, h: float,
    label: str, muster_rect: dict[str, Any], muster_text: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Erzeugt rect+gebundenen text (Stil von der Vorlage geklont, Winkel 0).
       Der Text wird horizontal UND vertikal im Feld zentriert."""
    rect: dict[str, Any] = copy.deepcopy(muster_rect)
    text: dict[str, Any] = copy.deepcopy(muster_text)
    rid: str = f"gen-rect-{idx}"
    tid: str = f"gen-text-{idx}"
    text_h: float = max(25, (label.count("\n") + 1) * 25)
    rect.update({
        "id": rid, "x": x, "y": y, "width": w, "height": h, "angle": 0,
        "version": rect.get("version", 1) + 1,
        "boundElements": [{"type": "text", "id": tid}],
    })
    text.update({
        "id": tid, "x": x + 8, "y": y + (h - text_h) / 2, "width": max(10, w - 16),
        "angle": 0, "containerId": rid, "text": label, "originalText": label,
        "version": text.get("version", 1) + 1, "height": text_h,
        "textAlign": "center", "verticalAlign": "middle",
    })
    return rect, text


def _mache_kreis(
    idx: int, cx: float, cy: float, d: float, label: str,
    muster_ellipse: dict[str, Any], muster_text: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Erzeugt eine Ellipse (Kreis) mit zentriertem Text, Stil von der Vorlage."""
    el: dict[str, Any] = copy.deepcopy(muster_ellipse)
    text: dict[str, Any] = copy.deepcopy(muster_text)
    eid: str = f"gen-ell-{idx}"
    tid: str = f"gen-elltext-{idx}"
    el.update({
        "id": eid, "x": cx - d / 2, "y": cy - d / 2, "width": d, "height": d, "angle": 0,
        "version": el.get("version", 1) + 1,
        "boundElements": [{"type": "text", "id": tid}],
    })
    text.update({
        "id": tid, "x": cx - d / 2 + 6, "y": cy - 12, "width": max(10, d - 12), "angle": 0,
        "containerId": eid, "text": label, "originalText": label,
        "version": text.get("version", 1) + 1, "height": 25,
    })
    return el, text


def erzeuge_skizze_doc(
    zuord: dict[str, Any],
    cfg: dict[str, Any],
    spitznamen: dict[str, str] | None = None,
    return_layout: bool = False,
    solo_cfg: dict[str, Any] | None = None,
    stapel: bool = False
) -> Any:
    """Baut das Excalidraw-Dokument: Vorlagen-Szenerie behalten, Personen-Felder
       der Vorlage entfernen, neue Felder gemaess Zonen-Layout erzeugen."""
    with open(VORLAGE_SKIZZE, encoding="utf-8") as f:
        doc: dict[str, Any] = json.load(f)
    bcfg: dict[str, Any] = cfg["buehne"]
    rollen_kurz: dict[str, str] = cfg["rollen_kurz"]
    ausblenden: list[str] = cfg.get("label_ausblenden", [])
    by_id: dict[str, dict[str, Any]] = {e["id"]: e for e in doc["elements"]}

    muster_rect: dict[str, Any] = by_id[bcfg["box_stil"]["rect_id_vorlage"]]
    muster_text: dict[str, Any] = by_id[bcfg["box_stil"]["text_id_vorlage"]]
    buehne_rect: dict[str, float] = by_id[bcfg["buehne_rect_id"]]

    # Optionaler Override der Buehnen-Dimensionen (UI/Einstellungen). Mutiert das
    # geklonte Rechteck -> wirkt auf berechne_layout (vordere Reihe) UND die Skizze.
    dim: dict[str, Any] = bcfg.get("dimensionen") or {}
    if dim.get("breite") is not None:
        buehne_rect["width"] = float(dim["breite"])
    if dim.get("hoehe") is not None:
        buehne_rect["height"] = float(dim["hoehe"])

    # Kreis-Vorlagen (MD, TS) merken (vor dem Entfernen)
    kreise: list[dict[str, Any]] = bcfg.get("kreise", [])
    kreis_muster: dict[str, tuple[dict[str, Any] | None, dict[str, Any] | None]] = {}
    for k in kreise:
        kreis_muster[k["text"]] = (
            by_id.get(k["ellipse_id_vorlage"]),
            by_id.get(k["text_id_vorlage"])
        )

    # Personen-Felder (und die statischen Kreise) der Vorlage entfernen
    entfernen: set[str] = set(bcfg["entfernen_rect_ids"])
    for k in kreise:
        entfernen.update([k["ellipse_id_vorlage"], k["text_id_vorlage"]])
    for rid in list(entfernen):
        r: dict[str, Any] | None = by_id.get(rid)
        for b in (r.get("boundElements") if r else []) or []:
            if b.get("type") == "text":
                entfernen.add(b["id"])
    doc["elements"] = [e for e in doc["elements"] if e["id"] not in entfernen]
    elemente: list[dict[str, Any]] = doc["elements"]

    if solo_cfg is None:
        solo_cfg = cfg.get("solo_instrument")

    def lbl(p: dict[str, Any]) -> str:
        return label_fuer_person(p, rollen_kurz, ausblenden, spitznamen, solo_cfg)

    plan: list[dict[str, Any]] = berechne_layout(zuord, bcfg, buehne_rect, lbl, stapel)
    for i, e in enumerate(plan):
        label: str = lbl(e["person"])
        rect, text = _mache_box(i, e["x"], e["y"], e["w"], e["h"], label, muster_rect, muster_text)
        elemente.append(rect)
        elemente.append(text)

    # Kreise (MD bei der MD-Person, TS beim Lobpreisleiter) neben die Person setzen
    for ki, k in enumerate(kreise):
        muster_ell, muster_txt = kreis_muster.get(k["text"], (None, None))
        if muster_ell is None:
            continue
        eintrag: dict[str, Any] | None = next(
            (e for e in plan if k["rolle"] in e["person"]["rollen"]), None
        )
        if not eintrag:
            continue
        d: float = k.get("groesse", 50)
        gap: float = k.get("abstand", 4)
        b_links: float = buehne_rect["x"]
        b_rechts: float = buehne_rect["x"] + buehne_rect["width"]
        b_oben: float = buehne_rect["y"]
        rand_abstand: float = k.get("rand_abstand", gap)
        # Standard: obere rechte Ecke der Box (kein Ueberlappen). Reicht der Platz
        # rechts nicht mehr (Kreis kaeme dem Buehnenrand naeher als rand_abstand),
        # wird der Kreis stattdessen mittig ueber die Box gesetzt.
        cx: float = eintrag["x"] + eintrag["w"] + d / 2 + gap + k.get("offset_x", 0)
        if cx + d / 2 > b_rechts - rand_abstand:
            cx = eintrag["x"] + eintrag["w"] / 2 + k.get("offset_x", 0)
        # Sicherheits-Clamp: Kreis bleibt vollstaendig innerhalb des Buehnenrechtecks.
        cx = min(max(cx, b_links + d / 2), b_rechts - d / 2)
        cy: float = eintrag["y"] - d / 2 - gap + k.get("offset_y", 0)
        cy = max(cy, b_oben + d / 2)
        el, t = _mache_kreis(f"{len(plan)}-{ki}", cx, cy, d, k["text"], muster_ell, muster_txt)
        elemente.append(el)
        elemente.append(t)

    # Stagebox-Positionen (fixe_elemente) per Drag-Override verschieben: rect +
    # gebundener Text + Verbindungslinien gemeinsam um das Delta versetzen.
    pos_ov: dict[str, Any] = bcfg.get("positionen", {})
    fixe: dict[str, Any] = bcfg.get("fixe_elemente", {})
    for skey, fe in fixe.items():
        if not isinstance(fe, dict):
            continue
        ov: dict[str, float] | None = pos_ov.get(skey)
        rect: dict[str, Any] | None = by_id.get(fe.get("rect"))
        if not ov or ov.get("x") is None or rect is None:
            continue
        dx: float = ov["x"] - rect.get("x", 0)
        dy: float = ov.get("y", rect.get("y", 0)) - rect.get("y", 0)
        ids: list[str] = [fe.get("rect")] + list(fe.get("linien", []))
        ids += [b.get("id") for b in (rect.get("boundElements") or [])]
        for eid in ids:
            el2: dict[str, Any] | None = by_id.get(eid)
            if el2 is not None:
                el2["x"] = el2.get("x", 0) + dx
                el2["y"] = el2.get("y", 0) + dy

    if return_layout:
        keys: dict[str, str | None] = {
            f"gen-rect-{i}": e["key"] for i, e in enumerate(plan) if e.get("key")
        }
        for skey, fe in fixe.items():
            if isinstance(fe, dict) and fe.get("rect"):
                keys[fe["rect"]] = skey
                for lid in fe.get("linien", []):
                    keys[lid] = skey
        stacks: dict[str, tuple[str, int]] = {
            f"gen-rect-{i}": (e["stapel"], e["stapel_index"])
            for i, e in enumerate(plan) if e.get("stapel")
        }
        return doc, {"plan": plan, "mitte_x": buehne_rect["x"] + buehne_rect["width"] / 2,
                     "keys": keys, "stacks": stacks}
    return doc


@functools.lru_cache(maxsize=1)
def _vorlage_doc() -> dict[str, Any]:
    with open(VORLAGE_SKIZZE, encoding="utf-8") as f:
        return json.load(f)


def vorlage_buehne_groesse(buehne_rect_id: str) -> tuple[float, float]:
    """Breite/Hoehe des Buehnen-Rechtecks aus der Vorlage (fuer die UI-Anzeige
       der effektiven Dimensionen, wenn kein Override gesetzt ist)."""
    for e in _vorlage_doc().get("elements", []):
        if e.get("id") == buehne_rect_id:
            return float(e.get("width", 0)), float(e.get("height", 0))
    return 0.0, 0.0
