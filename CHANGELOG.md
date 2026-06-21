# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier dokumentiert.

## [Unreleased]

### Hinzugefügt
- **Konfigurationen (Profile) speichern:** komplette Snapshots eines Dienstes
  serverseitig speichern und wiederherstellen. Pro Profil werden erfasst:
  - Besetzungstext, Setliste, Dateiname
  - transiente Bühnenpositionen (Feld-Verschiebungen auf der Hauptseite)
  - manuelle Patchlisten-Edits (Kanalnamen, Mic-Labels, SB1/SB2-Slots)
  - Monitor-Bus-Namen
  - Gespeichert in `config/sitzungen.json` (gitignored, atomar geschrieben).
  - **Nicht** im Snapshot: Spitznamen, Solo-Instrumente, Stagebox-Kapazität
    (globale Settings).
  - UI: neue Karte „Konfiguration speichern" mit Dropdown, Speichern/Laden/
    Löschen. Laden wendet Edits über stabile `zeile`/`bus`-Matches an, nicht
    über Array-Index.
  - API: `GET /api/sitzungen`, `POST /api/sitzungen` mit
    `aktion: speichern|loeschen`. Speichern unter existierendem Namen fragt
    vor dem Überschreiben nach.
- **Setliste – Zeilen entfernen:** jede Setlist-Zeile hat einen Löschen-Button
  (✕) im Detail-Modal, der die Zeile in Sidebar und Detailansicht gemeinsam
  entfernt. Hinzufügen und Entfernen nur im Detail-Modal; die kompakte
  Sidebar-Ansicht zeigt weder Löschen- noch Hinzufügen-Buttons.

### Geändert
- Track-Eingänge (`excel.track_aktiv`) werden nun automatisch von der `Multitrack`-
  Rolle in der Besetzung abgeleitet (jede `plane()`-Ausführung), statt als
  persistenter Override in `einstellungen.json` gespeichert zu werden. Der UI-
  Schalter `#trackAktiv` ist ein reiner Status-Indikator (disabled, nicht
  schreibbar).

### Behoben
- **Datenverlust bei korruptem `sitzungen.json`:** der ursprüngliche
  Korrupt-JSON-Schutz (liefer `{}` bei Decode-Fehler) hatte einen
  Datenverlust-Bug eingeführt — beim Speichern diente `{}` als Basis und
  löschte alle bestehenden Profile. Behoben durch `_lade_json` mit
  `strict`-Parameter: der Schreibpfad (`POST /api/sitzungen`) wirft bei
  korrupter Datei `ValueError` und bricht ab, bevor gespeichert wird.
  Der Lese-Pfad sichert die korrupte Datei zu `.corrupt-N` (nummeriert)
  und liefert `{}` — der Nutzer kann die Datei reparieren.
- **Korrupt-JSON-Schutz für alle Config-Lader:** `_lade_json` als
  gemeinsamer Helper für `lade_einstellungen`, `lade_spitznamen`,
  `lade_solo_personen`, `lade_sitzungen`. Prüft auch auf valides
  Nicht-Objekt-JSON (`[]`, `42`) und behandelt es wie korrupt.
- **Veraltete Tabellen nach fehlgeschlagenem Profil-Laden:** `ladeSitzung`
  leert nun Patchliste, Stageboxen und Outputs, wenn `erzeugen()` scheitert
  — kein Arbeiten mehr auf veralteten Tabellen eines anderen Profils.