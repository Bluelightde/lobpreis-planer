#!/usr/bin/env python3
"""Tests für die Heuristiken in setlisten_check.py (_pruefe_zeile, _letzte_klammer)."""

import os
import sys
import unittest

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASIS)
sys.path.insert(0, os.path.join(BASIS, "werkzeuge"))
import setlisten_check as SC   # noqa: E402
import churchtools as CT       # noqa: E402


class LetzteKlammerTests(unittest.TestCase):
    def test_einfach(self):
        self.assertEqual(SC._letzte_klammer("- Titel (Besetzung)"), "Besetzung")

    def test_titel_mit_klammern(self):
        self.assertEqual(SC._letzte_klammer(
            "- Psalm 23 (Ich bin der Herr) (Voc, E-Git)"), "Voc, E-Git")

    def test_verschachtelt_verschiedene_tiefen(self):
        self.assertEqual(SC._letzte_klammer(
            "- Lied (Intro (langsam)) (Besetzung)"), "Besetzung")

    def test_keine_klammer(self):
        self.assertIsNone(SC._letzte_klammer("- Titel ohne alles"))

    def test_nur_oeffnende(self):
        self.assertIsNone(SC._letzte_klammer("- Titel (unvollstaendig"))

    def test_leer(self):
        self.assertIsNone(SC._letzte_klammer(""))


class PruefeZeileTests(unittest.TestCase):
    def test_normal_keine_auffaelligkeit(self):
        self.assertEqual(SC._pruefe_zeile("- Titel (David, A-Git)"), [])

    def test_doppeltes_trennzeichen(self):
        self.assertIn("doppeltes Trennzeichen",
                      " ".join(SC._pruefe_zeile("- Titel (David, , A-Git)")))

    def test_stimm_praefix_nicht_entfernt(self):
        gruende = SC._pruefe_zeile("- Titel (Lead: David, A-Git)")
        self.assertTrue(any("Praefix" in g for g in gruende),
                        f"Erwarte Praefix-Warnung in {gruende}")

    def test_stopwort_als_stimme(self):
        gruende = SC._pruefe_zeile("- Titel (Intro, A-Git)")
        self.assertTrue(any("Schluesselwort" in g for g in gruende),
                        f"Erwarte Schluesselwort-Warnung in {gruende}")

    def test_stopwort_alle(self):
        gruende = SC._pruefe_zeile("- Titel (Alle, Drums)")
        self.assertTrue(any("Schluesselwort" in g for g in gruende))

    def test_stopwort_chorus(self):
        gruende = SC._pruefe_zeile("- Titel (Chorus)")
        self.assertTrue(any("Schluesselwort" in g for g in gruende))

    def test_instrument_als_stimme(self):
        gruende = SC._pruefe_zeile("- Titel (E-Git, Drums)")
        self.assertTrue(any("Instrument" in g for g in gruende),
                        f"Erwarte Instrument-Warnung in {gruende}")

    def test_voc_in_bemerkung(self):
        gruende = SC._pruefe_zeile(
            "- Titel [Mit Track; LeadVoc: David] (David, A-Git)")
        self.assertTrue(any("Bemerkung" in g for g in gruende),
                        f"Erwarte Bemerkung-Warnung in {gruende}")

    def test_nur_bemerkung_keine_stimme_ok(self):
        self.assertEqual(SC._pruefe_zeile("- Titel [Nur Bemerkung]"), [])

    def test_leere_stimme_ok(self):
        self.assertEqual(SC._pruefe_zeile("- Titel ()"), [])

    def test_mehrere_gruende(self):
        gruende = SC._pruefe_zeile("- Titel (lead: Intro,, [LeadVoc: X])")
        self.assertGreaterEqual(len(gruende), 2)

    def test_vox_abkuerzung(self):
        gruende = SC._pruefe_zeile(
            "- Titel [Vox: Sarah] (Sarah)")
        self.assertTrue(any("Bemerkung" in g for g in gruende))


class StopwortAbdeckungTests(unittest.TestCase):
    """Prüft, dass die _STOPWORTE-Menge typische Parsing-Fehler abdeckt."""

    def test_typische_falsch_erkannte_stimmen(self):
        falsche_stimmen = [
            "Intro", "Outro", "Bridge", "Refrain", "Chorus",
            "Vers", "Verse", "Pre-Chorus", "Prechorus",
            "Track", "Backingtrack", "Playback",
            "Alle", "All", "Instrumental",
        ]
        for wort in falsche_stimmen:
            with self.subTest(wort=wort):
                self.assertIn(wort.lower(), SC._STOPWORTE,
                              f"'{wort}' fehlt in _STOPWORTE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
