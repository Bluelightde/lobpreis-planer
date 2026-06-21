"""Konfiguration: Pfade, Konstanten, Deep-Merge, atomares Schreiben, Lade-/Speicherfunktionen.

Alle Konfig-Schreibvorgänge laufen über _schreibe_json_atomar (Lock + os.replace).
"""

import json
import os
import re
import tempfile
import threading
from typing import Any

BASIS: str = os.path.dirname(os.path.abspath(__file__))
KONFIG: str = os.path.join(BASIS, "config", "mapping.json")
SPITZNAMEN: str = os.path.join(BASIS, "config", "spitznamen.json")
SOLO_PERSONEN: str = os.path.join(BASIS, "config", "solo_personen.json")
EINSTELLUNGEN: str = os.path.join(BASIS, "config", "einstellungen.json")
CHURCHTOOLS: str = os.path.join(BASIS, "config", "config.json")
CHURCHTOOLS_ALT: str = os.path.join(BASIS, "config", "churchtools.json")
SITZUNGEN: str = os.path.join(BASIS, "config", "sitzungen.json")
VORLAGE_SKIZZE: str = os.path.join(BASIS, "vorlagen", "Skizze_default.excalidraw")
VORLAGE_EXCEL: str = os.path.join(BASIS, "vorlagen", "X32-Belegungsplan_Standard.xlsx")
VORLAGEN_DIR: str = os.path.join(BASIS, "vorlagen")
AUSGABE: str = os.path.join(BASIS, "ausgabe")

# Excel-Hauptnamespace
M: str = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

# Ein Kuerzel ist ein Token aus Grossbuchstaben gefolgt von einer Zahl, z.B. DD1, AD2.
KUERZEL: re.Pattern[str] = re.compile(r"^[A-ZÄÖÜ]{1,5}\d+$")


def _deep_merge(base: dict[str, Any], over: dict[str, Any] | None) -> dict[str, Any]:
    """Mischt 'over' rekursiv in 'base' (dicts), Skalare/Listen werden ersetzt."""
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def _lade_json(pfad: str, default: Any = None, strict: bool = False) -> Any:
    """Laedt eine JSON-Datei mit umfassendem Schutz gegen korrupte Inhalte.

    - Datei fehlt -> default (Default {}).
    - JSON nicht parsebar -> Datei vorher zu <pfad>.corrupt sichern,
      dann default. So bleibt der Datenverlust reparabel und fuer den
      Nutzer sichtbar (statt still verschluckt).
    - JSON ist kein dict -> wie korrupt behandeln (Typprüfung gegen #2).
    - strict=True -> wirft ValueError statt default zu liefern. Wird im
      Schreibpfad genutzt (POST /api/sitzungen), damit ein Speichern nie
      alle anderen Profile loescht, weil die Datei gerade unlesbar war.
    """
    if default is None:
        default = {}
    if not os.path.isfile(pfad):
        return default
    try:
        with open(pfad, encoding="utf-8") as f:
            daten = json.load(f)
    except (json.JSONDecodeError, OSError):
        if strict:
            raise ValueError(f"sitzungen.json unlesbar: {pfad}")
        # Datei zu .corrupt-N sichern (Nummerierung vermeidet Ueberschreiben
        # eines bereits existierenden Backups).
        i = 0
        while True:
            korrupt = f"{pfad}.corrupt{'' if i == 0 else f'.{i}'}"
            if not os.path.exists(korrupt):
                break
            i += 1
        try:
            os.replace(pfad, korrupt)
        except OSError:
            pass
        return default
    if not isinstance(daten, dict):
        if strict:
            raise ValueError(f"{pfad} enthaelt kein JSON-Objekt")
        return default
    return daten


def lade_einstellungen(pfad: str = EINSTELLUNGEN) -> dict[str, Any]:
    """UI-Einstellungen, die die mapping.json ueberschreiben."""
    return _lade_json(pfad)


_SCHREIB_LOCK: threading.Lock = threading.Lock()


def _schreibe_json_atomar(pfad: str, daten: Any) -> None:
    """Schreibt JSON atomar (Temp-Datei + os.replace) unter einem prozessweiten Lock.
       Verhindert, dass parallele Anfragen (ThreadingHTTPServer) die Konfig-Dateien
       halb-geschrieben/korrupt hinterlassen."""
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with _SCHREIB_LOCK:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(pfad), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(daten, f, ensure_ascii=False, indent=1)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, pfad)  # atomar
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise


def speichere_einstellungen(daten: Any, pfad: str = EINSTELLUNGEN) -> None:
    _schreibe_json_atomar(pfad, daten)


def lade_konfig(pfad: str = KONFIG) -> dict[str, Any]:
    with open(pfad, encoding="utf-8") as f:
        cfg: dict[str, Any] = json.load(f)
    _deep_merge(cfg, lade_einstellungen())  # UI-Einstellungen ueberschreiben
    return cfg


def lade_churchtools(pfad: str = CHURCHTOOLS) -> dict[str, Any]:
    cfg: dict[str, Any] = {"base_url": "https://jgdresden.church.tools",
                            "gruppe": "Lobpreis", "token": "",
                            "markier_dienst": "", "ssl_verify": False}
    for pf in (pfad, CHURCHTOOLS_ALT):
        if os.path.isfile(pf):
            with open(pf, encoding="utf-8") as f:
                cfg.update(json.load(f))
            break
    if isinstance(cfg.get("token"), str):
        cfg["token"] = cfg["token"].strip()
    return cfg


def speichere_churchtools(daten: Any, pfad: str = CHURCHTOOLS) -> None:
    _schreibe_json_atomar(pfad, daten)


def lade_spitznamen(pfad: str = SPITZNAMEN) -> dict[str, str]:
    return _lade_json(pfad)


def speichere_spitznamen(daten: Any, pfad: str = SPITZNAMEN) -> None:
    _schreibe_json_atomar(pfad, daten)


def lade_solo_personen(pfad: str = SOLO_PERSONEN,
                       event_key: str | None = None) -> dict[str, str]:
    """Person -> Solo-Instrument (z.B. {'Carla Weber': 'Bratsche'}).

       Format: { name: instrument, ..., "@events": { event_key: { name: instr } } }
       Bei Angabe von event_key werden die Event-spezifischen Einträge
       über die globalen gelegt (Deep-Merge pro Person).
    """
    daten = _lade_json(pfad)
    if not daten:
        return {}
    # Event-spezifische Overrides extrahieren (falls vorhanden)
    events: dict[str, dict[str, str]] = {}
    if isinstance(daten.get("@events"), dict):
        events = daten.pop("@events")
        # Rest sind die globalen Einträge (Flat-Format rückwärtskompatibel)
    ergebnis: dict[str, str] = {str(k): str(v) for k, v in daten.items()
                                if not str(k).startswith("@")}
    if event_key and event_key in events:
        for k, v in events[event_key].items():
            ergebnis[str(k)] = str(v)
    return ergebnis


def speichere_solo_personen(daten: Any, pfad: str = SOLO_PERSONEN) -> None:
    _schreibe_json_atomar(pfad, daten)


def lade_sitzungen(pfad: str = SITZUNGEN, strict: bool = False) -> dict[str, Any]:
    """Gespeicherte Konfigurations-Snapshots: {name: {besetzung_text, setlist, ...}}.
       Persoenliche Daten -- gitignored.
       strict=True wirft bei korrupter Datei (Schreibpfad: kein Datenverlust)."""
    return _lade_json(pfad, strict=strict)

def speichere_sitzungen(daten: Any, pfad: str = SITZUNGEN) -> None:
    _schreibe_json_atomar(pfad, daten)
