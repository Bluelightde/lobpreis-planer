#!/usr/bin/env python3
"""
Lobpreis-Planer -- Browser-Oberflaeche
======================================
Startet einen lokalen Webserver. Im Browser:
  - Besetzung einfuegen (oder eine gespeicherte laden)
  - "Erzeugen" -> Zuordnung + Buehnen-Vorschau ansehen
  - Skizze (.excalidraw) und Belegungsplan (.xlsx) herunterladen

Aufruf:
    python3 ui.py            # http://127.0.0.1:8765
    python3 ui.py --port 9000 --host 0.0.0.0   # im WLAN erreichbar

Nur Python-Standardbibliothek, keine Zusatzpakete.
"""

import argparse
import base64
import hmac
import json
import logging
import logging.handlers
import os
import sys
from typing import Any
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

BASIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASIS)
import lobpreis_planer as L  # noqa: E402
import churchtools as CT  # noqa: E402

BESETZUNGEN = os.path.join(BASIS, "besetzungen")

# Basis-Skizze im Einstellungs-Modal: zeigt das Standard-Buehnenbild, damit sich
# Standard-Positionen + Stageboxen ziehen lassen, ohne erst eine echte Besetzung
# zu laden. Das Lineup wird AUS DER KONFIG abgeleitet (instrument_rollen,
# leiter_rolle, sing_rollen), damit es den tatsaechlichen Standard widerspiegelt
# und mitwandert, wenn sich die Konfig aendert. Labels = Rollen (selbsterklaerend).
# MD ist keine eigene Box, sondern eine Zweitrolle der Piano-Person -> der
# MD-Kreis haengt an deren Box; TS haengt am Lobpreisleiter. Saengerzahl (3) ist
# eine reine Anzeige-Annahme (pro Dienst variabel, nicht in der Konfig).
def _basis_besetzung(cfg: dict[str, Any]) -> str:
    b: dict[str, Any] = cfg.get("buehne", {})
    leiter: str = b.get("leiter_rolle", "Lobpreisleitung")
    instrumente: list[str] = b.get("instrument_rollen", [])
    sing: str = (cfg.get("sing_rollen") or ["Gesang"])[0]
    zeilen: list[str] = [f"{leiter} BS1: {leiter}"]
    zeilen += [f"{instr} BS1: {instr}" for instr in instrumente]
    md_ziel: str = "Bass" if "Bass" in instrumente else (instrumente[0] if instrumente else leiter)
    zeilen.append(f"MD BS1: {md_ziel}")
    zeilen += [f"{sing} BS1 {i}: {sing} {i}" for i in range(1, 4)]
    return "\n".join(zeilen)

# Bei jeder relevanten Aenderung erhoehen -- macht im UI sichtbar, welche Version laeuft.
VERSION = "2026-06-11.13"

LOG_DATEI = os.path.join(BASIS, "lobpreis.log")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
rot_handler = logging.handlers.RotatingFileHandler(
    LOG_DATEI, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
rot_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logging.getLogger().addHandler(rot_handler)
log = logging.getLogger("lobpreis")

# Optionales Zugriffspasswort (Basic Auth); in main() gesetzt. None = offen.
ZUGRIFF_PW = None

# Shutdown-Timer: wird beim /api/shutdown gesetzt und bei jedem Request zurueckgesetzt.
_SHUTDOWN_TIMER = None


# --------------------------------------------------------------------------
# HTML-Seite (eine Datei, eingebettet)
# --------------------------------------------------------------------------

WEB_DIR = os.path.join(BASIS, "web")  # ausgelagertes Frontend


# --------------------------------------------------------------------------
# Shutdown-Verzoegerung: Bei Tab-Schliessen wird der Server verzögert beendet.
# Kommt innerhalb von 3s ein neuer Request (z.B. Reload), wird der Shutdown abgebrochen.
# --------------------------------------------------------------------------
import threading

_SHUTDOWN_DELAY = 3  # Sekunden
_SHUTDOWN_LOCK = threading.Lock()  # schuetzt _SHUTDOWN_TIMER ueber Request-Threads

def _cancel_shutdown_locked():
    """Bricht einen laufenden Timer ab. Aufrufer haelt _SHUTDOWN_LOCK."""
    global _SHUTDOWN_TIMER
    if _SHUTDOWN_TIMER is not None:
        _SHUTDOWN_TIMER.cancel()
        _SHUTDOWN_TIMER = None

def _starte_shutdown(srv):
    global _SHUTDOWN_TIMER
    with _SHUTDOWN_LOCK:
        _cancel_shutdown_locked()
        _SHUTDOWN_TIMER = threading.Timer(_SHUTDOWN_DELAY, srv.shutdown)
        _SHUTDOWN_TIMER.daemon = True
        _SHUTDOWN_TIMER.start()

def _breche_shutdown_ab():
    with _SHUTDOWN_LOCK:
        _cancel_shutdown_locked()


# --------------------------------------------------------------------------
# Server
# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        daten = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(daten)))
        self.end_headers()
        self.wfile.write(daten)

    def log_message(self, *a):
        pass  # ruhig bleiben

    def _auth_ok(self):
        """True, wenn kein Passwort gesetzt ist oder die Basic-Auth passt."""
        if not ZUGRIFF_PW:
            return True
        kopf = self.headers.get("Authorization", "")
        if kopf.startswith("Basic "):
            try:
                roh = base64.b64decode(kopf[6:]).decode("utf-8", "replace")
                _, _, pw = roh.partition(":")
                if hmac.compare_digest(pw, ZUGRIFF_PW):
                    return True
            except Exception:  # noqa: BLE001
                pass
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Lobpreis-Planer"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def _fehler(self, kontext, e, code=200):
        """Loggt die Ursache (mit Traceback) und gibt eine knappe Meldung zurueck."""
        log.exception("Fehler bei %s", kontext)
        self._json({"ok": False, "error": f"{type(e).__name__}: {e}"}, code)

    def _serve_static(self, dateiname, content_type):
        """Liefert eine Datei aus web/ aus (frisch von der Platte -> kein Neustart noetig)."""
        pfad = os.path.join(WEB_DIR, dateiname)
        try:
            with open(pfad, "rb") as f:
                daten = f.read()
        except FileNotFoundError:
            self._json({"error": f"{dateiname} nicht gefunden"}, 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(daten)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.end_headers()
        self.wfile.write(daten)

    def _einstellungen_slice(self):
        """Editierbarer Ausschnitt der (gemergten) Konfig fuer das Regeln-Formular."""
        cfg = L.lade_konfig()
        b = cfg.get("buehne", {})

        def nimm(d, keys):
            return {k: d.get(k) for k in keys}

        bl = {}
        for n, v in b.get("backline", {}).items():
            if isinstance(v, dict):
                bl[n] = nimm(v, ("immer", "backline_ab_saengern", "x", "y", "w", "h"))
        dim = b.get("dimensionen") or {}
        t_w, t_h = L.vorlage_buehne_groesse(b.get("buehne_rect_id", ""))
        return {
            "modus": {k: v for k, v in (cfg.get("modus") or {}).items() if not k.startswith("_")},
            "backline_reihenfolge": b.get("backline_reihenfolge", []),
            "backline": bl,
            "unter_drums": nimm(b.get("unter_drums", {}), ("offset_y", "rollen", "w", "h")),
            "solo_platz": nimm(b.get("solo_platz", {}), ("x", "y", "w", "h", "stapel_dy")),
            "vorne": nimm(b.get("vorne", {}), ("y", "h", "min_box_w", "max_box_w", "rand", "luecke")),
            "track_aktiv": bool((cfg.get("excel") or {}).get("track_aktiv", False)),
            "stagebox_kapazitaet": int((cfg.get("excel") or {}).get("stagebox_kapazitaet", 16)),
            "dimensionen": {
                "breite": round(dim.get("breite") if dim.get("breite") is not None else t_w),
                "hoehe": round(dim.get("hoehe") if dim.get("hoehe") is not None else t_h),
            },
        }

    def do_GET(self):
        _breche_shutdown_ab()
        if not self._auth_ok():
            return
        weg = urlparse(self.path)
        if weg.path in ("/", "/index.html"):
            self._serve_static("index.html", "text/html; charset=utf-8")
        elif weg.path == "/style.css":
            self._serve_static("style.css", "text/css; charset=utf-8")
        elif weg.path == "/app.js":
            self._serve_static("app.js", "application/javascript; charset=utf-8")
        elif weg.path == "/ct.js":
            self._serve_static("ct.js", "application/javascript; charset=utf-8")
        elif weg.path == "/ui.js":
            self._serve_static("ui.js", "application/javascript; charset=utf-8")
        elif weg.path == "/favicon.svg":
            self._serve_static("favicon.svg", "image/svg+xml")
        elif weg.path == "/api/liste":
            try:
                dateien = sorted(os.listdir(BESETZUNGEN))
            except FileNotFoundError:
                dateien = []
            self._json({"dateien": dateien})
        elif weg.path == "/api/laden":
            name = (parse_qs(weg.query).get("name") or [""])[0]
            pfad = os.path.join(BESETZUNGEN, os.path.basename(name))
            if os.path.isfile(pfad):
                with open(pfad, encoding="utf-8") as f:
                    self._json({"text": f.read()})
            else:
                self._json({"text": ""}, 404)
        elif weg.path == "/api/spitznamen":
            self._json({"spitznamen": L.lade_spitznamen()})
        elif weg.path == "/api/solo_personen":
            self._json({"solo_personen": L.lade_solo_personen()})
        elif weg.path == "/api/einstellungen":
            self._json(self._einstellungen_slice())
        elif weg.path == "/api/basis_skizze":
            try:
                cfg = L.lade_konfig()
                # Basis-Skizze: Felder einzeilig beschriften (nur das Instrument/der
                # Name, kein zusaetzliches Rollen-Kuerzel -> keine "Bass/Bass"-Dopplung).
                b = cfg.get("buehne", {})
                cfg["label_ausblenden"] = list(
                    set(cfg.get("label_ausblenden", []))
                    | set(cfg.get("rollen_kurz", {}).keys())
                    | set(b.get("instrument_rollen", []))
                    | set(cfg.get("sing_rollen", ["Gesang"]))
                    | {b.get("leiter_rolle", "Lobpreisleitung"), "MD", "Solo", "Geige"}
                )
                r = L.plane(_basis_besetzung(cfg), cfg,
                            L.lade_spitznamen(), L.lade_solo_personen(),
                            stapel_skizze=True)
                self._json({"svg": r.get("svg", "")})
            except Exception as e:  # noqa: BLE001
                self._fehler("/api/basis_skizze", e)
        elif weg.path == "/api/ct/status":
            c = L.lade_churchtools()
            token = (c.get("token") or "").strip()
            config_da = os.path.isfile(L.CHURCHTOOLS) or os.path.isfile(L.CHURCHTOOLS_ALT)
            log.info("CT Status: token=%s config_da=%s ssl_verify=%s", bool(token), config_da, c.get("ssl_verify"))
            status: dict[str, Any] = {"base_url": c.get("base_url"), "gruppe": c.get("gruppe"),
                                       "hat_token": bool(token),
                                       "config_vorhanden": config_da, "version": VERSION}
            if token:
                try:
                    ct = CT.CT(c["base_url"], token=token, ssl_verify=c.get("ssl_verify", True))
                    ct.servicegroups()
                    status["token_ok"] = True
                except CT.ChurchToolsAuthFehler:
                    status["token_ok"] = False
                except Exception:
                    pass
            self._json(status)
        elif weg.path == "/api/ct/events":
            c = L.lade_churchtools()
            if not (c.get("token") or "").strip():
                self._json({"ok": False, "error": "Kein Token konfiguriert."})
                return
            q = parse_qs(weg.query)
            von = (q.get("von") or [""])[0]
            bis = (q.get("bis") or [von])[0]
            log.info("CT Events abfragen: %s bis %s", von, bis)
            try:
                ct = CT.CT(c["base_url"], token=c.get("token"), ssl_verify=c.get("ssl_verify", True))
                events = CT.termin_liste(ct, von, bis, nur_gruppe=c.get("gruppe", "Lobpreis"),
                                         markiere_dienst=c.get("markier_dienst", ""))
                self._json({"ok": True, "events": events})
            except CT.ChurchToolsAuthFehler:
                self._json({"ok": False, "error": "Token ungültig oder abgelaufen."})
            except Exception as e:  # noqa: BLE001
                self._fehler("/api/ct/events", e)
        elif weg.path == "/api/ct/laden":
            eid = (parse_qs(weg.query).get("event") or [""])[0]
            c = L.lade_churchtools()
            if not (c.get("token") or "").strip():
                self._json({"ok": False, "error": "Kein Token konfiguriert."})
                return
            log.info("CT Besetzung laden: Event %s", eid)
            try:
                ct = CT.CT(c["base_url"], token=c.get("token"), ssl_verify=c.get("ssl_verify", True))
                text = CT.besetzung_text(ct, eid, c.get("gruppe", "Lobpreis"))
                self._json({"ok": True, "text": text})
            except CT.ChurchToolsAuthFehler:
                self._json({"ok": False, "error": "Token ungültig."})
            except Exception as e:  # noqa: BLE001
                self._fehler("/api/ct/laden", e)
        elif weg.path == "/api/ct/setliste":
            eid = (parse_qs(weg.query).get("event") or [""])[0]
            c = L.lade_churchtools()
            if not (c.get("token") or "").strip():
                self._json({"ok": False, "error": "Kein Token konfiguriert."})
                return
            try:
                ct = CT.CT(c["base_url"], token=c.get("token"), ssl_verify=c.get("ssl_verify", True))
                text = CT.setliste_text(ct, eid)
                self._json({"ok": True, "text": text})
            except CT.ChurchToolsAuthFehler:
                self._json({"ok": False, "error": "Token ungültig."})
            except Exception as e:  # noqa: BLE001
                self._fehler("/api/ct/setliste", e)
        else:
            self._json({"error": "nicht gefunden"}, 404)

    def do_POST(self):
        pfad = urlparse(self.path).path

        # Server-Shutdown: wird vom Browser bei Tab-Schliessen per sendBeacon() ausgeloest.
        # Muss VOR der Auth-Pruefung stehen, da sendBeacon keine Basic-Auth-Header sendet.
        # Shutdown wird verzögert (3s) – kommt ein neuer Request, wird er abgebrochen.
        if pfad == "/api/shutdown":
            log.info("Shutdown angefordert")
            self._json({"ok": True})
            _starte_shutdown(self.server)
            return

        if not self._auth_ok():
            return
        try:
            laenge = int(self.headers.get("Content-Length", 0) or 0)
            body = json.loads(self.rfile.read(laenge) or b"{}") if laenge else {}
        except (ValueError, TypeError) as e:
            # Ungueltiges Content-Length oder kaputtes JSON -> klare JSON-Antwort
            # statt unbehandelter Exception im Handler-Thread.
            return self._fehler(pfad, e, code=400)

        if pfad == "/api/ct/token":
            try:
                c = L.lade_churchtools()
                c["token"] = str(body.get("token", "")).strip()
                if body.get("base_url"):
                    c["base_url"] = str(body["base_url"]).strip().rstrip("/")
                L.speichere_churchtools(c)
                self._json({"ok": True})
            except Exception as e:  # noqa: BLE001
                self._fehler("/api/ct/token", e)
            return

        if pfad in ("/api/spitznamen", "/api/solo_personen"):
            schluessel = "spitznamen" if pfad.endswith("spitznamen") else "solo_personen"
            speichern = L.speichere_spitznamen if schluessel == "spitznamen" else L.speichere_solo_personen
            try:
                daten = {str(k).strip(): str(v).strip()
                         for k, v in (body.get(schluessel) or {}).items()
                         if str(k).strip() and str(v).strip()}
                speichern(daten)
                self._json({"ok": True, "anzahl": len(daten)})
            except Exception as e:  # noqa: BLE001
                self._fehler("/api/" + schluessel, e)
            return

        if pfad == "/api/einstellungen":
            try:
                ein = L.lade_einstellungen()
                ein.setdefault("buehne", {})
                aktion = body.get("aktion")
                if aktion == "form":
                    ein["modus"] = body.get("modus", {})
                    bl = ein["buehne"].setdefault("backline", {})
                    for instr, vals in (body.get("backline") or {}).items():
                        bl.setdefault(instr, {}).update(vals)
                    kap = body.get("stagebox_kapazitaet")
                    if kap is not None:
                        # Vorlage hat 16 Patch-Zeilen je Box; A-Bank fasst 32 -> max 16/Box.
                        ein.setdefault("excel", {})["stagebox_kapazitaet"] = max(1, min(16, int(kap)))
                    dim = body.get("dimensionen")
                    if isinstance(dim, dict):
                        zd = ein["buehne"].setdefault("dimensionen", {})
                        for k in ("breite", "hoehe"):
                            v = dim.get(k)
                            zd[k] = max(100, int(v)) if v is not None else None
                    sr = body.get("stapel_rollen")
                    if isinstance(sr, list):
                        # Welche Instrumente im Stapel (unter_drums) liegen -> als Gruppe.
                        ein["buehne"].setdefault("unter_drums", {})["rollen"] = [str(x) for x in sr]
                elif aktion == "position":
                    pos = ein["buehne"].setdefault("positionen", {})
                    pos[body["key"]] = {"x": body.get("x"), "y": body.get("y")}
                elif aktion == "vorne_y":
                    pos = ein["buehne"].setdefault("positionen", {})
                    pos["vorne"] = {"y": body.get("y")}
                elif aktion == "reset_positionen":
                    ein["buehne"].pop("positionen", None)
                elif aktion == "track":
                    ein.setdefault("excel", {})["track_aktiv"] = bool(body.get("aktiv"))
                else:
                    return self._json({"ok": False, "error": "unbekannte Aktion"})
                L.speichere_einstellungen(ein)
                self._json({"ok": True})
            except Exception as e:  # noqa: BLE001
                self._fehler("/api/einstellungen", e)
            return

        if pfad == "/api/regenerate":
            # Wird vom Browser aufgerufen, wenn der User im Patchlisten-
 # Formular Kanal-Name, Mic oder Stagebox-Slot aendert. Wir nehmen
 # den vom Client mitgeschickten plane-erg-Teil (setzwerte + excel)
 # und die Edits, rendern neue Excel/Scene-Bytes, und schicken sie
 # zurueck. plane() wird NICHT erneut ausgefuehrt.
            try:
                plane_erg: dict[str, Any] = body.get("plane_erg") or {}
                if not plane_erg.get("setzwerte"):
                    return self._json({"ok": False,
                        "error": "plane_erg.setzwerte fehlt -- erst /api/erzeugen aufrufen."})
                edits: dict[str, Any] = body.get("edits") or {}
                cfg: dict[str, Any] = L.lade_konfig()
                log.info("Regenerate: %d input-edits, %d bus-edits",
                         len(edits.get("inputs") or []),
                         len(edits.get("busse") or []))
                regen: dict[str, Any] = L.regeneriere_excel_und_scene(
                    plane_erg, cfg, edits,
                    L.lade_spitznamen(), L.lade_solo_personen())
                self._json({
                    "ok": True,
                    "excel": regen["excel"],
                    "setzwerte": regen.get("setzwerte", {}),  # fuer Folge-Edits
                    "excel_b64": base64.b64encode(regen["excel_bytes"]).decode("ascii"),
                    "scene_data": regen.get("scene_text"),
                    "scene": regen.get("scene") or {},
                    "fehlend": regen.get("fehlend") or [],
                })
            except Exception as e:  # noqa: BLE001
                self._fehler("/api/regenerate", e)
            return

        if pfad != "/api/erzeugen":
            return self._json({"error": "nicht gefunden"}, 404)
        try:
            text = body.get("text", "")
            name = (body.get("name") or "besetzung").strip() or "besetzung"
            log.info("Erzeuge Plan fuer '%s' (%d Zeilen)", name, text.count("\n") + 1)

            cfg = L.lade_konfig()
            # Transiente Positionen der Hauptseite (nur fuer DIESE Generierung,
            # werden NICHT in einstellungen.json gespeichert -> Default bleibt unberuehrt).
            pos = body.get("positionen")
            if isinstance(pos, dict):
                zp = cfg["buehne"].setdefault("positionen", {})
                for k, v in pos.items():
                    if isinstance(v, dict) and v.get("x") is not None:
                        zp[k] = {"x": v["x"], "y": v.get("y")}
            r = L.plane(text, cfg, L.lade_spitznamen(), L.lade_solo_personen())
            log.info("Plan erzeugt: %d Personen, %d fehlend", len(r.get("personen", [])), len(r.get("fehlend", [])))
            self._json({
                "ok": True,
                "kuerzel": r["kuerzel"],
                "personen": r["personen"],
                "vorne": r["vorne"],
                "hinten": r["hinten"],
                "solo": r["solo"],
                "excel": r["excel"],
                "setzwerte": r.get("setzwerte", {}),  # fuer /api/regenerate
                "fehlend": r["fehlend"],
                "svg": r["svg"],
                "skizze_name": f"{name}_Skizze.excalidraw",
                "skizze_data": json.dumps(r["skizze_doc"], ensure_ascii=False, indent=1),
                "excel_name": f"{name}_Belegungsplan.xlsx",
                "excel_b64": base64.b64encode(r["excel_bytes"]).decode("ascii"),
                "scene": r.get("scene") or {},
                "scene_name": f"{name}.scn" if r.get("scene_text") else None,
                "scene_data": r.get("scene_text"),
            })
        except Exception as e:  # noqa: BLE001
            self._fehler("/api/erzeugen", e)


def main():
    global ZUGRIFF_PW
    ap = argparse.ArgumentParser(description="Lobpreis-Planer Browser-Oberflaeche")
    ap.add_argument("--host", default="127.0.0.1", help="Host (0.0.0.0 = im Netzwerk erreichbar)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--password", default=os.environ.get("LP_PASSWORD"),
                    help="Optionales Zugriffspasswort (HTTP Basic Auth). Empfohlen bei --host 0.0.0.0.")
    args = ap.parse_args()

    # Vorlagen-Selbstcheck: lieber sofort klar scheitern als spaeter still falsch.
    try:
        L.pruefe_vorlagen()
    except L.VorlagenFehler as e:
        raise SystemExit(str(e))

    ZUGRIFF_PW = (args.password or "").strip() or None
    lokal = args.host in ("127.0.0.1", "localhost", "::1")
    if not lokal and not ZUGRIFF_PW:
        print("⚠  WARNUNG: Server ist im Netzwerk erreichbar (--host " + args.host + "), "
              "aber OHNE Passwort. Jeder im Netz kann zugreifen.\n"
              "   Empfehlung: mit --password <PW> starten (oder Umgebungsvariable LP_PASSWORD).")

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{'127.0.0.1' if args.host=='0.0.0.0' else args.host}:{args.port}"
    log.info("Server gestartet auf %s", url)
    print(f"Lobpreis-Planer laeuft auf {url}")
    if ZUGRIFF_PW:
        print("Zugriff ist passwortgeschuetzt (Basic Auth).")
    print("Im Browser oeffnen. Beenden mit Strg+C.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    log.info("Server beendet.")
    print("\nBeendet.")
    srv.server_close()


if __name__ == "__main__":
    main()
