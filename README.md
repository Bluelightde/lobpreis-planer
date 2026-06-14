# Lobpreis-Planer

Erzeugt aus einer Band-Besetzung automatisch:

1. eine **Excalidraw-Bühnenskizze** mit den Namen an den richtigen Plätzen
2. einen ausgefüllten **X32-Belegungsplan** (`.xlsx`), **abgeleitet aus der Skizze**:
   - **SB1/SB2-Nummern**: jedes vorhandene Instrument bekommt je nach Position
     (links/rechts der Bühnenmitte) eine Nummer in SB1 (Spalte F) oder SB2 (G);
     pro Stagebox wird lückenlos durchnummeriert. **Fehlende Instrumente** (nicht
     in der Skizze) werden geleert.
   - **Sänger-Vornamen** kommen statt „Voc1…Voc5" in **Spalte C**;
     ihre Stagebox-Seite richtet sich nach der X-Position (links→SB1, rechts→SB2).
   - **Monitor-Outputs (Spalte J)** nach Skizzen-Seite: **alle** Personen links
     der Bühnenmitte → **J5–J9**, rechts → **J13–J18**.
   - Mikrofonierung, Routing, Checkliste usw. bleiben wie in der Vorlage.
3. eine angepasste **X32-Szene** (`.scn`), abgeleitet aus Skizze + Excel:
   - **Vox1–4** → Sängernamen (Vorname/Spitzname).
   - **Kanal-Source** je Kanal aus Excel-**Spalte D** (die `A`-Nummer; ergibt sich
     aus SB1/SB2 = Skizzen-Seite): SB1 → `A<n>`, SB2 → `A<n+16>` → Scene-Source `n`.
   - **Bus-Namen** aus den Monitoren: Spalte **J** (Name) + **K** (`Mix N`) →
     Scene-Bus `N`.
   - Alles andere (Icons, Farben, EQ, Mikrofon-/Drum-Namen, FX-Busse) bleibt wie
     in der Vorlage `vorlagen/Standard.scn`.
   - **Kanäle ohne Eingang** (abwesendes Instrument oder „aus") → Scene-Source **0 (aus)**.
   - Konfig: `scene.voc_kanaele`, `scene.kanal_zu_excelzeile`, `excel.monitor.*_bus`.

> **Standardmäßig aus:** `excel.aus_zeilen` (z. B. Track + Track Klick) bekommen
> keinen Eingang/SB-Platz und sind in der Szene auf Source 0. Weitere Kanäle
> lassen sich dort ergänzen.

### Auto-Balance der Stageboxen
Eine Stagebox hat **16 Eingänge**. Würde durch die Skizzen-Seiten eine Box mehr
als 16 bekommen, **verteilt das Programm automatisch um**: Kanäle, deren Person
am nächsten zur Bühnenmitte steht, wandern zur freien Box (Drums ganz außen
bleiben zusammen). **Jede Umverteilung wird angezeigt** (CLI „⚖ Balance-Anpassung",
UI-Hinweis), z. B. „Voc4: 1 Kanal SB2→SB1". Passt es auch danach nicht (insgesamt
> 32 Eingänge), wird ein echter Engpass gemeldet. Konfig: `excel.stagebox_kapazitaet`.

Das Programm ist **rollenbasiert**: Es kennt keine festen Namen, sondern ordnet
jede Person über ihre Rolle (Bass, Drums, A-Git …) dem richtigen Platz zu. Es
funktioniert daher mit **jeder beliebigen Besetzung**.

## Bedienung per Browser-Oberfläche (empfohlen)

### Ein-Klick-Start (Desktop-Symbol, ohne Terminal)

Für den täglichen Gebrauch **einmalig** den passenden Starter installieren —
danach genügt ein **Doppelklick** aufs „Lobpreis-Planer"-Symbol: der Server
startet und der Browser öffnet sich automatisch. Schließt man den Tab, beendet
sich der Server nach wenigen Sekunden von selbst. Ein zweiter Klick startet
nichts doppelt, sondern öffnet nur den Browser zur laufenden Instanz.

- **Linux:** `./installiere_starter.sh` — legt einen Eintrag im
  Anwendungsmenü **und** ein Desktop-Symbol an.
- **Windows:** `installiere_starter.cmd` doppelklicken — legt Verknüpfungen
  (mit Icon) auf dem Desktop und im Startmenü an. Voraussetzung: Python 3 von
  [python.org](https://www.python.org), beim Setup **„Add Python to PATH"**
  aktivieren.
- **macOS:** `installiere_starter_mac.command` doppelklicken — baut
  `~/Applications/Lobpreis-Planer.app` (mit Icon); danach über
  Launchpad/Spotlight oder per Doppelklick startbar.

Alle Symbole tragen das Fader-Icon (`web/favicon.svg`, als `.ico`/`.icns`
beigelegt).

Alternativ ohne Installation direkt starten (öffnet ebenfalls den Browser):

- **Linux/macOS:** `./start.sh`
- **Windows:** `start.bat` doppelklicken

Oder klassisch (alle Plattformen):

```bash
python3 ui.py
```

Dann im Browser **http://127.0.0.1:8765** öffnen:

1. Besetzung einfügen
2. Dateinamen wählen, **Erzeugen** klicken
3. Bühnen-Vorschau + Zuordnung ansehen
4. **Skizze (.excalidraw)**, **Belegungsplan (.xlsx)** und **X32-Szene (.scn)** herunterladen
5. In der Patchlisten-Tabelle lassen sich **alle Felder** direkt bearbeiten:
   **Kanalnamen, Mikro-Bezeichnungen und Stagebox-Slots (SB1/SB2).**
   Die Downloads (Excel + Szene) werden automatisch aktualisiert.
   Leere Zeilen erscheinen ausgegraut — sie entsprechen den Lücken
   in der Excel-Vorlage. Mit **Pfeiltasten** (←→↑↓) springst du
   schnell durch die Tabelle, mit **↺** setzt du alles zurück.

Im Netzwerk teilen (anderes Gerät im selben WLAN):

```bash
python3 ui.py --host 0.0.0.0 --port 8765
```

Direktlink, der eine gespeicherte Besetzung sofort erzeugt:
`http://127.0.0.1:8765/?auto=besetzung_5`

## Bedienung per Kommandozeile

```bash
python3 lobpreis_planer.py besetzungen/DD1.txt
python3 lobpreis_planer.py besetzungen/DD1.txt --titel "Dresden 1 (Vormittag)"
```

Voraussetzung: nur Python 3 (Standardbibliothek, keine Zusatzpakete).

Die Ausgaben landen in `ausgabe/`:
- `<Kürzel>_Skizze.excalidraw` – in [excalidraw.com](https://excalidraw.com) öffnen
- `<Kürzel>_Belegungsplan.xlsx`

## Eingabeformat (`besetzungen/*.txt`)

Eine Zeile pro Rolle, Format `<Rolle> <Kürzel>: <Name>`:

```
Bass DD1: Bert Schmidt
Drums DD1: Felix Müller
Synth DD1: ?
Gesang DD1 1: Emma Meier
Gesang DD1 2: Greta Wagner
```

- Das **Kürzel** (z. B. `DD1` = Dresden 1) wird automatisch erkannt und für den
  Dateinamen verwendet.
- `?` (oder leer / `-`) bedeutet **unbesetzt** – die Rolle wird übersprungen.
- Mehrere Rollen einer Person werden zusammengefasst (eine Box pro Person).

## Layout-Regeln (Skizze)

- **Nur Vornamen** in Skizze und Excel (oder Spitzname, siehe unten).
- **Erste Reihe (vorne, Saalseite):** alle, die singen – auch singende
  Instrumentalisten. Der **Lobpreisleiter steht immer ganz links** (ohne
  „Leitung"-Beschriftung). **Reine Sänger stehen in der Mitte**, Sänger mit
  zusätzlichem Instrument an den **Rändern**. Die Reihe wird dynamisch über die
  Bühnenbreite verteilt (kein Überlappen/Überstand, auch bei 5 Personen).
- **Hintere Reihe (Instrumente):** Drums und Bass bleiben immer hinten;
  E-Git/A-Git/Piano/Synth nur hinten, wenn die Person **nicht** singt.
  Die **A-Git** steht (nicht singend) **unter den Drums**.
- **Solo-Platz (neben SB1):** Solo/Geige **ohne** Gesang.
- **MD:** Ist jemand MD, erscheint ein **Kreis mit „MD" neben** dieser Person
  (nicht im Feld-Text); der statische MD-Kreis der Vorlage entfällt.
- „Gesang" wird als **„Voc"** angezeigt.

## Spitznamen

Im UI (Bereich **Spitznamen**) lassen sich pro Person Spitznamen hinterlegen
(eine Zeile `Voller Name = Spitzname`). Sie werden **dauerhaft** in
`config/spitznamen.json` gespeichert und in **Skizze und Excel** statt des
Vornamens verwendet.

## ChurchTools-Anbindung

Statt die Besetzung manuell einzufügen, kann sie direkt aus der ChurchTools-
Dienstplanung geladen werden (Dienstgruppe **„Lobpreis"**). Da die Dienste dort
bereits „Lobpreisleitung DD1", „Gesang DD1 1" usw. heißen, entspricht das exakt
dem Eingabeformat – es ist **kein Mapping** nötig.

**Einrichtung:** Im UI unter *Aus ChurchTools laden → ChurchTools-Token einstellen*
den persönlichen **Login-Token** eintragen (ChurchTools → eigenes Profil →
„Berechtigungen"). Gespeichert in `config/config.json` (per `.gitignore`
ausgenommen). Instanz/Gruppe stehen ebenfalls dort.

**Nutzung:** Datum wählen → *Termine laden* → Termin auswählen → *Besetzung laden*
→ *Erzeugen*. Der manuelle Weg (Text einfügen) bleibt als Fallback.

## Spezial: Solo-Instrument je Person

„Solo" bedeutet standardmäßig **Geige**. Im UI (Bereich **Spezial:
Solo-Instrument je Person**) lassen sich Abweichungen hinterlegen (eine Zeile
`Voller Name = Instrument`, z. B. `Carla Weber = Bratsche`). Gespeichert
in `config/solo_personen.json`, wirkt in **Skizze** (Feld-Beschriftung) und
**Excel** (Geige- bzw. Bratsche-Kanal).

## Anpassen: `config/mapping.json`

Das ist der **anpassbare Vorschlag**. Hier wird festgelegt, ohne den Code zu
ändern:

- **`buehne.backline`** – feste Positionen (x/y/w/h) der hinteren Instrumente.
  `immer: true` = bleibt hinten, auch wenn die Person singt (Drums/Bass).
- **`buehne.solo_platz`** – Position für Solo/Geige ohne Gesang (neben SB1).
- **`buehne.vorne`** – erste Reihe: `y`, Box-Maße, `rand`, `luecke` (Abstand).
- **`buehne.leiter_rolle`** – welche Rolle „ganz links" steht.
- **`label_ausblenden`** – Rollen, die nicht ins Feld-Label kommen (z. B. Leitung).
- **`excel.instrumente`** – welche Rolle welche Excel-Zeilen (Kanäle) belegt;
  daraus werden SB1/SB2-Nummern (Spalten F/G) berechnet.
- **`excel.voc`** – Zeilen der Voc-Eingänge (Spalte C) und der Monitor-Outputs (J).
- **`excel.technik`** – immer vorhandene Kanäle (Track, Saal, MD …) und ihre Seite.
- **`excel.alt_namen_leeren`** – Zellen mit alten Beispiel-Namen, die geleert werden.
- **`rollen_kurz`** – Kurzbezeichnungen für die Skizze (z. B. Gesang → Voc).

> ⚠️ **Bitte prüfen:** Die SB1/SB2-Zuordnung und die Monitor-Zellen sind ein
> Vorschlag (aus Skizze + Standard-Vorlage). Gleicht sie mit eurem echten
> X32-Routing ab. Solisten ohne Gesang und ein 5.+ Sänger bekommen aktuell
> keinen eigenen Kanal (nur Voc1–4) – das meldet der Bericht/das UI.

## Struktur

```
lobpreis-planer/
├─ ui.py                     # Browser-Oberfläche (lokaler Webserver) + JSON-API
├─ lobpreis_planer.py        # Kernlogik + Kommandozeile
├─ churchtools.py            # ChurchTools-Anbindung
├─ web/                      # Frontend: index.html, style.css, app.js
├─ config/mapping.json       # anpassbare Rollen-/Positions-Zuordnung
├─ vorlagen/                 # Skizze_default.excalidraw, X32-Belegungsplan_Standard.xlsx, *.scn
├─ besetzungen/              # Eingabe-Dateien (eine pro Gottesdienst)
├─ tests/                    # Golden-File-Tests (python3 tests/test_plane.py)
└─ ausgabe/                  # erzeugte Skizzen + Belegungspläne (Kommandozeile)
```

## Annahmen & Anpassung an ein anderes Setup

Die **Besetzungs-/Layout-Logik ist allgemein** (jede Band, jede Bühne über Koordinaten in `mapping.json`). Das **Routing in Excel/Szene ist auf ein konkretes Setup zugeschnitten**:

- **Behringer X32** mit **zwei 16-Eingang-Stageboxen** (SB1/SB2 = 32 Eingänge gesamt).
- Feste Vorlagen in `vorlagen/` und feste Zeilen↔Kanal-Zuordnungen in `mapping.json`
  (`excel.instrumente`, `excel.voc`, `excel.sb_spalten`, `excel.monitor`, `scene.kanal_zu_excelzeile`).

**Für ein anderes Pult / andere Stageboxen / ein anderes Patch-Sheet** sind anzupassen:

1. **Vorlagen** in `vorlagen/` durch eure ersetzen (Excel-Belegungsplan, ggf. `.scn`-Szene, Skizze).
2. In `mapping.json` die **Element-IDs der Skizze** (`buehne.buehne_rect_id`, `box_stil`, `entfernen_rect_ids`, `kreise`) und die **Excel-Zeilen/Spalten** (`excel.*`, `scene.*`) auf die neue Vorlage abgleichen.
3. `excel.stagebox_kapazitaet` und die SB-Spalten anpassen, falls nicht 2×16.

Beim Start prüft ein **Selbstcheck**, ob alle erwarteten Element-IDs/Zellen existieren, und bricht sonst mit klarer Meldung ab (statt still falsch zu rendern).

## Zugriffsschutz & Track-Eingänge

- **Zugriffsschutz:** Im Netzwerk (`--host 0.0.0.0`) sollte ein Passwort gesetzt werden:
  `python3 ui.py --host 0.0.0.0 --password <PW>` (oder Umgebungsvariable `LP_PASSWORD`).
  Ohne Passwort warnt der Server beim Start.
- **Track + Track (Klick):** Im UI per Schalter zuschaltbare Playback-Eingänge. Beide bleiben
  zusammen und werden auf die Stagebox mit mehr freiem Platz gelegt. Standard: aus.
- Eine **Kapazitäts-Anzeige** im Ergebnis meldet, ob das Setting noch aufs Pult passt
  (grün) oder warnt (gelb) bei zu vielen Sängern, Monitor-Überlauf oder Stagebox-Engpass.

## Mehrere Besetzungen

Einfach mehrere Dateien in `besetzungen/` ablegen und nacheinander aufrufen:

```bash
for f in besetzungen/*.txt; do python3 lobpreis_planer.py "$f"; done
```

Die mitgelieferten `besetzungen/DD1.txt` und `besetzungen/besetzung_1`…`besetzung_10`
sind **frei erfundene Beispiel-Eingaben** zum Ausprobieren — keine echten Personen.
`DD1.txt` ist das kanonische Beispiel (auch in Tests und CLI-Aufrufen).

## Lizenz

MIT — siehe [LICENSE](LICENSE). Beispiel-Besetzungen und Spitznamen im Repo sind
frei erfundene Platzhalter; echte personenbezogene Daten gehören in die
gitignorierten Dateien (`config/spitznamen.json`, `config/solo_personen.json`).
