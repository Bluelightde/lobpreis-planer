#!/usr/bin/env python3
"""E2E-Test für den UI-Webserver: startet ui.py und testet die HTTP-Endpunkte."""

import http.client
import json
import os
import sys
import threading
import time
import unittest
from http.server import ThreadingHTTPServer

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASIS)
import lobpreis_planer as L  # noqa: E402
import ui                      # noqa: E402


def _freier_port():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class UIEndToEndTests(unittest.TestCase):
    """Startet den UI-Server auf einem zufälligen Port und testet die API."""

    @classmethod
    def setUpClass(cls):
        cls.port = _freier_port()
        cls.base = f"http://127.0.0.1:{cls.port}"
        # Kein Passwort für den Test
        ui.ZUGRIFF_PW = None
        cls.srv = ThreadingHTTPServer(("127.0.0.1", cls.port), ui.Handler)
        cls._srv_thread = threading.Thread(
            target=cls.srv.serve_forever, daemon=True)
        cls._srv_thread.start()
        time.sleep(0.1)  # Server braucht einen Moment

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls._srv_thread.join(timeout=2)

    def _get(self, pfad):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", pfad)
        r = conn.getresponse()
        body = r.read().decode("utf-8")
        conn.close()
        return r.status, body

    def _post(self, pfad, daten):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        body = json.dumps(daten).encode("utf-8")
        conn.request("POST", pfad, body=body,
                     headers={"Content-Type": "application/json"})
        r = conn.getresponse()
        resp_body = r.read().decode("utf-8")
        conn.close()
        return r.status, resp_body

    def test_static_index_html(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("<!DOCTYPE html>", body)

    def test_static_app_js(self):
        status, body = self._get("/app.js")
        self.assertEqual(status, 200)
        self.assertIn("function", body)

    def test_static_style_css(self):
        status, body = self._get("/style.css")
        self.assertEqual(status, 200)
        self.assertIn("font-family", body)

    def test_api_erzeugen_dd1(self):
        with open(os.path.join(BASIS, "besetzungen", "DD1.txt"),
                  encoding="utf-8") as f:
            text = f.read()
        status, body = self._post("/api/erzeugen",
                                  {"text": text, "name": "DD1"})
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data.get("ok"), f"Erwarte ok=True, bekam: {data}")
        self.assertEqual(data["kuerzel"], "DD1")
        self.assertIn("personen", data)
        self.assertIn("vorne", data)
        self.assertIn("hinten", data)
        self.assertIn("solo", data)
        self.assertIn("excel", data)
        self.assertIn("svg", data)
        self.assertIn("skizze_data", data)
        self.assertIn("excel_b64", data)
        # Keine Fehlzellen
        self.assertEqual(data.get("fehlend"), [])

    def test_api_erzeugen_magischen_text(self):
        text = "Lobpreisleitung: Micky Maus\nGesang DD1 1: Minnie Maus\nE-Git DD1: Goofy"
        status, body = self._post("/api/erzeugen",
                                  {"text": text, "name": "test"})
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data.get("ok"), f"Erwarte ok=True: {data}")
        self.assertEqual(data["kuerzel"], "DD1")
        self.assertEqual(len(data["personen"]), 3)

    def test_api_erzeugen_leeren_text(self):
        status, body = self._post("/api/erzeugen",
                                  {"text": "", "name": "leer"})
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data.get("ok"))
        self.assertEqual(data["kuerzel"], None)
        self.assertEqual(len(data["personen"]), 0)

    def test_api_nicht_gefunden(self):
        status, body = self._get("/api/gibts-nicht")
        self.assertEqual(status, 404)

    def test_api_einstellungen(self):
        status, body = self._get("/api/einstellungen")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("modus", data)
        self.assertIn("backline", data)
        self.assertIn("stagebox_kapazitaet", data)
        self.assertIn("dimensionen", data)

    def test_api_erzeugen_multitrack_setzt_track_aktiv(self):
        """Multitrack in der Besetzung -> /api/erzeugen liefert track_aktiv=True."""
        text = "Lobpreisleitung DD1: Anna\nGesang DD1 1: Anna\nMultitrack DD1: Bob"
        status, body = self._post("/api/erzeugen", {"text": text, "name": "mt"})
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data.get("ok"), f"Erwarte ok=True: {data}")
        self.assertTrue(data.get("track_aktiv"),
                        "track_aktiv muss True sein bei Multitrack in der Besetzung")

    def test_api_erzeugen_ohne_multitrack_track_aktiv_false(self):
        """Ohne Multitrack -> /api/erzeugen liefert track_aktiv=False."""
        text = "Lobpreisleitung DD1: Anna\nGesang DD1 1: Anna\nBass DD1: Bob"
        status, body = self._post("/api/erzeugen", {"text": text, "name": "ohne"})
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data.get("ok"), f"Erwarte ok=True: {data}")
        self.assertFalse(data.get("track_aktiv"),
                         "track_aktiv muss False sein ohne Multitrack")

    def test_api_basis_skizze(self):
        status, body = self._get("/api/basis_skizze")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("<svg", data.get("svg", ""))
        # Stageboxen muessen als ziehbare Elemente (data-key) auftauchen.
        self.assertIn("data-key='SB1'", data["svg"])
        self.assertIn("data-key='SB2'", data["svg"])
    def test_api_spitznamen(self):
        status, body = self._get("/api/spitznamen")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("spitznamen", data)

    def test_api_solo_personen(self):
        status, body = self._get("/api/solo_personen")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("solo_personen", data)
    def test_static_ct_js(self):
        """ct.js muss ladbar sein (Kalender-Logik). Ein Syntax-Fehler hier
           laesst den ganzen Modul-Graphen kollabieren → Kalender weg."""
        status, body = self._get("/ct.js")
        self.assertEqual(status, 200)
        self.assertIn("renderKalender", body)
        self.assertIn("export", body)

    def test_static_ui_js(self):
        """ui.js muss ladbar sein und patchWertSpeichern exportieren."""
        status, body = self._get("/ui.js")
        self.assertEqual(status, 200)
        self.assertIn("patchWertSpeichern", body)
        self.assertIn("export function patchWertSpeichern", body)
        # Sicherstellen dass kein export innerhalb einer Funktion steht
        # (das wuerde im Browser einen SyntaxError werfen, auch wenn
        # node --check es durchgehen laesst).
        self.assertNotIn("  export ", body)

    def test_static_app_js_imports_kalender(self):
        """app.js muss ct.js und ui.js korrekt importieren, damit der
           Kalender beim Laden der Seite erscheint."""
        status, body = self._get("/app.js")
        self.assertEqual(status, 200)
        self.assertIn("renderKalender", body)
        self.assertIn("patchWertSpeichern", body)
        self.assertIn("LETZTES", body)
    # ---- /api/regenerate: Excel + Scene muessen Edits enthalten ----

    def _excel_zellen(self, b64):
        """Liest alle Zellwerte aus einer base64-kodierten .xlsx-Datei."""
        import base64, io, zipfile
        from xml.etree import ElementTree as ET
        z = zipfile.ZipFile(io.BytesIO(base64.b64decode(b64)))
        sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        out: dict[str, str] = {}
        for c in sheet.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c"):
            ref = c.get("r", "")
            v = c.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v")
            is_el = c.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}is")
            if v is not None and v.text:
                out[ref] = v.text
            elif is_el is not None:
                t = is_el.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")
                if t is not None and t.text:
                    out[ref] = t.text
        return out

    def _regen(self, setzwerte, inputs, edits):
        """Hilfsfunktion: /api/regenerate mit gegebenen Daten."""
        status, body = self._post("/api/regenerate", {
            "plane_erg": {"setzwerte": setzwerte, "basis_inputs": inputs,
                          "excel": {"inputs": inputs}},
            "edits": {"inputs": edits},
        })
        self.assertEqual(status, 200, f"/api/regenerate fehlgeschlagen: {body[:200]}")
        return json.loads(body)

    def test_regenerate_label_aendert_excel_c_und_h(self):
        """Label/Mic-Edit: muss in Excel-Spalten C und H ankommen."""
        _, body = self._post("/api/erzeugen", {
            "text": "Gesang DD1 1: Emma\nGesang DD1 2: Greta\n",
            "name": "t",
        })
        r = json.loads(body)
        edits = []
        for e in r["excel"]["inputs"]:
            edits.append({"label": e.get("label"), "mic": e.get("mic"),
                          "sb1": e.get("sb1"), "sb2": e.get("sb2")})
        edits[0]["label"] = "EVA-X"
        edits[0]["mic"] = "SM58-X"

        regen = self._regen(r["setzwerte"], r["excel"]["inputs"], edits)
        zellen = self._excel_zellen(regen["excel_b64"])
        self.assertEqual(zellen.get("C5"), "EVA-X")
        self.assertEqual(zellen.get("H5"), "SM58-X")

    def test_regenerate_sb_wechsel_aendert_excel_f(self):
        """SB1-Wechsel: muss in Excel-Spalte F ankommen."""
        _, body = self._post("/api/erzeugen", {
            "text": "Gesang DD1 1: Emma\n",
            "name": "t",
        })
        r = json.loads(body)
        edits = []
        for e in r["excel"]["inputs"]:
            edits.append({"label": e.get("label"), "mic": e.get("mic"),
                          "sb1": e.get("sb1"), "sb2": e.get("sb2")})
        edits[0]["sb1"] = 6

        regen = self._regen(r["setzwerte"], r["excel"]["inputs"], edits)
        zellen = self._excel_zellen(regen["excel_b64"])
        self.assertEqual(zellen.get("F5"), "1")  # Reorder: Voc → Slot 1

    def test_regenerate_scene_source_folgt_sb(self):
        """Scene-Source muss der SB-Nummer folgen."""
        _, body = self._post("/api/erzeugen", {
            "text": "Gesang DD1 1: Emma\nGesang DD1 2: Greta\n",
            "name": "t",
        })
        r = json.loads(body)
        edits = []
        for e in r["excel"]["inputs"]:
            edits.append({"label": e.get("label"), "mic": e.get("mic"),
                          "sb1": e.get("sb1"), "sb2": e.get("sb2")})
        edits[0]["sb1"] = None
        edits[0]["sb2"] = True
        regen = self._regen(r["setzwerte"], r["excel"]["inputs"], edits)
        scene = regen.get("scene_data") or ""
        ch01 = next((l for l in scene.splitlines() if l.startswith("/ch/01/config")), "")
        self.assertTrue(ch01, "Scene Ch01 fehlt")
        source = int(ch01.split()[-1])
        self.assertIn(source, (1, 17))

    def test_regenerate_kein_edit_liefert_gleiche_bytes(self):
        """Regen ohne Edit: Excel-Bytes duerfen nicht kaputtgehen."""
        _, body = self._post("/api/erzeugen", {
            "text": "Gesang DD1 1: Emma\n",
            "name": "t",
        })
        r = json.loads(body)
        regen = self._regen(r["setzwerte"], r["excel"]["inputs"], [])
        zellen = self._excel_zellen(regen["excel_b64"])
        self.assertTrue(zellen.get("C5"))
        self.assertEqual(regen.get("fehlend"), [])
    # ----- /api/sitzungen: Konfigurationen speichern/laden/loeschen -----

    def setUp(self):
        # Deterministisch: sitzungen.json sichern und leeren.
        import shutil
        self._sitz_backup = None
        if os.path.isfile(L.SITZUNGEN):
            self._sitz_backup = L.SITZUNGEN + ".bak"
            shutil.copy2(L.SITZUNGEN, self._sitz_backup)
        if os.path.isfile(L.SITZUNGEN):
            os.remove(L.SITZUNGEN)

    def tearDown(self):
        if os.path.isfile(L.SITZUNGEN):
            os.remove(L.SITZUNGEN)
        if self._sitz_backup and os.path.isfile(self._sitz_backup):
            shutil.move(self._sitz_backup, L.SITZUNGEN)

    def test_sitzungen_leer_bei_start(self):
        """Ohne sitzungen.json liefert GET ein leeres Dict."""
        status, body = self._get("/api/sitzungen")
        self.assertEqual(status, 200)
        j = json.loads(body)
        self.assertEqual(j.get("sitzungen"), {})

    def test_sitzung_speichern_und_laden(self):
        """POST speichert eine Sitzung, GET liefert sie zurueck."""
        _, body = self._post("/api/sitzungen", {
            "aktion": "speichern", "name": "Testprofil",
            "besetzung_text": "Bass DD1: Alex\n",
            "setlist": [{"nr": "1", "lied": "Amazing Grace", "stimme": "Lead",
                         "instrument": "Gitarre", "bemerkung": ""}],
            "dateiname": "DD1",
            "haupt_pos": {"vorne_0": {"x": 100, "y": 200}},
            "input_edits": [{"zeile": 5, "label": "Test", "mic": "SM58",
                             "sb1": 1, "sb2": None}],
            "bus_edits": [{"bus": 1, "name": "Monitor 1"}],
        })
        j = json.loads(body)
        self.assertTrue(j.get("ok"), body)
        self.assertEqual(j.get("anzahl"), 1)

        status, body = self._get("/api/sitzungen")
        self.assertEqual(status, 200)
        j = json.loads(body)
        sitz = j["sitzungen"]
        self.assertIn("Testprofil", sitz)
        self.assertEqual(sitz["Testprofil"]["besetzung_text"], "Bass DD1: Alex\n")
        self.assertEqual(sitz["Testprofil"]["dateiname"], "DD1")
        self.assertEqual(len(sitz["Testprofil"]["setlist"]), 1)
        self.assertEqual(sitz["Testprofil"]["setlist"][0]["lied"], "Amazing Grace")
        self.assertEqual(sitz["Testprofil"]["haupt_pos"]["vorne_0"]["x"], 100)
        self.assertEqual(sitz["Testprofil"]["input_edits"][0]["zeile"], 5)
        self.assertEqual(sitz["Testprofil"]["bus_edits"][0]["name"], "Monitor 1")

    def test_sitzung_loeschen(self):
        """POST mit aktion=loeschen entfernt die Sitzung."""
        self._post("/api/sitzungen", {"aktion": "speichern", "name": "Weg",
                                       "besetzung_text": "", "setlist": []})
        _, body = self._get("/api/sitzungen")
        self.assertIn("Weg", json.loads(body)["sitzungen"])
        self._post("/api/sitzungen", {"aktion": "loeschen", "name": "Weg"})
        _, body = self._get("/api/sitzungen")
        self.assertEqual(json.loads(body)["sitzungen"], {})

    def test_sitzung_ohne_name_fehler(self):
        """Speichern ohne Name -> Fehler."""
        _, body = self._post("/api/sitzungen", {"aktion": "speichern", "name": "",
                                                 "besetzung_text": "", "setlist": []})
        j = json.loads(body)
        self.assertFalse(j.get("ok"))
        self.assertIn("Name", j.get("error", ""))

    def test_sitzung_unbekannte_aktion_fehler(self):
        """Unbekannte Aktion -> Fehler."""
        _, body = self._post("/api/sitzungen", {"aktion": "hacker", "name": "x"})
        j = json.loads(body)
        self.assertFalse(j.get("ok"))

    def test_sitzung_persistiert_auf_disk(self):
        """Speichern schreibt tatsaechlich sitzungen.json (atomar)."""
        self._post("/api/sitzungen", {"aktion": "speichern", "name": "Disk",
                                      "besetzung_text": "x", "setlist": [],
                                      "dateiname": "d", "haupt_pos": {},
                                      "input_edits": [], "bus_edits": []})
        self.assertTrue(os.path.isfile(L.SITZUNGEN))
        with open(L.SITZUNGEN, encoding="utf-8") as f:
            raw = json.load(f)
        self.assertIn("Disk", raw)
        # Atomar geschrieben: kein .tmp-File bleibt zurueck.
        self.assertFalse(os.path.isfile(L.SITZUNGEN + ".tmp"))

if __name__ == "__main__":
    unittest.main(verbosity=2)
