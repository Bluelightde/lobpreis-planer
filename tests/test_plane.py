#!/usr/bin/env python3
"""
Golden-File-Tests fuer den Lobpreis-Planer (nur Standardbibliothek).

Jeder Testfall fuettert eine Besetzung in plane() und vergleicht das deterministische
Ergebnis (Zuordnung + Excel-/Szene-Bericht) mit einem gespeicherten Snapshot unter
tests/snapshots/. So fallen Regressionen in der fummeligen Layout-, Stagebox- und
Routing-Logik sofort auf.

Aufruf:
    python3 -m unittest tests.test_plane            # oder: python3 tests/test_plane.py
    UPDATE_SNAPSHOTS=1 python3 tests/test_plane.py  # Snapshots neu schreiben (nach
                                                    # bewussten Aenderungen)

Wichtig: Die Tests laden NUR config/mapping.json (ohne die persoenliche
einstellungen.json), damit sie unabhaengig von lokalen UI-Einstellungen sind.
"""

import copy
import io
import json
import os
import re
import sys
import unittest
import xml.etree.ElementTree as ET
import zipfile

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASIS)
import lobpreis_planer as L  # noqa: E402

SNAP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshots")
UPDATE = os.environ.get("UPDATE_SNAPSHOTS") == "1"

# Nur das Basis-Mapping laden (ohne UI-Einstellungen) -> deterministisch.
with open(L.KONFIG, encoding="utf-8") as _f:
    BASIS_CFG = json.load(_f)





# (Name, Besetzungs-Text, Optionen) -- Optionen=None => Basis-Mapping, kein Override.
# Optionen-dict: {"solo_personen": {...}} setzt person-spezifische Solo-Instrumente.
FAELLE = [
    ("dd1_standard", """
Lobpreisleitung DD1: Emma Meier
MD DD1: Bert Schmidt
A-Git DD1: Carla Weber
E-Git DD1: David Fischer
Piano DD1: Emma Meier
Synth DD1: ?
Solo DD1: Carla Weber
Bass DD1: Bert Schmidt
Drums DD1: Felix Müller
Gesang DD1 1: Emma Meier
Gesang DD1 2: Greta Wagner
Gesang DD1 3: Carla Weber
Gesang DD1 4: Felix Müller
""", None),

    # E-Git weicht auf freien Geige-Platz aus (Synth da, Solist singt)
    ("egit_ausweichen_solo", """
Synth DD1: Karl
Lobpreisleitung DD1: Emma Meier
A-Git DD1: Carla Weber
E-Git DD1: David Fischer
Solo DD1: Carla Weber
Bass DD1: Bert Schmidt
Drums DD1: Felix Müller
Gesang DD1 1: Emma Meier
Gesang DD1 3: Carla Weber
""", None),

    # Geige-Platz belegt (Solist singt nicht) + Synth -> Gitarren/Piano/Synth
    # werden vertikal unter den Drums gestapelt (rechte Seite -> SB2)
    ("gitarre_neben_synth", """
Gesang DD1 1: Karl
Synth DD1: Bob
Solo DD1: Lena
A-Git DD1: Tim Weiß
E-Git DD1: Quentin Schröder
Piano DD1: Paula Wolf
Bass DD1: Rosa Schwarz
Drums DD1: Karl Schäfer
Gesang DD1 2: Paula Wolf
Gesang DD1 3: Quentin Schröder
Gesang DD1 4: Ute Braun
MD DD1: Rosa Schwarz
Lobpreisleitung DD1: Paula Wolf
Co-Leiter DD1: Quentin Schröder
""", None),

    # Kein Synth -> keine Ausweich-Regel, Gitarren bleiben hinten
    ("kein_synth", """
Lobpreisleitung DD1: Emma
A-Git DD1: Tim
E-Git DD1: Rob
Bass DD1: Bert
Drums DD1: Felix
Gesang DD1 1: Emma
Gesang DD1 2: Greta
""", None),

    # 5 Saenger -> Voc1-5 voll, Auto-Balance der Stageboxen
    ("fuenf_saenger", """
Gesang DD1 1: Tim
Gesang DD1 5: Lisa
Synth DD1: Bob
Solo DD1: Lena
A-Git DD1: Tim Weiß
E-Git DD1: Quentin Schröder
Piano DD1: Paula Wolf
Bass DD1: Rosa Schwarz
Drums DD1: Karl Schäfer
Gesang DD1 2: Paula Wolf
Gesang DD1 3: Quentin Schröder
Gesang DD1 4: Ute Braun
MD DD1: Rosa Schwarz
Lobpreisleitung DD1: Paula Wolf
Co-Leiter DD1: Quentin Schröder
""", None),

    # 6 Saenger -> ueberzaehliger Saenger (kein Voc-Kanal)
    ("sechs_saenger_warnung", """
Lobpreisleitung DD1: Emma
Bass DD1: Bert
Drums DD1: Felix
Gesang DD1 1: Emma
Gesang DD1 2: A
Gesang DD1 3: B
Gesang DD1 4: C
Gesang DD1 5: D
Gesang DD1 6: E
""", None),

    # Track + Track Klick aktiv (Multitrack in der Besetzung) -> 2 zusaetzliche
    ("track_aktiv", """
Gesang DD1 1: Tim
Gesang DD1 5: Lisa
Synth DD1: Bob
Solo DD1: Lena
A-Git DD1: Tim Weiß
E-Git DD1: Quentin Schröder
Piano DD1: Paula Wolf
Bass DD1: Rosa Schwarz
Drums DD1: Karl Schäfer
Gesang DD1 2: Paula Wolf
Gesang DD1 3: Quentin Schröder
Gesang DD1 4: Ute Braun
MD DD1: Rosa Schwarz
Lobpreisleitung DD1: Paula Wolf
Co-Leiter DD1: Quentin Schröder
Multitrack DD1: Ute Braun
""", None),

    # Zwei nicht-singende Solisten (Solo + Geige) -> beide auf den Solo-Platz
    # gestapelt; keine Gitarren-Ausweichregel (Solo-Platz belegt).
    ("zwei_solisten", """
Lobpreisleitung DD1: Emma
Solo DD1: Lena
Geige DD1: Mara
Bass DD1: Bert
Drums DD1: Felix
Gesang DD1 1: Emma
""", None),

    # Person-spezifisches Solo-Instrument: Solist spielt Bratsche statt Geige
    # -> Excel-Zeile 19 (Bratsche) belegt, Zeile 18 (Geige) leer.
    ("bratsche", """
Lobpreisleitung DD1: Emma
Solo DD1: Clara
Bass DD1: Bert
Drums DD1: Felix
Gesang DD1 1: Emma
Gesang DD1 2: Mara
""", {"solo_personen": {"Clara": "Bratsche"}}),

    # Grosse Besetzung -> mehr Personen links als Gusttor-Mixe (J5-9): loest den
    # Gusttor-Ueberlauf-Zweig aus (bericht['monitor_ueberlauf']).
    ("monitor_ueberlauf", """
Lobpreisleitung DD1: Emma
MD DD1: Bert
Bass DD1: Bert
Drums DD1: Felix
A-Git DD1: Lena
E-Git DD1: Max
Piano DD1: Cara
Synth DD1: Dora
Solo DD1: Emil
Geige DD1: Finn
Gesang DD1 1: Emma
Gesang DD1 2: Greta
Gesang DD1 3: Hans
Gesang DD1 4: Ida
Gesang DD1 5: Jan
""", None),
]

# Diese (deterministischen) Teile des Ergebnisses werden als Snapshot verglichen.
SNAP_KEYS = ("kuerzel", "vorne", "hinten", "solo", "excel", "scene")


def _plane(text, opts):
    opts = opts or {}
    cfg = copy.deepcopy(BASIS_CFG)
    return L.plane(text.strip(), cfg, {}, opts.get("solo_personen") or {})


def schnappschuss(name, text, opts):
    r = _plane(text, opts)
    return {k: r.get(k) for k in SNAP_KEYS}


def vergleiche_snapshot(self, name, ist):
    """Vergleicht 'ist' mit dem Snapshot tests/snapshots/<name>.json. Legt den
       Snapshot an, falls er fehlt (oder UPDATE_SNAPSHOTS=1 gesetzt ist)."""
    pfad = os.path.join(SNAP_DIR, name + ".json")
    if UPDATE or not os.path.isfile(pfad):
        os.makedirs(SNAP_DIR, exist_ok=True)
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump(ist, f, ensure_ascii=False, indent=1, sort_keys=True)
        if not UPDATE:
            self.skipTest(f"Snapshot neu angelegt: {name}")
        return
    with open(pfad, encoding="utf-8") as f:
        soll = json.load(f)
    # Roundtrip durch JSON, damit Tupel/Listen identisch verglichen werden.
    ist = json.loads(json.dumps(ist, ensure_ascii=False))
    self.assertEqual(soll, ist, f"Snapshot weicht ab fuer '{name}' "
                                f"(bei bewusster Aenderung: UPDATE_SNAPSHOTS=1)")


class GoldenFileTests(unittest.TestCase):
    maxDiff = None


def _mache_test(name, text, opts):
    def test(self):
        vergleiche_snapshot(self, name, schnappschuss(name, text, opts))
    return test


for _name, _text, _opts in FAELLE:
    setattr(GoldenFileTests, "test_" + _name, _mache_test(_name, _text, _opts))


# ---------------------------------------------------------------------------
# Artefakt-Tests: aus den erzeugten BYTES (.xlsx) bzw. dem .scn-Text wird wieder
# ausgelesen und gegen einen Snapshot verglichen. So ist die komplette
# Datei-Erzeugung (nicht nur die bericht-Logik) abgedeckt -- ein verrutschtes
# Vorlagen-Layout oder ein kaputter Zell-Schreiber faellt sofort auf.
# ---------------------------------------------------------------------------

# Spalten, die der Generator im Belegungsplan beschreibt (Footprint).
ARTEFAKT_SPALTEN = {"C", "F", "G", "J", "R", "S", "Y", "Z"}


def _xlsx_zellen(daten, blatt, spalten):
    """Liest die belegten Zellen der angegebenen Spalten aus den erzeugten
       Excel-Bytes zurueck (Inline-String, Shared-String oder Zahl)."""
    z = zipfile.ZipFile(io.BytesIO(daten))
    try:
        sheet = L._sheet_datei_fuer_blatt(z, blatt)
        try:
            ss = ["".join(t.text or "" for t in si.iter(f"{{{L.M}}}t"))
                  for si in ET.fromstring(z.read("xl/sharedStrings.xml"))]
        except KeyError:
            ss = []
        root = ET.fromstring(z.read(sheet))
        out = {}
        for c in root.iter(f"{{{L.M}}}c"):
            ref = c.get("r")
            spalte = re.match(r"[A-Z]+", ref).group(0)
            if spalte not in spalten:
                continue
            inl = c.find(f"{{{L.M}}}is")
            if inl is not None:
                wert = "".join(x.text or "" for x in inl.iter(f"{{{L.M}}}t"))
            else:
                v = c.find(f"{{{L.M}}}v")
                if v is None:
                    continue
                wert = ss[int(v.text)] if c.get("t") == "s" else (v.text or "")
            wert = wert.strip()
            if wert:
                out[ref] = wert
        return out
    finally:
        z.close()


def _scene_konfig_zeilen(text):
    """Nur die Zeilen, die erzeuge_scene anfasst (Kanal- und Bus-config)."""
    return [z for z in (text or "").splitlines()
            if re.match(r"^/(ch|bus)/\d+/config ", z)]


# Repraesentative Besetzungen fuer die Artefakt-Snapshots.
ARTEFAKT_FAELLE = [("dd1_standard", FAELLE[0][1], FAELLE[0][2])]


class ArtefaktTests(unittest.TestCase):
    maxDiff = None


def _mache_artefakt_test(name, text, opts):
    def test(self):
        r = _plane(text, opts)
        # Jede angesteuerte Zelle muss in der Vorlage existieren (sonst Drift).
        self.assertEqual([], r["fehlend"],
                          "Excel-Zellen nicht in der Vorlage gefunden: "
                          f"{r['fehlend']}")
        blatt = BASIS_CFG["excel"]["blatt"]
        zellen = _xlsx_zellen(r["excel_bytes"], blatt, ARTEFAKT_SPALTEN)
        vergleiche_snapshot(self, "artefakt_" + name + "_excel", zellen)
        if r.get("scene_text"):
            vergleiche_snapshot(self, "artefakt_" + name + "_scene",
                                _scene_konfig_zeilen(r["scene_text"]))
    return test


for _name, _text, _opts in ARTEFAKT_FAELLE:
    setattr(ArtefaktTests, "test_artefakt_" + _name, _mache_artefakt_test(_name, _text, _opts))


# ---------------------------------------------------------------------------
# Regen-Tests: stellen sicher, dass UI-Edits tatsaechlich in den
# Excel-Bytes und im Scene-Text ankommen. Ohne diesen Pfad aenderte
# dlExcel/dlScene nur die initialen Generierungs-Ergebnisse.
# ---------------------------------------------------------------------------

class RegenTests(unittest.TestCase):
    """regeneriere_excel_und_scene: der Pfad, der dlExcel/dlScene nach
       UI-Edits auf den aktuellen Stand bringt."""
    maxDiff = None

    def _plane_erg(self):
        return L.plane(FAELLE[0][1].strip(),
                        copy.deepcopy(BASIS_CFG), {}, {})

    def test_label_edit_in_excel_und_scene(self):
        r = self._plane_erg()
        regen = L.regeneriere_excel_und_scene(
            r, copy.deepcopy(BASIS_CFG),
            {"inputs": [
                {"label": "EVA-NEU", "mic": "SM58-NEU"},
                {"label": "MARIE-NEU", "mic": "Beta58-NEU"},
            ]},
        )
        # Excel C5/H5 muessen die neuen Namen tragen
        blatt: str = BASIS_CFG["excel"]["blatt"]
        zellen: dict[str, str] = _xlsx_zellen(regen["excel_bytes"], blatt,
                                              {"C", "F", "G", "H", "R", "S", "Y", "Z"})
        self.assertEqual(zellen.get("C5"), "EVA-NEU")
        self.assertEqual(zellen.get("H5"), "SM58-NEU")
        self.assertEqual(zellen.get("C6"), "MARIE-NEU")
        self.assertEqual(zellen.get("H6"), "Beta58-NEU")
        # R-Patchlist (SB1): inputs[0] -> slot 1, inputs[1] -> slot 2
        self.assertEqual(zellen.get("R5"), "EVA-NEU")
        self.assertEqual(zellen.get("S5"), "SM58-NEU")
        self.assertEqual(zellen.get("R6"), "MARIE-NEU")
        self.assertEqual(zellen.get("S6"), "Beta58-NEU")
        # Scene: Channel-Configs tragen die neuen Namen
        scene_lines: list[str] = (regen.get("scene_text") or "").splitlines()
        self.assertTrue(any('/ch/01/config "EVA-NEU"' in z for z in scene_lines),
                        "Scene Ch01 nicht umbenannt")
        self.assertTrue(any('/ch/02/config "MARIE-NEU"' in z for z in scene_lines),
                        "Scene Ch02 nicht umbenannt")
        self.assertEqual(regen["fehlend"], [])

    def test_stagebox_wechsel_aendert_scene_source(self):
        r = self._plane_erg()
        regen = L.regeneriere_excel_und_scene(
            r, copy.deepcopy(BASIS_CFG),
            {"inputs": [{"sb1": None, "sb2": 5}]},
        )
        blatt: str = BASIS_CFG["excel"]["blatt"]
        zellen: dict[str, str] = _xlsx_zellen(regen["excel_bytes"], blatt,
                                              {"F", "G"})
        # Nach Reorder: Emma ist einziger Eintrag auf SB2, bekommt Slot 1
        # (Voc wird nach oben sortiert, keine Lücken)
        self.assertNotEqual(zellen.get("F5"), "1",
                            "F5 muss frei sein (SB1-Slot wurde abgegeben)")
        self.assertEqual(zellen.get("G5"), "1",
                         "Emma als einziger SB2-Eintrag → Slot 1 (reorder)")
        # Scene Ch01 Source = 1 + 16 = 17
        ch1: str = next((z for z in (regen.get("scene_text") or "").splitlines()
                          if z.startswith("/ch/01/config")), "")
        self.assertTrue(ch1, "Scene Ch01 Zeile fehlt")
        self.assertEqual(int(ch1.split()[-1]), 17)

    def test_setzwerte_state_propagates_across_regens(self):
        """Zwei aufeinanderfolgende Regen-Aufrufe muessen akkumulieren --
           die zweite Aenderung darf die erste nicht ueberschreiben."""
        r = self._plane_erg()
        # Erste Aenderung: Gesang 1 umbenennen
        res1 = L.regeneriere_excel_und_scene(
            r, copy.deepcopy(BASIS_CFG),
            {"inputs": [{"label": "EVA-NEU"}]},
        )
        # Zweite Aenderung: Gesang 2 umbenennen, auf res1 aufsetzen
        res2 = L.regeneriere_excel_und_scene(
            {"setzwerte": res1["setzwerte"], "excel": res1["excel"]},
            copy.deepcopy(BASIS_CFG),
            {"inputs": [{}, {"label": "MARIE-NEU"}]},
        )
        blatt: str = BASIS_CFG["excel"]["blatt"]
        zellen: dict[str, str] = _xlsx_zellen(res2["excel_bytes"], blatt, {"C"})
        self.assertEqual(zellen.get("C5"), "EVA-NEU",
                         "Erste Aenderung ging verloren")
        self.assertEqual(zellen.get("C6"), "MARIE-NEU")

    def test_edit_ohne_edit_gibt_origin_zurueck(self):
        """Regen ohne Edits darf das Original nicht versauen (Regression-
           Schutz: niemand darf in regeneriere_excel_und_scene versehentlich
           Inputs ueberschreiben)."""
        r = self._plane_erg()
        regen = L.regeneriere_excel_und_scene(
            r, copy.deepcopy(BASIS_CFG), None,
        )
        blatt: str = BASIS_CFG["excel"]["blatt"]
        zellen: dict[str, str] = _xlsx_zellen(regen["excel_bytes"], blatt, {"C", "H"})
        # C5 hat den Original-Namen, nicht 'None' oder ''
        self.assertTrue(zellen.get("C5"),
                        f"Original-Name verschwunden: C5={zellen.get('C5')!r}")

    def test_bus_edit_behaelt_andere_busnamen(self):
        """Ein einzelner Bus-Name-Edit darf die uebrigen Gusttor-Busse in der
           .scn NICHT auf die Template-Defaults zuruecksetzen (Regression)."""
        r = self._plane_erg()
        orig = r["excel"].get("busse") or []
        self.assertGreaterEqual(len(orig), 2, "Testfall braucht >=2 Gusttor-Busse")
        ziel = int(orig[0]["bus"])
        regen = L.regeneriere_excel_und_scene(
            r, copy.deepcopy(BASIS_CFG),
            {"busse": [{"bus": ziel, "name": "NEU-EVA"}]},
        )
        zeilen = (regen.get("scene_text") or "").splitlines()

        def busname(nr):
            pat = "/bus/%02d/config " % nr
            z = next((x for x in zeilen if x.startswith(pat)), "")
            m = re.search(r'config "([^"]*)"', z)
            return m.group(1) if m else None
        self.assertEqual(busname(ziel), "NEU-EVA")
        for b in orig[1:]:
            self.assertEqual(busname(int(b["bus"])), b["name"],
                             f"Bus {b['bus']} verlor seinen Namen nach fremdem Edit")

    def test_bus_edit_landet_in_excel_j_und_bericht(self):
        """Ein Bus-Name-Edit muss in der Excel-J-Spalte UND im zurueckgegebenen
           Bericht (Outputs-Tabelle im UI) stehen -- nicht nur in der Scene."""
        r = self._plane_erg()
        orig = r["excel"].get("busse") or []
        self.assertGreaterEqual(len(orig), 1, "Testfall braucht >=1 Monitor-Bus")
        ziel = int(orig[0]["bus"])
        regen = L.regeneriere_excel_und_scene(
            r, copy.deepcopy(BASIS_CFG),
            {"busse": [{"bus": ziel, "name": "MONITOR-NEU"}]},
        )
        # Excel: die J-Zelle des Bus traegt den neuen Namen
        j_cell = L._bus_zu_j_zelle(ziel, BASIS_CFG["excel"])
        self.assertIsNotNone(j_cell, "Bus hat keine J-Zelle")
        blatt = BASIS_CFG["excel"]["blatt"]
        zellen = _xlsx_zellen(regen["excel_bytes"], blatt, {"J"})
        self.assertEqual(zellen.get(j_cell), "MONITOR-NEU")
        # Bericht (Outputs-Tabelle) spiegelt den Edit fuer den Roundtrip
        neu = next((b for b in (regen["excel"].get("busse") or [])
                    if int(b["bus"]) == ziel), None)
        self.assertIsNotNone(neu, "Bus fehlt im Bericht")
        self.assertEqual(neu["name"], "MONITOR-NEU")


# ---------------------------------------------------------------------------
# Multitrack-Tests: Rolle "Multitrack" in der Besetzung aktiviert automatisch
# die Track-Eingaenge (track_aktiv=True) und erscheint als Label in der Skizze.
# ---------------------------------------------------------------------------

class MultitrackTests(unittest.TestCase):
    """Multitrack in der Besetzung -> track_aktiv wird automatisch True."""
    maxDiff = None

    MULTITRACK_TEXT = """
Lobpreisleitung DD1: Emma Meier
Gesang DD1 1: Tim Schmidt
Multitrack DD1: Alex Doe
"""

    KEIN_MULTITRACK_TEXT = """
Lobpreisleitung DD1: Emma Meier
Gesang DD1 1: Tim Schmidt
Bass DD1: Alex Doe
"""

    def test_multitrack_aktiviert_track(self) -> None:
        """Multitrack in der Besetzung -> track_aktiv=True im Ergebnis."""
        r = L.plane(self.MULTITRACK_TEXT.strip(),
                    copy.deepcopy(BASIS_CFG), {}, {})
        self.assertTrue(r.get("track_aktiv"),
                        "track_aktiv sollte True sein bei Multitrack in der Besetzung")

    def test_kein_multitrack_deaktiviert_track(self) -> None:
        """Ohne Multitrack bleibt track_aktiv=False (Basis-Mapping-Default)."""
        r = L.plane(self.KEIN_MULTITRACK_TEXT.strip(),
                    copy.deepcopy(BASIS_CFG), {}, {})
        self.assertFalse(r.get("track_aktiv"),
                         "track_aktiv sollte False sein ohne Multitrack")

    def test_multitrack_track_inputs_present(self) -> None:
        """Bei aktiviertem Track muessen die Track-Eingaenge in Excel belegt sein."""
        r = L.plane(self.MULTITRACK_TEXT.strip(),
                    copy.deepcopy(BASIS_CFG), {}, {})
        track_inputs = [i for i in r["excel"]["inputs"]
                        if i.get("label") and "Track" in (i.get("label") or "")]
        self.assertGreaterEqual(len(track_inputs), 2,
                                "Track + Track Klick muessen belegt sein")
        for ti in track_inputs:
            self.assertTrue(ti.get("sb1") or ti.get("sb2"),
                             f"Track-Eingang {ti.get('label')} hat keine SB-Nummer")

    def test_multitrack_person_landet_vorne(self) -> None:
        """Multitrack ist keine Backline-Rolle -> Person landet in der vorderen Reihe."""
        r = L.plane(self.MULTITRACK_TEXT.strip(),
                    copy.deepcopy(BASIS_CFG), {}, {})
        vorne_namen = [p["voll"] for p in r["vorne"]]
        self.assertIn("Alex Doe", vorne_namen,
                      "Multitrack-Person muss vorne stehen")

    def test_multitrack_label_erscheint(self) -> None:
        """Das Label der Multitrack-Person enthaelt 'Multitrack' als Rollen-Kurzform."""
        r = L.plane(self.MULTITRACK_TEXT.strip(),
                    copy.deepcopy(BASIS_CFG), {}, {})
        mt = next(p for p in r["vorne"] if p["voll"] == "Alex Doe")
        self.assertIn("Multitrack", mt["rollen"],
                      "Multitrack muss im Rollen-Label erscheinen")

    def test_unbesetztes_multitrack_aktiviert_nicht(self) -> None:
        """Ein unbesetztes Multitrack ('?') darf track_aktiv NICHT aktivieren."""
        text = "Multitrack DD1: ?\nGesang DD1 1: Tim\n"
        r = L.plane(text.strip(), copy.deepcopy(BASIS_CFG), {}, {})
        self.assertFalse(r.get("track_aktiv"),
                         "Unbesetztes Multitrack darf track_aktiv nicht setzen")

    def test_track_wird_zurueckgesetzt_ohne_multitrack(self) -> None:
        """Wurde track_aktiv durch Multitrack aktiviert, muss eine nachfolgende
           Besetzung OHNE Multitrack track_aktiv wieder auf False setzen
           (track_aktiv wird bei jedem plane()-Lauf aus der Besetzung bestimmt)."""
        cfg = copy.deepcopy(BASIS_CFG)
        cfg.setdefault("excel", {})["track_aktiv"] = True  # simuliert: vorher aktiviert
        r = L.plane(self.KEIN_MULTITRACK_TEXT.strip(), cfg, {}, {})
        self.assertFalse(r.get("track_aktiv"),
                         "track_aktiv muss False sein, wenn die neue Besetzung keinen Multitrack hat")


# ---------------------------------------------------------------------------
# Box-Breite-Tests: _label_breite schaetzt grosszuegig genug, dass Text nicht
# ueber den Box-Rand ragt (generell, nicht nur fuer Multitrack).
# ---------------------------------------------------------------------------

class LabelBreiteTests(unittest.TestCase):
    """_label_breite muss grosszuegig genug schaetzen, damit der Text in der
       Excalidraw-Box Platz hat und nicht ueber den Rand ragt."""
    maxDiff = None

    def test_kurz_label_passt(self) -> None:
        """Kurzes Label (z.B. 'Voc') braucht weniger als min_box_w."""
        from lp_layout import _label_breite
        w = _label_breite("Emma\nVoc")
        self.assertGreater(w, 0)
        self.assertLess(w, 200, "Kurzes Label sollte unter 200px bleiben")

    def test_lang_label_hat_reserve(self) -> None:
        """Laengeres Label (z.B. 'Multitrack') muss genug Reserve haben."""
        from lp_layout import _label_breite
        w = _label_breite("Alex\nMultitrack")
        # Multitrack = 10 Zeichen, bei char=0.7, fontsize=20, pad=32:
        # 10 * 20 * 0.7 + 32 = 172
        self.assertGreaterEqual(w, 170,
                                "Multitrack-Label muss breit genug geschaetzt werden")

    def test_mehrzeilig_nimmt_laengste_zeile(self) -> None:
        """Bei mehrzeiligen Labels wird die laengste Zeile fuer die Breite gemessen."""
        from lp_layout import _label_breite
        w_kurz = _label_breite("A\nB")
        w_lang = _label_breite("A\nMultitrack")
        self.assertGreater(w_lang, w_kurz,
                           "Laengere Zeile muss breitere Box fordern")

    def test_box_wachstum_in_konfig(self) -> None:
        """box_wachstum muss in mapping.json gesetzt sein (groesser als default 130)."""
        self.assertGreaterEqual(BASIS_CFG["buehne"].get("box_wachstum", 130), 170,
                                "box_wachstum sollte >= 170 sein fuer breitere Boxen")

    def test_max_box_w_in_konfig(self) -> None:
        """max_box_w fuer die vordere Reihe muss grosszuegig genug sein."""
        self.assertGreaterEqual(BASIS_CFG["buehne"]["vorne"]["max_box_w"], 190,
                                "max_box_w sollte >= 190 sein fuer laengere Labels")


if __name__ == "__main__":
    unittest.main(verbosity=2)
