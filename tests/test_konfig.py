#!/usr/bin/env python3
"""
Tests fuer lp_konfig: atomares JSON-Schreiben, Deep-Merge, Formatkonventionen.

Stellt sicher, dass alle per _schreibe_json_atomar geschriebenen Dateien:
  - gueltiges JSON sind,
  - mit einem Zeilenumbruch enden (POSIX-Konvention, saubere Diffs),
  - UTF-8-kodiert sind (ensure_ascii=False).

Aufruf:
    python3 tests/test_konfig.py
"""

import json
import os
import sys
import tempfile
import unittest

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASIS)

import lp_konfig as K  # noqa: E402


class AtomarerWriterTest(unittest.TestCase):
    """_schreibe_json_atomar: Format und Robustheit."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="lp_test_")
        self._pfad = os.path.join(self._tmpdir, "test.json")

    def tearDown(self) -> None:
        if os.path.exists(self._pfad):
            os.remove(self._pfad)
        os.rmdir(self._tmpdir)

    def test_endet_mit_newline(self) -> None:
        """Geschriebene JSON-Datei endet mit genau einem \\n."""
        K._schreibe_json_atomar(self._pfad, {"a": 1})
        with open(self._pfad, "rb") as f:
            content = f.read()
        self.assertTrue(content.endswith(b"\n"),
                        f"Datei endet nicht mit \\n: {content[-10:]!r}")
        self.assertFalse(content.endswith(b"\n\n"),
                         f"Doppeltes \\n am Ende: {content[-10:]!r}")

    def test_ist_gueltiges_json(self) -> None:
        """Geschriebene Datei kann von json.load gelesen werden."""
        daten = {"buehne": {"backline": {"Drums": {"immer": True}}},
                 "modus": {"leiter_links": True}}
        K._schreibe_json_atomar(self._pfad, daten)
        with open(self._pfad, encoding="utf-8") as f:
            gelesen = json.load(f)
        self.assertEqual(gelesen, daten)

    def test_ensure_ascii_false(self) -> None:
        """Umlaute und sz werden als UTF-8 geschrieben, nicht als \\uXXXX."""
        daten = {"name": "Bert Müller äöüß"}
        K._schreibe_json_atomar(self._pfad, daten)
        with open(self._pfad, "rb") as f:
            raw = f.read()
        self.assertIn(b"M\xc3\xbcller", raw,
                      "Umlaute wurden nicht als UTF-8 gespeichert")
        self.assertNotIn(b"\\u00fc", raw,
                         "ensure_ascii=False wurde nicht angewendet")

    def test_leeres_dict(self) -> None:
        """Auch ein leeres Dict bekommt einen trailing newline."""
        K._schreibe_json_atomar(self._pfad, {})
        with open(self._pfad, "rb") as f:
            content = f.read()
        self.assertTrue(content.endswith(b"\n"))

    def test_verschachtelt_endet_mit_newline(self) -> None:
        """Tief verschachtelte Strukturen bekommen ebenfalls einen newline."""
        daten = {"a": {"b": {"c": {"d": [1, 2, 3]}}}}
        K._schreibe_json_atomar(self._pfad, daten)
        with open(self._pfad, "rb") as f:
            content = f.read()
        self.assertTrue(content.endswith(b"\n"))

    def test_ueberschreibt_vorhandene_datei(self) -> None:
        """Beim erneuten Schreiben wird die alte Datei atomar ersetzt."""
        K._schreibe_json_atomar(self._pfad, {"alt": 1})
        K._schreibe_json_atomar(self._pfad, {"neu": 2})
        with open(self._pfad, encoding="utf-8") as f:
            daten = json.load(f)
        self.assertEqual(daten, {"neu": 2})
        self.assertNotIn("alt", daten)

    def test_keine_temp_datei_zurueckgelassen(self) -> None:
        """Nach erfolgreichem Schreiben gibt es keine .tmp-Datei mehr."""
        K._schreibe_json_atomar(self._pfad, {"x": 0})
        tmps = [f for f in os.listdir(self._tmpdir) if f.endswith(".tmp")]
        self.assertEqual(tmps, [],
                         f".tmp-Dateien nicht aufgeraeumt: {tmps}")


class DeepMergeTest(unittest.TestCase):
    """_deep_merge: Verschmelzung von mapping.json und einstellungen.json."""

    def test_skalar_ersetzt(self) -> None:
        base = {"a": 1, "b": 2}
        over = {"b": 99}
        ergebnis = K._deep_merge(base, over)
        self.assertEqual(ergebnis["a"], 1)
        self.assertEqual(ergebnis["b"], 99)

    def test_dict_wird_rekursiv_gemischt(self) -> None:
        base = {"buehne": {"breite": 100, "hoehe": 50}}
        over = {"buehne": {"breite": 200}}
        ergebnis = K._deep_merge(base, over)
        self.assertEqual(ergebnis["buehne"]["breite"], 200)
        self.assertEqual(ergebnis["buehne"]["hoehe"], 50)

    def test_liste_wird_ersetzt(self) -> None:
        """Listen werden nicht gemischt, sondern ersetzt (kein Merge)."""
        base = {"rollen": ["A", "B", "C"]}
        over = {"rollen": ["X"]}
        ergebnis = K._deep_merge(base, over)
        self.assertEqual(ergebnis["rollen"], ["X"])

    def test_none_over_laesst_base_erhalten(self) -> None:
        """over=None veraendert base nicht."""
        base = {"a": 1, "b": {"c": 2}}
        ergebnis = K._deep_merge(base, None)
        self.assertEqual(ergebnis, base)

    def test_tiefe_verschachtelung(self) -> None:
        base = {"a": {"b": {"c": {"d": 1}}}}
        over = {"a": {"b": {"c": {"e": 2}}}}
        ergebnis = K._deep_merge(base, over)
        self.assertEqual(ergebnis["a"]["b"]["c"]["d"], 1)
        self.assertEqual(ergebnis["a"]["b"]["c"]["e"], 2)

    def test_base_wird_inplace_gemischt(self) -> None:
        """_deep_merge mischt 'over' in-place in 'base' ein und gibt base zurueck."""
        base = {"a": {"x": 1}}
        ergebnis = K._deep_merge(base, {"a": {"y": 2}})
        self.assertIs(ergebnis, base)
        self.assertEqual(base["a"], {"x": 1, "y": 2})


class EinstellungenFormatTest(unittest.TestCase):
    """Prueft, dass die echte config/einstellungen.json Formatkonventionen einhaelt."""

    PFAD = os.path.join(BASIS, "config", "einstellungen.json")

    def test_endet_mit_newline(self) -> None:
        """einstellungen.json endet mit \\n (saubere git-Diffs, POSIX)."""
        if not os.path.isfile(self.PFAD):
            self.skipTest("einstellungen.json existiert nicht lokal")
        with open(self.PFAD, "rb") as f:
            content = f.read()
        self.assertTrue(content.endswith(b"\n"),
                        f"einstellungen.json endet nicht mit \\n: "
                        f"{content[-10:]!r}")

    def test_ist_gueltiges_json(self) -> None:
        if not os.path.isfile(self.PFAD):
            self.skipTest("einstellungen.json existiert nicht lokal")
        with open(self.PFAD, encoding="utf-8") as f:
            daten = json.load(f)
        self.assertIsInstance(daten, dict)

    def test_lade_einstellungen_rundtrip(self) -> None:
        """lade_einstellungen + speichere_einstellungen = identischer Inhalt."""
        if not os.path.isfile(self.PFAD):
            self.skipTest("einstellungen.json existiert nicht lokal")
        daten = K.lade_einstellungen()
        with tempfile.NamedTemporaryFile(
                suffix=".json", delete=False, dir=os.path.dirname(self.PFAD)) as tmp:
            tmp_pfad = tmp.name
        try:
            K.speichere_einstellungen(daten, pfad=tmp_pfad)
            with open(self.PFAD, encoding="utf-8") as f:
                original = json.load(f)
            with open(tmp_pfad, encoding="utf-8") as f:
                kopie = json.load(f)
            self.assertEqual(original, kopie)
            # Auch die temporaere Datei endet mit newline
            with open(tmp_pfad, "rb") as f:
                self.assertTrue(f.read().endswith(b"\n"))
        finally:
            if os.path.exists(tmp_pfad):
                os.remove(tmp_pfad)


class MappingFormatTest(unittest.TestCase):
    """mapping.json ist handgeschrieben (indent=2) — prueft nur Gueltigkeit."""

    PFAD = os.path.join(BASIS, "config", "mapping.json")

    def test_ist_gueltiges_json(self) -> None:
        with open(self.PFAD, encoding="utf-8") as f:
            daten = json.load(f)
        self.assertIsInstance(daten, dict)

    def test_endet_mit_newline(self) -> None:
        with open(self.PFAD, "rb") as f:
            content = f.read()
        self.assertTrue(content.endswith(b"\n"),
                        "mapping.json endet nicht mit \\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)