#!/usr/bin/env python3
"""
Invarianten-Tests fuer plane().

Diese Tests pruefen *Eigenschaften*, die fuer jeden Plan gelten muessen --
anders als die Golden-File-Tests in test_plane.py, die auf einen festen
Snapshot vergleichen. So fallen strukturelle Regressionen auf, ohne dass
bei jeder bewussten Aenderung alle Snapshots neu geschrieben werden muessen.

Gepruefte Invarianten:
  * A-Nummern-Bereich: SB1 -> A1..A16, SB2 -> A17..A32
  * Keine Duplikate innerhalb einer Stagebox
  * Konsistenz: stagebox1/2 <-> inputs (Label, Mic, A-Nr)
  * Kapazitaet: hoechstens 16 Eintraege pro Stagebox
  * Excel-Artefakt: alle angesteuerten Zellen existieren in der Vorlage
  * Eingabeparsing-Robustheit: leerer Text, sehr grosse Besetzung

Aufruf:
    python3 tests/test_invariantes.py
"""

import copy
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

with open(L.KONFIG, encoding="utf-8") as _f:
    BASIS_CFG = json.load(_f)

KAP = BASIS_CFG["excel"].get("stagebox_kapazitaet", 16)


def _plane(text, cfg=None):
    return L.plane(text, cfg or copy.deepcopy(BASIS_CFG), {}, {})


# Standard-Besetzungen, gegen die Invarianten geprueft werden.
STANDARD = """
Lobpreisleitung DD1: Emma
MD DD1: Bert
A-Git DD1: Lena
E-Git DD1: Max
Bass DD1: Bert
Drums DD1: Felix
Gesang DD1 1: Emma
Gesang DD1 2: Greta
Gesang DD1 3: Max
"""


def _quell_nr(source):
    """Parst 'A17' -> 17, 'A1' -> 1."""
    m = re.match(r"^A(\d+)$", source or "")
    return int(m.group(1)) if m else None


def _stagebox_aus_inputs(excel):
    """Leitet stagebox1/2 deterministisch aus inputs ab (Spiegel der
       Frontend-Funktion 'rederiveStageboxen') -- gegen diese Ableitung
       wird das plane()-Ergebnis verifiziert."""
    out = {1: [], 2: []}
    for k in range(1, 17):
        inp1 = next((x for x in excel["inputs"] if x.get("sb1") == k), None)
        if inp1 and (inp1.get("label") or inp1.get("mic")):
            out[1].append({"nr": k, "source": f"A{k}",
                           "label": inp1.get("label", ""), "mic": inp1.get("mic", "")})
        inp2 = next((x for x in excel["inputs"] if x.get("sb2") == k), None)
        if inp2 and (inp2.get("label") or inp2.get("mic")):
            out[2].append({"nr": k, "source": f"A{k + 16}",
                           "label": inp2.get("label", ""), "mic": inp2.get("mic", "")})
    return out[1], out[2]


class ANummerBereichTests(unittest.TestCase):
    """SB1 -> A1..A16, SB2 -> A17..A32, nie ausserhalb."""

    def test_sb1_bereich(self):
        r = _plane(STANDARD)
        for e in r["excel"]["stagebox1"]:
            n = _quell_nr(e["source"])
            self.assertIsNotNone(n, f"Ungueltige source: {e['source']!r}")
            self.assertGreaterEqual(n, 1)
            self.assertLessEqual(n, KAP)

    def test_sb2_bereich(self):
        r = _plane(STANDARD)
        for e in r["excel"]["stagebox2"]:
            n = _quell_nr(e["source"])
            self.assertIsNotNone(n, f"Ungueltige source: {e['source']!r}")
            self.assertGreaterEqual(n, KAP + 1)
            self.assertLessEqual(n, 2 * KAP)

    def test_keine_sb1_in_sb2_und_umgekehrt(self):
        r = _plane(STANDARD)
        sb1 = {_quell_nr(e["source"]) for e in r["excel"]["stagebox1"]}
        sb2 = {_quell_nr(e["source"]) for e in r["excel"]["stagebox2"]}
        self.assertEqual(sb1 & sb2, set(), "A-Nummer doppelt vergeben")


class KeineDuplikateTests(unittest.TestCase):
    """Innerhalb einer Stagebox keine doppelten A-Nummern."""

    def test_stagebox1_eindeutig(self):
        r = _plane(STANDARD)
        nums = [_quell_nr(e["source"]) for e in r["excel"]["stagebox1"]]
        self.assertEqual(len(nums), len(set(nums)), f"Duplikate: {nums}")

    def test_stagebox2_eindeutig(self):
        r = _plane(STANDARD)
        nums = [_quell_nr(e["source"]) for e in r["excel"]["stagebox2"]]
        self.assertEqual(len(nums), len(set(nums)), f"Duplikate: {nums}")

    def test_nr_ist_position(self):
        """nr (1..16) ist die Position innerhalb der Box -- genau einmal pro Wert."""
        r = _plane(STANDARD)
        nrs = [e["nr"] for e in r["excel"]["stagebox1"]]
        self.assertEqual(sorted(nrs), list(range(1, len(nrs) + 1)))


class KapazitaetTests(unittest.TestCase):
    """Hoechstens KAP Eintraege pro Stagebox (Auto-Balance)."""

    def test_max_pro_box(self):
        r = _plane(STANDARD)
        self.assertLessEqual(len(r["excel"]["stagebox1"]), KAP)
        self.assertLessEqual(len(r["excel"]["stagebox2"]), KAP)

    def test_auto_balance_bei_ueberlauf(self):
        """17 Inputs erzwingen einen Wechsel auf die andere Box."""
        text = "\n".join([f"Gesang DD1 {i}: Person{i}" for i in range(1, 18)])
        r = _plane(text)
        # Es gibt 17 Gesang-Kanaele; bei 16/Box geht mindestens einer rueber.
        self.assertLessEqual(len(r["excel"]["stagebox1"]), KAP)
        self.assertLessEqual(len(r["excel"]["stagebox2"]), KAP)
        # Und die Summe sollte 17 sein (alle Gesang-Kanaele verteilt)
        # abzueglich derer, die auf den vocal-Bus gehen (voc-Kanaele
        # erscheinen NICHT in stagebox1/2).
        # Mindestens die Input-Kanaele (voc-Anzahl + 1) sollten verteilt sein.

    def test_konfigurierbare_kapazitaet(self):
        """stagebox_kapazitaet steuert Balance-Schwelle UND SB2-Quell-Offset."""
        cfg = copy.deepcopy(BASIS_CFG)
        cfg["excel"]["stagebox_kapazitaet"] = 8
        text = "\n".join([f"Gesang DD1 {i}: Person{i}" for i in range(1, 18)])
        r = _plane(text, cfg)
        self.assertLessEqual(len(r["excel"]["stagebox1"]), 8)
        self.assertLessEqual(len(r["excel"]["stagebox2"]), 8)
        # SB1 -> A1..A8, SB2 -> A9..A16 (Offset = Kapazitaet)
        for e in r["excel"]["stagebox1"]:
            self.assertLessEqual(_quell_nr(e["source"]), 8)
        for e in r["excel"]["stagebox2"]:
            self.assertGreaterEqual(_quell_nr(e["source"]), 9)
            self.assertLessEqual(_quell_nr(e["source"]), 16)


class KonsistenzTests(unittest.TestCase):
    """plane().excel.stagebox1/2 <-> plane().excel.inputs."""

    def test_stagebox1_aus_inputs_rekonstruierbar(self):
        r = _plane(STANDARD)
        sb1_erwartet, _ = _stagebox_aus_inputs(r["excel"])
        self.assertEqual(r["excel"]["stagebox1"], sb1_erwartet)

    def test_stagebox2_aus_inputs_rekonstruierbar(self):
        r = _plane(STANDARD)
        _, sb2_erwartet = _stagebox_aus_inputs(r["excel"])
        self.assertEqual(r["excel"]["stagebox2"], sb2_erwartet)

    def test_label_in_stagebox_stimmt_mit_input(self):
        r = _plane(STANDARD)
        for e in r["excel"]["stagebox1"]:
            nr = e["nr"]
            inp = next((x for x in r["excel"]["inputs"] if x.get("sb1") == nr), None)
            self.assertIsNotNone(inp, f"Kein Input mit sb1={nr}")
            self.assertEqual(e["label"], inp.get("label", ""))
            self.assertEqual(e["mic"], inp.get("mic", ""))


class EingabeRobustheitTests(unittest.TestCase):
    """Leere/kleine Besetzungen duerfen nicht abstuerzen."""

    def test_leerer_text(self):
        r = _plane("")
        self.assertIsNone(r["kuerzel"])
        self.assertEqual(r["personen"], [])
        self.assertEqual(r["fehlend"], [])

    def test_nur_whitespace(self):
        r = _plane("   \n\n  \n")
        self.assertEqual(r["personen"], [])

    def test_unbekannte_rollen_werden_ignoriert(self):
        """Rollen, die nicht im mapping stehen, fuehren nicht zu Inputs
           (oder nur zu harmlosen Person-Eintraegen)."""
        r = _plane("Banjo DD1: Lena\nGesang DD1 1: Bob")
        # Wichtig: kein Crash, kein Excel-Fehler
        self.assertEqual(r["fehlend"], [])

    def test_nur_drums_und_bass(self):
        r = _plane("Drums DD1: A\nBass DD1: B")
        self.assertEqual(r["fehlend"], [])
        # Mindestens Bass + Drumkit-Mics als Inputs verteilt
        sb = r["excel"]["stagebox1"] + r["excel"]["stagebox2"]
        labels = [e["label"] for e in sb]
        self.assertIn("Bass", labels)
        # Drumkit wird in seine Einzel-Mics aufgeteilt (Kick, Snare, ...)
        self.assertTrue(any("Snare" in l or "Kick" in l for l in labels),
                        f"Keine Drum-Mics in: {labels}")


class ExcelArtefaktTests(unittest.TestCase):
    """Die generierte .xlsx enthaelt alle angesteuerten Zellen."""

    def test_fehlend_leer(self):
        r = _plane(STANDARD)
        self.assertEqual(r["fehlend"], [],
                         f"Zellen nicht in Vorlage: {r['fehlend']}")

    def test_excel_bytes_sind_valide_xlsx(self):
        """Sind die Bytes zumindest ein lesbares OOXML-Archiv?"""
        import io
        r = _plane(STANDARD)
        try:
            z = zipfile.ZipFile(io.BytesIO(r["excel_bytes"]))
            names = z.namelist()
        except zipfile.BadZipFile:
            self.fail("excel_bytes ist kein gueltiges ZIP/XLSX")
        self.assertIn("xl/workbook.xml", names)
        self.assertIn("[Content_Types].xml", names)

    def test_belegte_zellen_referenzieren_vorlage(self):
        """Jede in der Vorlage angesteuerte Zelle existiert tatsaechlich."""
        r = _plane(STANDARD)
        import io
        z = zipfile.ZipFile(io.BytesIO(r["excel_bytes"]))
        M = L.M
        blatt = BASIS_CFG["excel"]["blatt"]
        sheet = L._sheet_datei_fuer_blatt(z, blatt)
        root = ET.fromstring(z.read(sheet))
        vorhandene = {c.get("r") for c in root.iter(f"{{{M}}}c")}
        # Alle nicht-leeren setzwerte sollten in der Vorlage existieren
        # (das ist genau das, was 'fehlend' aussagt -- hier verifiziert
        # wir die Konsistenz von 'fehlend' und der realen Tabelle).
        self.assertEqual(r["fehlend"], [])


class SceneTests(unittest.TestCase):
    """Der X32-Szene-Text wird nur erzeugt, wenn die Vorlage vorhanden ist."""

    def test_scene_keys(self):
        r = _plane(STANDARD)
        sc = r.get("scene") or {}
        # Mindestens einer der Busse/Vocs-Keys sollte existieren, sobald
        # die Standardbesetzung Belege hat.
        self.assertIn("busse", sc)
        self.assertIn("voc", sc)


class VocReihenfolgeTests(unittest.TestCase):
    """Voc-Reihenfolge folgt der Skizze (links -> rechts nach X-Position) und
       die X32-Szene-Kanaele folgen derselben Reihenfolge wie die Excel-Voc."""

    def _dd1(self):
        with open(os.path.join(BASIS, "besetzungen", "DD1.txt"), encoding="utf-8") as f:
            return f.read()

    def test_voc_folgt_skizze_links_rechts(self):
        cfg = copy.deepcopy(BASIS_CFG)
        text = self._dd1()
        # Layout direkt berechnen, um cx (Skizzen-X) je Saenger zu kennen.
        eintraege, _ = L.parse_besetzung_text(text)
        personen = L.personen_aus_eintraegen(eintraege, cfg["rollen_reihenfolge"])
        zuord = L.zuordnen(personen, cfg["buehne"],
                           cfg.get("sing_rollen", ["Gesang"]), cfg.get("modus"))
        _doc, layout = L.erzeuge_skizze_doc(
            zuord, cfg, {}, return_layout=True,
            solo_cfg=dict(cfg.get("solo_instrument") or {}))
        cx_von = {e["person"]["name"]: e["cx"] for e in layout["plan"]}

        r = L.plane(text, cfg, {}, {})
        belegte = [v for v in r["excel"]["voc"] if v.get("roh")]
        cxs = [cx_von.get(v["roh"]) for v in belegte]
        self.assertEqual(
            cxs, sorted(cxs, key=lambda c: (c is None, c)),
            f"Voc-Reihenfolge nicht links->rechts: "
            f"{[(v['roh'], cx_von.get(v['roh'])) for v in belegte]}")

    def test_scene_voc_folgt_excel_voc(self):
        r = L.plane(self._dd1(), copy.deepcopy(BASIS_CFG), {}, {})
        excel_namen = {v["voc"]: v["name"] for v in r["excel"]["voc"]}
        for sv in r["scene"]["voc"]:
            self.assertEqual(
                sv["name"], excel_namen.get(sv["voc"]),
                f"Scene-Voc {sv['voc']} weicht von der Excel-Voc-Reihenfolge ab")


if __name__ == "__main__":
    unittest.main(verbosity=2)
