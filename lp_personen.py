"""Namens-Helfer: Anzeigenamen, Rollen-Kurzbezeichnungen, Labels."""

from typing import Any


def vorname(name: str | None) -> str:
    return name.split()[0] if name else ""


def anzeige_name(
    name: str | None,
    spitznamen: dict[str, str] | None = None,
    fmt: str = "vorname"
) -> str:
    """Anzeigename: Spitzname falls hinterlegt, sonst Vorname (oder voller Name)."""
    if spitznamen and name and name in spitznamen and str(spitznamen[name]).strip():
        return str(spitznamen[name]).strip()
    if fmt == "voll":
        return name or ""
    return vorname(name)


def kurz_rolle(
    r: str,
    person_name: str,
    rollen_kurz: dict[str, str],
    solo_cfg: dict[str, Any] | None = None
) -> str:
    """Kurzbezeichnung einer Rolle. 'Solo' wird zum tatsaechlichen Instrument
       (Geige/Bratsche, person-spezifisch); sonst aus rollen_kurz."""
    if solo_cfg and r == solo_cfg.get("rolle", "Solo"):
        return solo_cfg.get("personen", {}).get(person_name, solo_cfg.get("standard", "Geige"))
    return rollen_kurz.get(r, r)


def label_fuer_person(
    person: dict[str, Any],
    rollen_kurz: dict[str, str],
    ausblenden: list[str] | None = None,
    spitznamen: dict[str, str] | None = None,
    solo_cfg: dict[str, Any] | None = None
) -> str:
    """Feldtext 'Anzeigename\\nRolle1, Rolle2'. Versteckt Leitungs-Rollen
       (ausblenden), bildet 'Gesang'->'Voc' und 'Solo'->Instrument ab, dedupliziert."""
    aus: set[str] = set(ausblenden or [])
    kurz: list[str] = []
    for r in person["rollen"]:
        if r in aus:
            continue
        k = kurz_rolle(r, person["name"], rollen_kurz, solo_cfg)
        if k not in kurz:
            kurz.append(k)
    # 'Voc' immer an erster Stelle im Feld
    voc = rollen_kurz.get("Gesang", "Voc")
    if voc in kurz:
        kurz.remove(voc)
        kurz.insert(0, voc)
    vn = anzeige_name(person["name"], spitznamen)
    return vn + ("\n" + ", ".join(kurz) if kurz else "")


def _singt(person: dict[str, Any], sing_rollen: list[str]) -> bool:
    return any(r in sing_rollen for r in person["rollen"])
