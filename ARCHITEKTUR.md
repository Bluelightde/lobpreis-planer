# Architektur-Graph

Automatisch aus dem Code abgeleitete Übersicht (verifiziert gegen `import`-Zeilen,
`ui.py`-Routen, `web/app.js`-`fetch`-Aufrufe und die `plane()`-Pipeline). Die
Diagramme sind [Mermaid](https://mermaid.js.org/) und rendern direkt auf GitHub —
keine zusätzlichen Werkzeuge nötig.

## 1. Module & Abhängigkeiten

Wer importiert/ruft wen, und welche Dateien gelesen/geschrieben werden.

```mermaid
graph TD
    subgraph Extern
        Browser["🌐 Browser"]
        CTAPI["ChurchTools REST-API<br/>(jgdresden.church.tools)"]
    end

    subgraph "Frontend — web/"
        HTML["index.html"]
        CSS["style.css"]
        APP["app.js<br/>(Kalender, Patchliste,<br/>Drag&amp;Drop, Setliste)"]
    end

    subgraph "Server (Python, nur stdlib)"
        UI["ui.py<br/>http.server + JSON-API"]
        L["lobpreis_planer.py<br/>Kernlogik + CLI"]
        CT["churchtools.py<br/>REST über urllib"]
    end

    subgraph "Daten (Dateisystem)"
        KONFIG["config/*.json<br/>mapping, einstellungen,<br/>spitznamen, solo_personen,<br/>churchtools"]
        VORLAGEN["vorlagen/*<br/>.excalidraw / .xlsx / .scn"]
        BES["besetzungen/*.txt"]
        AUSGABE["ausgabe/<br/>(CLI-Ergebnisse)"]
    end

    TESTS["tests/test_plane.py<br/>Golden-File-Snapshots"]

    Browser <-->|HTTP| UI
    UI -->|liefert statisch| HTML
    UI -->|liefert statisch| CSS
    UI -->|liefert statisch| APP
    HTML --> APP
    APP -.->|fetch /api/*| UI

    UI -->|"import L"| L
    UI -->|"import CT"| CT
    TESTS -->|"import L"| L

    CT -->|GET/POST| CTAPI

    L -->|liest| KONFIG
    L -->|klont| VORLAGEN
    L -->|liest| BES
    L -->|schreibt atomar| KONFIG
    L -->|CLI schreibt| AUSGABE
    UI -->|liest/schreibt via L| KONFIG
```

## 2. HTTP-API (Frontend ↔ ui.py)

Alle von `web/app.js` aufgerufenen Endpunkte und ihre serverseitige Anbindung.

```mermaid
graph LR
    APP["web/app.js"]

    subgraph "GET"
        G1["/api/ct/status"]
        G2["/api/ct/events"]
        G3["/api/ct/laden"]
        G4["/api/ct/setliste"]
        G5["/api/spitznamen"]
        G6["/api/solo_personen"]
        G7["/api/einstellungen"]
        G8["/api/laden · /api/liste"]
    end

    subgraph "POST"
        P1["/api/erzeugen"]
        P2["/api/ct/token"]
        P3["/api/spitznamen"]
        P4["/api/solo_personen"]
        P5["/api/einstellungen"]
    end

    APP --> G1 & G2 & G3 & G4 & G5 & G6 & G7 & G8
    APP --> P1 & P2 & P3 & P4 & P5

    G2 -->|"CT.termin_liste"| CT["churchtools.py"]
    G3 -->|"CT.besetzung_text"| CT
    G4 -->|"CT.setliste_text"| CT
    G1 -->|"L.lade_churchtools"| L["lobpreis_planer.py"]
    P2 -->|"L.lade/_schreibe_json"| L
    G5 & G6 & G7 -->|"L.lade_*"| L
    P3 & P4 & P5 -->|"L.speichere_* / _schreibe_json"| L
    P1 -->|"L.plane(text, cfg)"| L
```

## 3. Datenfluss in `plane()`

Die zentrale Pipeline (CLI **und** UI rufen dieselbe Funktion). Die
Bühnenskizze (`layout`) ist die **einzige Quelle der Wahrheit**; Excel und
Szene werden daraus abgeleitet.

```mermaid
graph TD
    TEXT["Besetzungs-Text<br/>(besetzungen/*.txt o. ChurchTools)"]
    TEXT --> P1["parse_besetzung_text<br/>→ eintraege, kuerzel"]
    P1 --> P2["personen_aus_eintraegen<br/>→ personen"]
    P2 --> P3["zuordnen<br/>Zonen-Layout: vorne / hinten / solo"]
    P3 --> P4["erzeuge_skizze_doc<br/>(→ berechne_layout)"]
    P4 -->|"layout = QUELLE DER WAHRHEIT"| SKIZZE[".excalidraw-Doc"]
    P4 -->|layout| P5["erzeuge_excel_bytes<br/>(→ berechne_excel_werte,<br/>Auto-Balance SB1/SB2)"]
    P5 -->|excel_bericht| P6["erzeuge_scene<br/>(.scn patchen)"]
    P4 -->|doc| P7["render_svg<br/>(UI-Vorschau)"]

    P5 --> XLSX["X32-Belegungsplan .xlsx"]
    P6 --> SCN["X32-Szene .scn"]
    P7 --> SVG["SVG-Vorschau"]

    KONFIG["config/ (lade_konfig:<br/>mapping ⊕ einstellungen)"] -.->|cfg| P3
    KONFIG -.->|cfg| P4
    KONFIG -.->|cfg| P5
    KONFIG -.->|cfg| P6

    classDef truth fill:#fde68a,stroke:#b45309,color:#000;
    class SKIZZE,P4 truth;
```
