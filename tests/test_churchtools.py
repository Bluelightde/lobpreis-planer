#!/usr/bin/env python3
"""Verhaltenstests fuer churchtools.setliste_text().

Synthetische Agenda-Fixtures (keine echten Personendaten) decken die
Parsing-Zweige ab: responsible (str/dict-text/persons/list), Notiz-Parsing
(Stimmen-Praefix inkl. 'Leadvoc'-Abkuerzung, Instrumente, Verneinung,
Bemerkungen, Dedup, Trennzeichen) und den Titel-Fallback. Erwartete Ausgaben
sind explizit -- der Test dokumentiert das gewuenschte Verhalten, nicht nur den
Ist-Zustand.

    python3 tests/test_churchtools.py
"""

import os
import sys
import unittest

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASIS)
import churchtools as CT  # noqa: E402


class FakeCT:
    """Minimaler CT-Ersatz: liefert eine vorgegebene Agenda, ohne Netz."""

    def __init__(self, agenda=None, fehler=False):
        self._agenda = agenda
        self._fehler = fehler

    def agenda(self, event_id):
        if self._fehler:
            raise CT.ChurchToolsFehler("simulierter HTTP 404")
        return self._agenda


def song(title="", responsible=None, note="", song_title=None):
    it = {"type": "song", "title": title, "note": note}
    if responsible is not None:
        it["responsible"] = responsible
    if song_title is not None:
        it["song"] = {"title": song_title}
    return it


def lauf(*items):
    return CT.setliste_text(FakeCT({"items": list(items)}), 1)


class SetlisteTextTests(unittest.TestCase):

    def test_leadvoc_abkuerzung(self):
        # Regressionswaechter: 'Leadvoc' (ohne 'al') muss als Stimmen-Praefix
        # erkannt werden; 'Intro' darf nicht als Saenger landen.
        txt = lauf(song("Good Plans", {"text": "", "persons": []},
                        "Leadvoc: Nastya\nLead: A-Gitarre Intro"))
        self.assertEqual(txt, "- Good Plans (Nastya, A-Gitarre)")

    def test_responsible_text_komma_zu_und(self):
        # responsible.text mit Komma -> EIN Feld mit ' & '; Bemerkungen ohne ';;'.
        txt = lauf(song("Es ist vollbracht", {"text": "Konsti, Nin"},
                        "Intro mit Synth; \nAlle stark"))
        self.assertEqual(
            txt, "- Es ist vollbracht (Konsti & Nin, Synth, [Intro mit Synth; Alle stark])")

    def test_verneinung_unterdrueckt_instrument(self):
        # 'ohne Drums' -> Drums NICHT als Instrument; Zeile bleibt Bemerkung.
        txt = lauf(song("Gott mein Fels", "Felix", "ohne Drums, Felix singt vorn"))
        self.assertEqual(
            txt, "- Gott mein Fels (Felix, [ohne Drums, Felix singt vorn])")

    def test_titel_fallback_auf_song_title(self):
        txt = lauf(song("", {"text": "", "persons": []}, "", song_title="10,000 Reasons"))
        self.assertEqual(txt, "- 10,000 Reasons")

    def test_instrument_dedup(self):
        # 'Piano' zweimal genannt -> nur einmal im Instrument-Feld.
        txt = lauf(song("King", {"text": "", "persons": []}, "Lead: Piano\nIntro Piano"))
        self.assertEqual(txt, "- King (Piano, [Intro Piano])")

    def test_responsible_personenliste(self):
        txt = lauf(song("Song", {"text": "", "persons": [{"name": "Emma"}, {"name": "Ida"}]}))
        self.assertEqual(txt, "- Song (Emma & Ida)")

    def test_responsible_firstname_lastname(self):
        txt = lauf(song("Song", {"persons": [{"firstName": "Emma", "lastName": "Becker"}]}))
        self.assertEqual(txt, "- Song (Emma Becker)")

    def test_nur_songs_zaehlen(self):
        txt = lauf({"type": "header", "title": "Begruessung"},
                   song("Lied", "Greta"))
        self.assertEqual(txt, "- Lied (Greta)")

    def test_unbekannter_song(self):
        txt = lauf(song("", {"text": "", "persons": []}))
        self.assertEqual(txt, "- Unbekannter Song")

    def test_agenda_fehler_ergibt_leer(self):
        self.assertEqual(CT.setliste_text(FakeCT(fehler=True), 1), "")

    def test_mehrere_songs_reihenfolge(self):
        txt = lauf(song("A", "Greta"), song("B", "Felix"))
        self.assertEqual(txt, "- A (Greta)\n- B (Felix)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
