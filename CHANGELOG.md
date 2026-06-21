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
    `aktion: speichern|loeschen`.
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