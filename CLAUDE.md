# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Was dieses Projekt tut

Aus einer Band-Besetzung (Worship-Team) erzeugt das Programm automatisch drei aufeinander abgeleitete Artefakte für einen Behringer-X32-Mixer:

1. eine **Excalidraw-Bühnenskizze** (`.excalidraw`) mit Namen an den richtigen Plätzen,
2. einen ausgefüllten **X32-Belegungsplan** (`.xlsx`),
3. eine angepasste **X32-Szene** (`.scn`).

Es ist **rollenbasiert**: keine festen Namen, jede Person wird über ihre Rolle (Bass, Drums, A-Git, Gesang …) platziert. Funktioniert mit jeder Besetzung.

## Kommandos

Reines Python 3 (nur Standardbibliothek, **keine Zusatzpakete**, kein Build-Schritt).

```bash
# Browser-Oberfläche (Standardweg), http://127.0.0.1:8765
python3 ui.py
python3 ui.py --host 0.0.0.0 --port 8765                 # im WLAN erreichbar
python3 ui.py --host 0.0.0.0 --password geheim           # mit Zugriffsschutz (Basic Auth)

# Kommandozeile (schreibt nach ausgabe/)
python3 lobpreis_planer.py besetzungen/DD1.txt
python3 lobpreis_planer.py besetzungen/DD1.txt --titel "Dresden 1"

# Tests (Golden-File-Snapshots der Kernlogik)
python3 tests/test_plane.py                             # Kernlogik (plane)
python3 tests/test_churchtools.py                       # setliste_text-Parsing (synthetische Fixtures)
UPDATE_SNAPSHOTS=1 python3 tests/test_plane.py          # Snapshots nach bewusster Änderung neu schreiben
# Rohdaten als lokale JSON-Fixtures ziehen (offline-Analyse/Tests, nach .cache/dump/)
python3 werkzeuge/ct_dump.py

# Setlisten-Anzeige gegen ChurchTools pruefen (kompakt: meldet nur Auffaelligkeiten,
# cacht Agenden unter .cache/). Statt 50 Setlisten zu dumpen.
python3 werkzeuge/setlisten_check.py                    # letzte 12 Monate, DD1
python3 werkzeuge/setlisten_check.py --monate 24 --all  # alle ausgeben
```

**Wichtig beim Entwickeln:**
- Änderungen an **`lobpreis_planer.py`/`ui.py` (Python)** erfordern einen **Server-Neustart** (Module werden einmal importiert).
- Änderungen am **Frontend (`web/`)** wirken **ohne Neustart** — die Dateien werden pro Anfrage frisch von der Platte ausgeliefert (nur Browser-Reload nötig).
- Nach Änderungen an der Kernlogik **`python3 tests/test_plane.py`**, nach Änderungen am ChurchTools-Parsing **`python3 tests/test_churchtools.py`** laufen lassen. Bei JS-Änderungen `node --check web/app.js`.
- Beim Start läuft ein **Vorlagen-Selbstcheck** (`pruefe_vorlagen`); fehlende Element-IDs/Zellen/Dateien brechen sofort mit klarer Meldung ab.

## Architektur

Drei Module, eine klare Datenfluss-Pipeline:

- **`lobpreis_planer.py`** — Kernlogik **und** CLI. Enthält die gesamte Generierung. Außerdem: `pruefe_vorlagen()` (Selbstcheck) und `_schreibe_json_atomar()` (alle Konfig-Schreibvorgänge laufen atomar unter einem Lock).
- **`ui.py`** — lokaler `http.server`-Webserver. Importiert `lobpreis_planer as L` und `churchtools as CT`, stellt eine kleine JSON-API bereit (`/api/erzeugen`, `/api/ct/*`, `/api/spitznamen`, `/api/einstellungen` …) und **liefert das Frontend aus `web/` aus** (statische Dateien, frisch pro Anfrage). Optionaler Zugriffsschutz via `--password` (Basic Auth).
- **`web/`** — das Frontend: `index.html`, `style.css`, `app.js` (~31 kB JS). Hier sitzt die gesamte UI-Logik (Kalender, Patchliste, Drag&Drop, Setliste, Misch-Modus). **War früher als String `SEITE` in ui.py eingebettet — jetzt ausgelagert.**
- **`churchtools.py`** — Anbindung an die ChurchTools-Dienstplanung (REST über `urllib`). Liefert die Besetzung im selben Textformat, das auch manuell eingegeben wird — daher **kein Mapping nötig**.
- **`tests/`** — Golden-File-Tests (`test_plane.py`) mit Snapshots unter `tests/snapshots/`. Vergleichen das deterministische `plane()`-Ergebnis repräsentativer Besetzungen.

### Zentraler Datenfluss (`plane()` in lobpreis_planer.py)

`plane()` ist der High-Level-Orchestrator, den **sowohl CLI als auch UI** aufrufen. Reihenfolge:

```
Text → parse_besetzung_text → personen_aus_eintraegen → zuordnen (Zonen-Layout)
     → erzeuge_skizze_doc (→ layout)   ← EINZIGE QUELLE DER WAHRHEIT
     → erzeuge_excel_bytes (aus layout abgeleitet)
     → erzeuge_scene (aus Excel-Bericht abgeleitet)
     → render_svg (Vorschau fürs UI)
```

**Das wichtigste Konzept:** Die Bühnenskizze (`layout` aus `berechne_layout`) ist die **einzige Quelle der Wahrheit**. Alles Weitere wird aus den **X-Positionen der Personen relativ zur Bühnenmitte** abgeleitet:
- Person **links** der Mitte → Stagebox **SB1** (Excel-Spalte F), **rechts** → **SB2** (Spalte G).
- Monitor-Outputs (Spalte J) und Szene-Sources (A-Nummern) folgen derselben Seite.
- Wer im UI eine Box **zieht**, ändert deren X-Position → ändert SB-Seite/Routing. Gezogene Positionen werden in `config/einstellungen.json` unter `buehne.positionen` gespeichert und gewinnen gegenüber den berechneten.

### Layout-Zonen (`zuordnen`)

Pro Person genau ein Platz: **vorne** (singt / erste Reihe, Leiter ganz links), **hinten** (Instrumente, Drums/Bass immer hinten), **solo** (Solo/Geige ohne Gesang, neben SB1). Die vordere Reihe wird dynamisch über die Bühnenbreite verteilt; Box-Breite wächst mit dem Label-Inhalt.

### Auto-Balance der Stageboxen

Eine Stagebox hat **16 Eingänge** (`excel.stagebox_kapazitaet`). `berechne_excel_werte` verschiebt automatisch ganze Instrument-/Voc-Gruppen, die der Bühnenmitte am nächsten stehen, auf die freie Box, falls eine Seite > 16 bekäme. Drums/Bass (`immer: true`) bleiben fix. Jede Verschiebung landet im `bericht["balance"]` und wird in CLI/UI angezeigt.

## Konfiguration (`config/`)

Alle Platzierungs- und Zuordnungsregeln stehen **datengetrieben** in JSON — Verhalten ohne Code-Änderung anpassbar:

- **`mapping.json`** — die Hauptkonfiguration (Versionskontrolle). Definiert `buehne.backline` (feste Instrument-Positionen x/y/w/h), `buehne.vorne`, `excel.instrumente` (welche Rolle welche Excel-Zeilen belegt), `excel.voc`, `excel.monitor`, `scene.*`, `rollen_kurz`, `rollen_reihenfolge`. Excalidraw-/Excel-Vorlagen werden über **fixe Element-IDs** angesprochen (`buehne_rect_id`, `entfernen_rect_ids`, `box_stil`). Beim Bearbeiten der Vorlagen müssen diese IDs konsistent bleiben.
- **`einstellungen.json`** — UI-Overrides; werden via `_deep_merge` **über** `mapping.json` gelegt (`lade_konfig`). Enthält Modus, gezogene Positionen, Backline-Anpassungen.
- **`spitznamen.json`** — `Voller Name → Spitzname` (statt Vorname in Skizze + Excel).
- **`solo_personen.json`** — `Voller Name → Solo-Instrument` (Standard „Solo" = Geige).
- **`config.json`** — Token/Instanz/Gruppe. **Per `.gitignore` ausgenommen** (Geheimnis), genau wie `ausgabe/` und `*.png`.

## Vorlagen (`vorlagen/`)

`Skizze_default.excalidraw`, `X32-Belegungsplan_Standard.xlsx`, `Standard.scn`. Die Generierung **klont die Vorlagen und ersetzt nur gezielte Zellen/Elemente** — Styling, Formeln, Icons, EQ etc. bleiben erhalten. Beim Excel werden Zellen über Inline-Strings per `ElementTree` direkt im Worksheet-XML gesetzt (`_set_zelle_inline`); die `.scn` wird zeilenweise per Regex gepatcht (`_scn_set_*`).

## Eingabeformat (`besetzungen/*.txt`)

Eine Zeile pro Rolle, `<Rolle> <Kürzel>: <Name>`:

```
Bass DD1: Bert Schmidt
Gesang DD1 1: Emma Meier
Synth DD1: ?
```

Das **Kürzel** (`DD1` = Großbuchstaben + Zahl, Regex `KUERZEL`) wird automatisch erkannt. `?`/leer/`-` = unbesetzt → übersprungen. Mehrere Rollen einer Person werden zu einer Box zusammengefasst. Mehrfach besetzte Dienste (`Gesang`) müssen durchnummeriert sein (`Gesang DD1 1`, `… 2`), damit das Voc-Mapping greift — `churchtools.py` macht das automatisch.

## Konventionen

- Code, Bezeichner, Kommentare und UI sind **durchgängig deutsch** (`erzeuge_*`, `berechne_*`, `zuordnen`, `bericht`). Beim Erweitern dieser Stil beibehalten.
- Keine externen Abhängigkeiten einführen — nur `stdlib`. Das ist eine bewusste Designentscheidung (läuft überall mit blankem Python 3).

## Symbol-Index (schnelles Springen, statt großer Dateien zu lesen)

Die Kernlogik ist auf mehrere Pipeline-Module verteilt. `lobpreis_planer.py` ist
der Orchestrator und re-exportiert die komplette öffentliche API. Zum Neuziehen:
`search '^def ' lp_*.py lobpreis_planer.py churchtools.py`.
Architektur-Diagramme: siehe `ARCHITEKTUR.md`.

**`lp_konfig.py`** (Konstanten, Deep-Merge, atomares Schreiben, Lader/Speicherer):

| Symbol | Zeile | Zweck |
|---|---|---|
| `BASIS` / `KONFIG` / … / `AUSGABE` | 14–27 | Pfad-Konstanten |
| `M` | 30 | Excel-Namespace |
| `KUERZEL` | 33 | Regex für Dienst-Kürzel (DD1 etc.) |
| `_deep_merge` | 36 | rekursives Dict-Merging |
| `_schreibe_json_atomar` | 61 | atomares JSON-Schreiben unter Lock |
| `lade_konfig` / `lade_einstellungen` | 84 / 45 | Konfig laden (mit Deep-Merge) |
| `lade_churchtools` / `speichere_churchtools` | 90 / 100 | CT-Config |
| `lade_spitznamen` / `speichere_spitznamen` | 104 / 109 | Spitznamen |
| `lade_solo_personen` / `speichere_solo_personen` | 113 / 118 | Solo-Instrumente pro Person |

**`lp_parsing.py`** (Eingabe-Parsing):

| Symbol | Zeile | Zweck |
|---|---|---|
| `parse_besetzung` / `parse_besetzung_text` | 10 / 16 | Besetzungstext → eintraege, kuerzel |
| `personen_aus_eintraegen` | 56 | Eintraege pro Person bündeln |

**`lp_personen.py`** (Namens-Helfer):

| Symbol | Zeile | Zweck |
|---|---|---|
| `vorname` / `anzeige_name` | 7 / 11 | Anzeigename (Spitzname/Vorname) |
| `kurz_rolle` / `label_fuer_person` | 21 / 31 | Rollen-Kurzform / Feld-Label |
| `_singt` | 57 | Prüft ob Person singt |

**`lp_layout.py`** (Zonen-Zuordnung + Box-Positionen):

| Symbol | Zeile | Zweck |
|---|---|---|
| `zuordnen` | 11 | Zonen-Layout vorne/hinten/solo |
| `berechne_layout` | 116 | Box-Positionen (Quelle der Wahrheit) |

**`lp_skizze.py`** (Excalidraw-Generierung):

| Symbol | Zeile | Zweck |
|---|---|---|
| `_mache_box` / `_mache_kreis` | 12 / 45 | Excalidraw-Elemente klonen |
| `erzeuge_skizze_doc` | 65 | Komplettes Excalidraw-Dokument |

**`lp_excel.py`** (Excel-Belegungsplan):

| Symbol | Zeile | Zweck |
|---|---|---|
| `_sheet_datei_fuer_blatt` | 31 | Worksheet-XML im ZIP finden |
| `_fuelle_zelle` / `_set_zelle_inline` | 52 / 66 | Zellen im XML setzen |
| `berechne_excel_werte` | 97 | Excel-Werte + Auto-Balance SB1/SB2 |
| `erzeuge_excel_bytes` | 293 | X32-Belegungsplan .xlsx |

**`lp_scene.py`** (X32-Szene + SVG):

| Symbol | Zeile | Zweck |
|---|---|---|
| `_scn_set_name` / `_scn_set_source` / `_scn_set_bus_name` | 16 / 22 / 28 | .scn-Zeilen patchen |
| `erzeuge_scene` | 34 | X32-Szene .scn |
| `render_svg` | 136 | SVG-Vorschau fürs UI |

**`lobpreis_planer.py`** (Orchestrator, Re-Exports, CLI):

| Symbol | Zeile | Zweck |
|---|---|---|
| `VorlagenFehler` | 37 | Exception für kaputte Vorlagen |
| `pruefe_vorlagen` | 41 | Vorlagen-Selbstcheck beim Start |
| `plane` | 99 | High-Level-Orchestrator (CLI + UI) |
| `main` | 154 | CLI-Einstieg |

**`churchtools.py`** (REST-Anbindung; Regexe `_STIMME_PREFIX` 175, `_INSTRUMENTE` 180, `_NEG_VOR` 188):

| Symbol | Zeile | Zweck |
|---|---|---|
| `CT` (Klasse) | 25 | HTTP-Client; `get`/`events`/`event`/`agenda` |
| `whoami` | 81 | Person-ID des Tokens |
| `termin_liste` | 90 | Termine [von,bis] für Auswahl |
| `besetzung_text` | 140 | Dienste → Besetzungstext |
| `_instrumente_aus` / `_ist_bemerkung` | 191 / 202 | Notiz-Parsing-Helfer |
| `setliste_text` | 214 | Ablaufplan → Setliste (Stimme/Instrument/Bemerkung) |

**`ui.py`** (Webserver): `Handler` 51 (Routen in `do_GET`/`do_POST`; Endpunkte siehe `ARCHITEKTUR.md` §2), `_serve_static` 87, `_einstellungen_slice` 102, `main` 281.

**`web/app.js`** (Frontend): Kalender `renderKalender` 227 / `holeMonat` 157 / `zeigeTag` 197; Setliste `parseSetlisteText` 380 / `slAddRow` 302 / `renderMischModus` 344; Regeln `ladeRegeln` 501 / `speicherePosition` 549; `erzeugen` 574 (ruft `/api/erzeugen`).

**`werkzeuge/`**: `setlisten_check.py` — Setlisten-Anzeige kompakt gegen ChurchTools prüfen; `ct_dump.py` — Rohdaten (Events/Agenden) als lokale JSON-Fixtures ziehen (offline-Analyse/Tests).
