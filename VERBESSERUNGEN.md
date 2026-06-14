# Verbesserungen / Backlog

Punkte aus dem Veroeffentlichungs-Review (2026-06-14). Festgehalten, damit nichts
verloren geht. Umgesetzt sind 1-3 und 6-8; 4-5 bleiben offen.

## Umgesetzt

- [x] **1. `config/config.example.json`** — Schema-Vorlage fuer das ChurchTools-Secret
  (`base_url`, `gruppe`, `token`, `markier_dienst`, `ssl_verify`), konsistent mit
  `spitznamen.example.json` / `solo_personen.example.json`. Hilft CLI-/Manuell-Nutzern,
  die nicht den UI-Weg gehen.
- [x] **2. `.gitattributes`** — plattformuebergreifende EOL-Normalisierung (`*.sh`/`*.command`
  → LF, `*.bat`/`*.cmd` → CRLF) und Binaer-Markierung der Vorlagen, damit Windows-Clones
  `start.sh` nicht mit CRLF zerschiessen und Binaerdiffs nicht rauschen.
- [x] **3. GitHub Actions CI** (`.github/workflows/tests.yml`) — laeuft `python3 tests/*.py`
  + `node --check web/*.js` bei Push/PR. Null Installation (stdlib + node). AGENTS.md §4
  ("No CI") entsprechend angeglichen.
- [x] **6. `config/einstellungen.json` untracked** — lokale UI-Overrides gehoeren nicht ins
  oeffentliche Repo. `git rm --cached` + `.gitignore`-Eintrag aktiviert. `lade_einstellungen`
  liefert bei fehlender Datei `{}` → fuer frische Clones unkritisch.
- [x] **7. `CLAUDE.md` Zeilennummern entfernt** — die Zeilen-Referenzen drifteten (laut
  eigener Notiz). Symbol-Index behaelt Symbolnamen + Zweck, ohne wandernde Nummern.
- [x] **8. `besetzungen/`-Hinweis** — kurze Notiz in der README, dass die Beispiel-Eingaben
  frei erfundene Platzhalter sind (keine echten Personen).

## Offen

- [ ] **4. `ui.py` `except Exception: pass` (CT-Status-Check)** — schluckt Netzwerk-/SSL-Fehler
  ohne Log (genau die "still regressierende" Fehlerform aus AGENTS.md §8.3). `ChurchToolsAuthFehler`
  wird sauber behandelt; der Rest sollte mindestens ein `log.warning(...)` bekommen.
- [ ] **5. CT-HTTP-Client-Fehlerpfade testen** — `test_churchtools.py` deckt via `FakeCT` nur
  das Parsing ab. Das Mapping echter `urllib`-Fehler auf `ChurchToolsNetzwerkFehler` /
  `ChurchToolsServerFehler` / `ChurchToolsAuthFehler` ist ungetestet.

## Optional

- Kurze `CONTRIBUTING.md` (Tests laufen lassen, "stdlib only / keine Deps",
  Snapshot-Update-Flow) — macht das Test-Wissen aus AGENTS.md beitragstauglich.
