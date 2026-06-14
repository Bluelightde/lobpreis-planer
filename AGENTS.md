# Repository Guidelines

> **An AI assistant works on this codebase by editing one of three layers.** Pick
> the right one and follow its rules — the rest of the document is detail.

---

## 1. Project Overview

**Lobpreis-Planer** turns a worship-team "Besetzung" (lineup) into three
co-derived artefacts for a Behringer X32 mixer:

1. an **Excalidraw stage sketch** (`.excalidraw`) — names at the right places,
2. a filled **X32 patch sheet** (`.xlsx`),
3. an adapted **X32 scene** (`.scn`).

Placement is **role-based** (Bass, Drums, A-Git, Gesang, …) — no hard-coded
people, so any lineup works. The same `plane()` pipeline powers the CLI and
the local web UI; both end up in `ausgabe/` or get downloaded from the browser.

Two entry points:

- `python3 ui.py` → local web server on `http://127.0.0.1:8765` (recommended)
- `python3 lobpreis_planer.py besetzungen/<name>.txt` → CLI, writes to `ausgabe/`

---

## 2. Architecture & Data Flow

**One pipeline, two entry points.** `plane()` in `lobpreis_planer.py` is the
high-level orchestrator called by both CLI and UI. Order is fixed and
load-bearing:

```
Text ─► parse_besetzung_text        → eintraege, kuerzel
     ─► personen_aus_eintraegen     → personen[]
     ─► zuordnen                    → Zonen-Layout  {vorne, hinten, solo}
     ─► erzeuge_skizze_doc          → .excalidraw-Doc
            └─► berechne_layout     → plan[]  ◄── EINZIGE QUELLE DER WAHRHEIT
     ─► erzeuge_excel_bytes         → .xlsx     (aus layout abgeleitet)
     ─► erzeuge_scene               → .scn      (aus Excel-Bericht abgeleitet)
     ─► render_svg                  → SVG-Vorschau fürs UI
```

### The single source of truth

`layout` (returned by `berechne_layout` in `lp_layout.py`) is the **only**
source of truth. A person's `x` position relative to the stage midpoint
(`layout["mitte_x"]`) decides everything downstream:

- **left of midpoint** → Stagebox **SB1** (Excel column F) → X32 input A1..A16
- **right of midpoint** → Stagebox **SB2** (column G) → input A(N+1)..A2N (source offset = `excel.stagebox_kapazitaet` N, default 16)
- same side rule drives Monitor-Outputs (column J) and Scene bus names.

When the user drags a box in the UI, the new `{x, y}` lands in
`config/einstellungen.json` under `buehne.positionen` and **wins** over the
computed position (see `lp_layout.py:175` and `:191`). The same `positionen`
map also moves the fixed Stageboxes (keys `SB1`/`SB2`, see `buehne.fixe_elemente`):
rect + bound text + connector lines are translated together — purely cosmetic,
routing still follows person X-positions.

### Auto-Balance (`berechne_excel_werte`)

Each stagebox holds **`excel.stagebox_kapazitaet` inputs** (default 16, UI-editable,
clamped 1..16 — the .xlsx patch sheet has 16 slot rows per box). The capacity also
sets the SB2 source offset (SB1 = A1..AN, SB2 = A(N+1)..A2N). If a side would
exceed N, whole instrument/vocal **groups** closest to the midpoint get moved
to the other box. Drums/Bass (`immer: true` in `buehne.backline`) stay fixed.
Every move is reported in `bericht["balance"]` and surfaced in CLI/UI.

---

## 3. Key Directories

| Path | Purpose |
|---|---|
| `lobpreis_planer.py` | Orchestrator: `plane()`, `pruefe_vorlagen()`, CLI. Re-exports the full public API. |
| `churchtools.py` | ChurchTools REST client + `setliste_text` / `besetzung_text` parsers. |
| `lp_*.py` | Pipeline stages (see § 6). One file per stage, all imported by the orchestrator. |
| `ui.py` | `http.server` web server. JSON API + static file serving from `web/`. |
| `web/` | Vanilla JS frontend (no build). Hot-reloaded by the server. |
| `config/` | All config is data, not code. See § 5. |
| `vorlagen/` | `.excalidraw` + `.xlsx` + `.scn` templates, **cloned** and patched — never edit-in-place. |
| `besetzungen/` | Input `.txt` files, one per service. |
| `ausgabe/` | CLI output (gitignored). |
| `tests/` | `unittest` + golden-file snapshots under `tests/snapshots/`. |
| `werkzeuge/` | Operator tools: `ct_dump.py` (offline JSON fixtures), `setlisten_check.py` (heuristic auditor). |

---

## 4. Runtime / Tooling Preferences

- **Python 3, pure standard library.** No `pip install`, no `pyproject.toml`,
  no `requirements.txt`, no `setup.py`, no `Makefile`, no `tox.ini`. This is a
  conscious design choice — it must run on a fresh Python 3 install.
- **No package manager, no lockfile.** Don't introduce one.
- **No build step for `web/`.** Vanilla ES modules served as static files
  (`<script type="module" src="/app.js">`). No bundler, no `node_modules`.
- **No CI configuration** in the repo. The user runs tests locally.
- **Browser-tested** with Chromium-based browsers. No PWA, no service worker.
- **No external Python services.** `churchtools.py` uses `urllib.request`.

---

## 5. Configuration (`config/`)

All placement/routing rules live in JSON, not in code. **Edit JSON, not
Python**, when behaviour should change without a code change.

| File | Purpose | VCS? |
|---|---|---|
| `config/mapping.json` | Main config: `buehne.*`, `excel.*`, `scene.*`, `rollen_kurz`, `rollen_reihenfolge`, `solo_instrument`. Holds the **fixed Excalidraw element IDs** the pipeline looks up. | ✅ |
| `config/einstellungen.json` | UI overrides: `modus`, dragged positions (`buehne.positionen`, incl. `SB1`/`SB2`), `buehne.dimensionen` (stage size), `excel.track_aktiv`, `excel.stagebox_kapazitaet`. Loaded via **Deep-Merge** over `mapping.json` by `lade_konfig`. | ⚠️ Allowed but ignored (commented-out in `.gitignore`). |
| `config/spitznamen.json` | `Voller Name → Spitzname` (shown in sketch + Excel). **Persoenliche Daten — gitignored**; Format-Vorlage: `config/spitznamen.example.json`. | ❌ |
| `config/solo_personen.json` | `Voller Name → Solo-Instrument` (e.g. `Bratsche`). **Persoenliche Daten — gitignored**; Format-Vorlage: `config/solo_personen.example.json`. | ❌ |
| `config/config.json` | `base_url`, `token`, `gruppe`. **Secret** — gitignored. | ❌ |

**Two ways to read config:**

- `L.lade_konfig()` → merged `mapping.json ⊕ einstellungen.json` (the real config).
- Tests load `L.KONFIG` (`mapping.json`) **only** for determinism — see `tests/test_plane.py:36`.

**Writing config must be atomic.** Always go through the `speichere_*` helpers
in `lp_konfig.py` (they use `_schreibe_json_atomar` under a process-wide lock).
Never write JSON directly.

### Templates (`vorlagen/`)

Three templates are **cloned, then patched** — the original stays intact and
the generator only replaces targeted cells/lines:

- `Skizze_default.excalidraw` — read as JSON, only `box_stil.rect_id_vorlage`
  / `text_id_vorlage` are cloned per person; all other scene elements
  (SB1/SB2, MD, lines) come from the template untouched.
- `X32-Belegungsplan_Standard.xlsx` — only the target worksheet XML is
  rewritten via `ElementTree`; styling, formulas, icons, EQ sheets stay.
- `*.scn` — patched line-by-line with regex (`_scn_set_name`,
  `_scn_set_source`, `_scn_set_bus_name`).

**When you change a template, also update the IDs/cells in `mapping.json`.**
The startup self-check `pruefe_vorlagen()` validates this and aborts with a
clear list on mismatch — don't suppress it, fix the mismatch.

---

## 6. Important Files (entry points & modules)

| File | Key public symbols |
|---|---|
| `lobpreis_planer.py` | `plane()` (orchestrator), `pruefe_vorlagen()` (startup check), `main()` (CLI), `VorlagenFehler` |
| `ui.py` | `Handler.do_GET` / `do_POST` (HTTP routes), `_einstellungen_slice` (form data), `main()` (server bootstrap) |
| `lp_konfig.py` | Path constants, `KUERZEL` regex, `_deep_merge`, `_schreibe_json_atomar`, `lade_*` / `speichere_*` pairs |
| `lp_parsing.py` | `parse_besetzung_text`, `personen_aus_eintraegen` |
| `lp_personen.py` | `anzeige_name`, `label_fuer_person`, `kurz_rolle` |
| `lp_layout.py` | `zuordnen` (zones), `berechne_layout` (**source of truth**) |
| `lp_skizze.py` | `erzeuge_skizze_doc` (clones template, adds per-person boxes) |
| `lp_excel.py` | `berechne_excel_werte` (incl. auto-balance), `erzeuge_excel_bytes` |
| `lp_scene.py` | `erzeuge_scene` (patches `.scn`), `render_svg` (UI preview) |
| `churchtools.py` | `CT` (HTTP client), `termin_liste`, `besetzung_text`, `setliste_text` |
| `werkzeuge/ct_dump.py` | CLI: dump CT events/agendas as local JSON fixtures (offline) |
| `werkzeuge/setlisten_check.py` | CLI: audit recent setlists against heuristics (caches under `.cache/`) |

For a long-form architectural view with Mermaid diagrams, see `ARCHITEKTUR.md`.
For deeper per-symbol index, see `CLAUDE.md` (slightly outdated line numbers —
the line counts drift, the symbol names don't).

---

## 7. Development Commands

```bash
# ---- Run ----
python3 ui.py                                         # Dev server: http://127.0.0.1:8765
python3 ui.py --host 0.0.0.0 --password <pw>          # LAN share + Basic Auth (or env LP_PASSWORD)
python3 lobpreis_planer.py besetzungen/DD1.txt        # CLI → ausgabe/

# ---- Tests (stdlib unittest) ----
python3 tests/test_plane.py                           # Golden-file snapshot tests
UPDATE_SNAPSHOTS=1 python3 tests/test_plane.py        # Refresh snapshots after a deliberate change
python3 tests/test_invariantes.py                     # A-number ranges, ≤16/box, determinism
python3 tests/test_churchtools.py                     # Synthetic agenda fixtures for setliste_text
python3 tests/test_setlisten_check.py                 # Heuristics in werkzeuge/setlisten_check.py
python3 tests/test_ui_e2e.py                          # Spins up ui.py on a free port, hits the API

# ---- JS syntax check (no bundler) ----
node --check web/app.js web/ct.js web/ui.js

# ---- Operator tools (offline analysis) ----
python3 werkzeuge/ct_dump.py                          # Pull CT events/agendas → .cache/dump/
python3 werkzeuge/setlisten_check.py                  # Audit last 12 months, DD1
```

### Hot-reload boundary (important!)

- **Frontend (`web/`)** — server reads from disk on every request. **No server
  restart needed.** Just reload the browser tab.
- **Python (anything else)** — modules are imported once. **Restart the server**
  after every change to `lobpreis_planer.py`, `ui.py`, `churchtools.py`, or any
  `lp_*.py`.
- `start.sh` is the user-facing launcher (server + `xdg-open` the browser).
- A delayed shutdown timer (3s, see `ui.py:_starte_shutdown`) makes "close tab
  → server stops, reload within 3s → server stays" work without races.

### Server shutdown contract

The browser posts to `/api/shutdown` via `navigator.sendBeacon` on
`visibilitychange:hidden` (`web/app.js:7`). Reloading the page resets the
timer. The endpoint sits **before** auth (`ui.py:236`) because `sendBeacon`
cannot send `Authorization` headers.

---

## 8. Code Conventions & Common Patterns

### 8.1 Language and naming

- **All-German identifiers**, comments, UI strings, configuration. Functions
  use `erzeuge_*`, `berechne_*`, `lade_*`, `speichere_*`, `pruefe_*`, `zuordnen`,
  `plane`. New code keeps this style — no mixed-language function names.
- Umlauts and `ß` are spelled out in source comments (`ü → ue`, `ä → ae`, etc.)
  to keep shells/terminals happy. They are used as-is in user-facing strings.
- Type hints on every public function. Use `dict[str, Any]`, `list[...]`, `tuple[...]`
  — stdlib generics, not `typing.Dict`.
- Module docstring at the top of every `lp_*.py`, in German, summarising the
  stage and its key concepts.

### 8.2 Pipeline discipline

- `plane()` is the **only** high-level entry. CLI and UI call it. Don't bypass
  it to call `erzeuge_excel_bytes` directly — you'll skip `render_svg` and
  miss the report.
- **Don't introduce a second source of truth.** If you find yourself computing
  stage-side from anything other than the X-position in `layout["plan"]`, stop.
- New pipeline stages: add a new `lp_<stage>.py`, re-export the public symbols
  in `lobpreis_planer.py`, and add a call inside `plane()`.

### 8.3 Errors and exceptions

- Module-level error classes per concern: `VorlagenFehler` (templates),
  `SceneFehler` (`.scn` patching failed — usually means the template format
  changed), `ChurchToolsFehler` + subclasses (`ChurchToolsAuthFehler`,
  `ChurchToolsNetzwerkFehler`, `ChurchToolsServerFehler`,
  `ChurchToolsNichtGefunden`).
- CLI catches `VorlagenFehler` → `SystemExit(str(e))` (so the user sees the
  multi-line list). UI catches everything in `_fehler` (`ui.py:114`) →
  JSON `{"ok": false, "error": "<Type>: <msg>"}` + full traceback in `lobpreis.log`.
- Never silently swallow errors. The `werkzeuge/setlisten_check.py` rule:
  "missed Parsing-Branch → regresses silently" is the canonical bug shape here.

### 8.4 Concurrency & state

- The UI server is `ThreadingHTTPServer`. `ui.py` has exactly one piece of
  cross-request mutable state: the shutdown `threading.Timer` (`_SHUTDOWN_TIMER`).
  All access goes through `_starte_shutdown` / `_breche_shutdown_ab`.
- The atomic-write lock (`_SCHREIB_LOCK` in `lp_konfig.py`) is process-wide
  and shared by all `speichere_*` helpers. Use them, don't reinvent.
- The `lp_*` modules are pure-Python and **not** thread-safe at module level
  (no `threading.Lock` around parsing). They're called from one request thread
  at a time per server, so this is fine — but don't add module-level
  caches that would race.

### 8.5 Configuration access pattern

- Always accept a `cfg` / `spitznamen` / `solo_personen` argument; never
  reach into module globals from inside pipeline code. This is what makes
  tests deterministic (`tests/test_plane.py` builds its own deep-copied cfg).
- `lade_konfig()` is the **only** entry that does the `mapping.json ⊕
  einstellungen.json` deep merge. Everything else reads raw.

### 8.6 Templates are immutable

- `vorlagen/*` files must not be edited by the program. The flow is always:
  **load template → modify a copy in memory → write output to `ausgabe/`.**
- The Excalidraw doc is read as JSON, deep-copied per person box via
  `copy.deepcopy` (`lp_skizze._mache_box`). Keep that.
- The `.xlsx` is read as a `zipfile`, only the target worksheet XML is
  rewritten, the rest is streamed through. Keep that.

### 8.7 Frontend conventions (`web/`)

- ES modules, no transpilation, no TypeScript. `index.html` loads
  `<script type="module" src="/app.js">`.
- Three files: `app.js` (bootstrap + deep-link `?auto=`), `ui.js`
  (generation, rules, drag&drop, downloads), `ct.js` (calendar, token,
  caching). Modules export functions called by `app.js`.
- State is plain JS: `LETZTES` / `REGELN` in `ui.js`, `kal` / `monatsCache`
  in `ct.js`. No framework, no virtual DOM, no reactive runtime.
- Dark mode is applied to `<html>` **before first paint** in an inline
  `<head>` script — never move it to `<body>` (it would flash).
- Theme persistence: `localStorage['lp-theme']`, overridable via
  `?theme=dark` / `?theme=light` query string.
- The termin popover is appended to `<body>` on load (`ct.js:271`) — the
  stage card uses `transform: translateY` on hover, which would otherwise
  break `position: fixed` for the popover. Don't undo that move.
- CT event cache: in-memory + `localStorage` with 12h TTL (`CACHE_TTL_MS`).
  Clear on token change (`cacheLeeren`).

### 8.8 ChurchTools parsing (`churchtools.py`)

- `_STIMME_PREFIX` distinguishes "Lead: David" (voice) from "Gesang einsetzen"
  (prose). The `\b` boundary keeps "Leader" and "Leadinstr" untouched.
- `_INSTRUMENTE` is **whitelist-only** — unknown words never become
  instruments. `_NEG_VOR` ("ohne Drums") suppresses the next match.
- `_instrumente_aus` returns deduplicated, original-case results.
- `setliste_text` returns a string in the same format `besetzungen/*.txt`
  uses — no extra mapping needed downstream. Keep that contract.

### 8.9 Style

- 4-space indent, no tabs, ~100 cols.
- Double-quoted strings.
- One statement per line, but multi-assign via `:` is fine (`x: int = 0`).
- Imports: stdlib first, then local (`from lp_konfig import ...`).
- `noqa: F401` is the standard marker for intentional re-exports in
  `lobpreis_planer.py` — keep them so the public API is visible there.

---

## 9. Testing & QA

### Frameworks

- **`unittest`** only. No `pytest`, no `hypothesis`, no `coverage` plugin.
- Tests are runnable as scripts: each file ends with
  `if __name__ == "__main__": unittest.main(verbosity=2)`.
- Run with `python3 tests/<file>.py` — no test discovery, no markers.

### Layers

| File | Style | What it covers |
|---|---|---|
| `tests/test_plane.py` | Golden-file snapshots (`tests/snapshots/*.json`) of the **deterministic** parts of `plane()`: `kuerzel, vorne, hinten, solo, excel, scene`. | The 10 named scenarios in `FAELLE` (line 50): `dd1_standard`, `egit_ausweichen_solo`, `gitarre_neben_synth`, `kein_synth`, `fuenf_saenger`, `sechs_saenger_warnung`, `track_aktiv`, `zwei_solisten`, `bratsche`, `monitor_ueberlauf`. Plus artifact tests that re-read the generated `.xlsx`/`.scn` and snapshot the touched cells. |
| `tests/test_invariantes.py` | Property-based assertions across many inputs. | A-number range (1..16 for SB1, 17..32 for SB2), no duplicates within a box, ≤16/box after auto-balance, `stagebox1/2` mirrors `inputs`, `fehlend == []`, empty inputs don't crash, scene produced only when template exists. |
| `tests/test_churchtools.py` | Synthetic agenda fixtures via `FakeCT`. | `setliste_text` covers: `responsible` as `str/dict.text/dict.persons/list`, vocal-prefix variants (incl. `Leadvoc`), `_instrumente_aus` dedup, `_NEG_VOR` ("ohne Drums"), remark detection, title fallback, deduplication, separator handling. **No real network.** |
| `tests/test_setlisten_check.py` | Direct unit tests of `_pruefe_zeile` / `_letzte_klammer` / `_STOPWORTE`. | Heuristics: doppelte Trennzeichen, nicht entfernte Stimm-Praefixe, Stoppwörter (Alle/Chorus/Intro), Instrument-als-Stimme, `Voc:`-in-Bemerkung, `lead:`-Mehrfachprobleme, `Vox:`-Abkürzung. |
| `tests/test_ui_e2e.py` | Spawns `ui.py` on a free port in-process, hits the API via `http.client`. | Static file serving, `/api/erzeugen` with `DD1.txt`, with arbitrary text, with empty text, 404 path, `/api/einstellungen`, `/api/spitznamen`, `/api/solo_personen`. |

### Key conventions

- **Tests load only `mapping.json`**, never `einstellungen.json` (see
  `tests/test_plane.py:36`). Determinism beats coverage.
- **Snapshot updates are explicit**: `UPDATE_SNAPSHOTS=1 python3 tests/test_plane.py`.
  Use this only after you've understood the diff and decided it's correct.
- **`maxDiff = None`** in golden-file test classes — show the whole diff, don't
  truncate.
- The artifact tests re-open the generated `.xlsx`/`scene_text` and snapshot
  the **touched cells/lines**, not the whole file. This catches broken XML
  writers without checking in megabytes of fixtures.
- `test_ui_e2e.py` is **self-contained**: it starts the server itself. Don't
  require a separately-running `ui.py` for CI/local runs.

### Coverage expectations

There is no enforced coverage target. The bar is: **every code path that
affects what ends up in `ausgabe/` (sketch, xlsx, scn) or in the
JSON response of `/api/erzeugen` is covered by a test in
`tests/test_plane.py` or `tests/test_invariantes.py`.** Parsing
branch coverage is owned by `test_churchtools.py` and
`test_setlisten_check.py`. The HTTP surface is owned by `test_ui_e2e.py`.

---

## 10. Things an AI assistant should NOT do

- Do **not** add a `requirements.txt`, `pyproject.toml`, or `pip install` of
  any kind. Stdlib only.
- Do **not** add a JS bundler, `package.json`, or build step to `web/`.
- Do **not** edit `vorlagen/*` programmatically. The program reads them and
  writes outputs to `ausgabe/`. Keep the separation.
- Do **not** add a second source of truth for stage-side assignment. It must
  come from `cx` in `layout["plan"]` (with the 1px tolerance in
  `lp_excel.seite`).
- Do **not** suppress `pruefe_vorlagen()` errors. They mean a template /
  config got out of sync — fix the mismatch, don't silence the check.
- Do **not** write JSON config files directly. Use the `speichere_*` helpers
  in `lp_konfig.py` (atomic write + lock).
- Do **not** introduce English function/variable names. Keep the German style.
- Do **not** ship a snapshot update without reading the diff. The snapshots
  in `tests/snapshots/` are the spec.
- Do **not** commit `config/config.json`, anything in `ausgabe/`, or
  `*.png`. All three are gitignored for a reason.
- Do **not** mix the `positionen` keys: `vorne_<i>` for the vorne row,
  `Solo` for the solo stack, the bare `"vorne"` key as a column-wide override,
  and `SB1`/`SB2` for the fixed Stageboxes. `lp_layout.berechne_layout` resolves
  the person keys (vorne/Solo) in that order; `lp_skizze` applies the SB keys —
  change one, audit the others.
