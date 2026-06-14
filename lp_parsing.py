"""Eingabe-Parsing: Besetzungs-Text in Einträge und Personen umwandeln."""

import re
from typing import Any

from lp_konfig import KUERZEL


def parse_besetzung(pfad: str) -> tuple[list[dict[str, Any]], str | None]:
    """Liest die Besetzungsdatei und parst sie (siehe parse_besetzung_text)."""
    with open(pfad, encoding="utf-8") as f:
        return parse_besetzung_text(f.read())


def parse_besetzung_text(text: str) -> tuple[list[dict[str, Any]], str | None]:
    """Parst rohen Besetzungs-Text. Rueckgabe:
       eintraege: Liste von dicts {rolle, index, name}
       kuerzel:   erkanntes Kuerzel (z.B. 'DD1') oder None
    """
    eintraege: list[dict[str, Any]] = []
    kuerzel: str | None = None
    for zeile in text.splitlines():
        zeile = zeile.strip()
        if not zeile or ":" not in zeile:
            continue
        links, name = zeile.split(":", 1)
        name = name.strip()
        tokens = links.split()

        # Kuerzel und optionalen Index (Zahl nach dem Kuerzel) heraussuchen
        rolle_tokens: list[str] = []
        index: int | None = None
        for i, tok in enumerate(tokens):
            if KUERZEL.match(tok):
                kuerzel = tok
                # Falls danach noch eine Zahl steht -> Index (z.B. Gesang DD1 2)
                if i + 1 < len(tokens) and tokens[i + 1].isdigit():
                    index = int(tokens[i + 1])
                break
            rolle_tokens.append(tok)
        else:
            # kein Kuerzel gefunden -> ganzes Links ist die Rolle
            rolle_tokens = tokens

        rolle = " ".join(rolle_tokens).strip()
        if not rolle:
            continue

        unbesetzt = name in ("", "?", "-", "–", "—")
        eintraege.append({
            "rolle": rolle,
            "index": index,
            "name": None if unbesetzt else name,
        })
    return eintraege, kuerzel


def personen_aus_eintraegen(
    eintraege: list[dict[str, Any]],
    rollen_reihenfolge: list[str]
) -> list[dict[str, Any]]:
    """Fasst Eintraege pro Person zusammen.
       Rueckgabe: Liste von dicts {name, rollen:[...]}, in stabiler Reihenfolge.
    """
    reihen_idx: dict[str, int] = {r: i for i, r in enumerate(rollen_reihenfolge)}
    personen: dict[str, list[str]] = {}
    erst_gesehen: list[str] = []
    for e in eintraege:
        if e["name"] is None:
            continue
        p = personen.setdefault(e["name"], [])
        if e["rolle"] not in p:
            p.append(e["rolle"])
            if e["name"] not in erst_gesehen:
                erst_gesehen.append(e["name"])

    def sort_rollen(rollen: list[str]) -> list[str]:
        return sorted(rollen, key=lambda r: reihen_idx.get(r, 999))

    return [{"name": n, "rollen": sort_rollen(personen[n])} for n in erst_gesehen]
