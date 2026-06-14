#!/usr/bin/env python3
"""
ChurchTools-Anbindung (nur Python-Standardbibliothek).

Holt aus der Dienstplanung (Dienstgruppe "Lobpreis") die Besetzung eines
Termins und liefert sie im Eingabeformat des Lobpreis-Planers, z.B.:
    Lobpreisleitung DD1: Emma Meier
    Gesang DD1 1: Emma Meier

Authentifizierung: persoenlicher Login-Token (ChurchTools -> eigenes Profil ->
"Berechtigungen"/API) oder alternativ Benutzername/Passwort.
"""

import http.cookiejar
import json
import re
import urllib.parse
import ssl
import urllib.request


class ChurchToolsFehler(Exception):
    """Basisklasse für alle CT-Fehler."""
    pass


class ChurchToolsAuthFehler(ChurchToolsFehler):
    """Authentifizierung fehlgeschlagen (falsches Token/Passwort, 401)."""
    pass


class ChurchToolsNetzwerkFehler(ChurchToolsFehler):
    """Verbindungs-/Netzwerkfehler (Timeout, DNS, Connection Refused)."""
    pass


class ChurchToolsServerFehler(ChurchToolsFehler):
    """Server-seitiger Fehler (5xx)."""
    pass


class ChurchToolsNichtGefunden(ChurchToolsFehler):
    """Ressource nicht gefunden (404)."""
    pass

def _ssl_fehler(path: str, e: Exception) -> str:
    """Baut eine verstaendliche Fehlermeldung fuer SSL-Fehler."""
    return (
        f"SSL-Fehler bei {path}: Das Zertifikat des ChurchTools-Servers "
        f"konnte nicht ueberprueft werden. Haeufig bei selbst-signierten "
        f"Zertifikaten oder wenn das Root-CA-Zertifikat fehlt.\n"
        f"Loesung: 'ssl_verify: false' in config/config.json setzen "
        f"(nur im vertrauenswuerdigen Netzwerk!)"
    )


class CT:
    def __init__(self, base_url, token=None, username=None, password=None, timeout=20, ssl_verify=True):
        self.base = (base_url or "").rstrip("/")
        self.token = token or None
        self.timeout = timeout
        ctx: ssl.SSLContext | None = None
        if not ssl_verify:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
            urllib.request.HTTPSHandler(context=ctx))

    def _login(self, username, password):
        body = json.dumps({"username": username, "password": password}).encode("utf-8")
        req = urllib.request.Request(self.base + "/api/login", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            self.opener.open(req, timeout=self.timeout).read()
        except urllib.error.HTTPError as e:
            raise ChurchToolsAuthFehler(
                f"Login fehlgeschlagen: HTTP {e.code}")
        except OSError as e:
            raise ChurchToolsNetzwerkFehler(
                f"Login: Server nicht erreichbar ({e})")
        except Exception as e:
            raise ChurchToolsFehler(f"Login fehlgeschlagen: {e}")

    def get(self, path, **params):
        if self.token:
            params.setdefault("login_token", self.token)
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with self.opener.open(req, timeout=self.timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 401 or e.code == 403:
                raise ChurchToolsAuthFehler(
                    f"HTTP {e.code} bei {path} (Token abgelaufen/Rechte fehlen)")
            elif e.code == 404:
                raise ChurchToolsNichtGefunden(
                    f"HTTP 404 bei {path} (nicht gefunden)")
            elif 500 <= e.code < 600:
                raise ChurchToolsServerFehler(
                    f"HTTP {e.code} bei {path} (Server-Fehler)")
            else:
                raise ChurchToolsFehler(
                    f"HTTP {e.code} bei {path}")
        except (urllib.error.URLError, OSError) as e:
            grund: str | Exception = e
            if isinstance(e, urllib.error.URLError) and isinstance(e.reason, ssl.SSLError):
                grund = e.reason
            raise ChurchToolsNetzwerkFehler(_ssl_fehler(path, grund))

    # -- Endpunkte ----------------------------------------------------------
    def _data(self, obj):
        return obj.get("data", obj) if isinstance(obj, dict) else obj

    def servicegroups(self):
        return self._data(self.get("/api/servicegroups"))

    def services(self):
        return self._data(self.get("/api/services"))

    def events(self, von):
        # Nur 'from': 'to' wuerde den Starttag abschneiden (Events starten 08:00Z,
        # 'to'=Tagesbeginn) -> wir filtern den Tag/Bereich clientseitig.
        return self._data(self.get("/api/events", **{"from": von}))

    def event(self, event_id):
        return self._data(self.get(f"/api/events/{event_id}"))

    def agenda(self, event_id):
        return self._data(self.get(f"/api/events/{event_id}/agenda"))


def whoami(ct):
    """Person-ID der eingeloggten Person (des Tokens) oder None."""
    try:
        me = ct._data(ct.get("/api/whoami"))
        return me.get("id") if isinstance(me, dict) else None
    except ChurchToolsFehler:
        return None


def termin_liste(ct, von, bis=None, nur_gruppe=None,
                 markiere_dienst="", meine_person_id=None):
    """Liste von {id, label, datum, meins, dienste} fuer die Termin-Auswahl, gefiltert
       auf [von, bis]. Mit nur_gruppe nur Termine, die Dienste dieser Gruppe haben.

       'dienste' = die Dienste, in denen die eingeloggte Person (meine_person_id, sonst
       whoami) an diesem Termin eingeteilt ist; 'meins'=True, sobald es mindestens einen
       gibt. So sieht jede Person -- egal welcher Token eingetragen ist -- ihre eigenen
       Termine hervorgehoben. Mit markiere_dienst (Namens-Teilstring, z.B.
       'Tontechnikleiter') laesst sich optional auf bestimmte Dienste einschraenken."""
    bis = bis or von
    gid = None
    if nur_gruppe:
        grp = next((g for g in ct.servicegroups() if g.get("name") == nur_gruppe), None)
        gid = grp.get("id") if grp else None
    svc = {s.get("id"): s for s in ct.services()}
    if meine_person_id is None:
        meine_person_id = whoami(ct)
    marker = (markiere_dienst or "").lower()

    out = []
    for ev in ct.events(von):
        sd = ev.get("startDate") or ev.get("start") or ""
        tag = sd[:10]
        if von and tag and not (von <= tag <= bis):
            continue
        det = None
        if gid is not None or meine_person_id:
            det = ct.event(ev.get("id"))
        if gid is not None:
            hat = any(svc.get(es.get("serviceId"), {}).get("serviceGroupId") == gid
                      for es in (det.get("eventServices") or []))
            if not hat:
                continue
        dienste = []
        if det is not None and meine_person_id:
            for es in det.get("eventServices") or []:
                if es.get("personId") != meine_person_id:
                    continue
                name = (svc.get(es.get("serviceId"), {}).get("name", "") or "").strip()
                if name and (not marker or marker in name.lower()) and name not in dienste:
                    dienste.append(name)
        out.append({"id": ev.get("id"),
                    "datum": tag,
                    "label": f"{sd[:16].replace('T', ' ')} – {ev.get('name', '')}".strip(" –"),
                    "meins": bool(dienste),
                    "dienste": dienste})
    return out


def besetzung_text(ct, event_id, gruppe="Lobpreis"):
    """Baut den Besetzungs-Text aus den Diensten der angegebenen Gruppe.
       Mehrfach besetzte Dienste (z.B. 'Gesang DD1') werden durchnummeriert
       ('Gesang DD1 1', 'Gesang DD1 2', ...), damit das Voc-Mapping greift."""
    grp = next((g for g in ct.servicegroups() if g.get("name") == gruppe), None)
    gid = grp.get("id") if grp else None
    svc = {s.get("id"): s for s in ct.services()}

    eintraege = []  # (service_name, serviceId, person)
    for es in ct.event(event_id).get("eventServices", []) or []:
        s = svc.get(es.get("serviceId"))
        if not s or (gid is not None and s.get("serviceGroupId") != gid):
            continue
        person = es.get("name") or es.get("personName") or "?"
        eintraege.append((s.get("name", ""), es.get("serviceId"), person))

    anzahl = {}
    for _, sid, _ in eintraege:
        anzahl[sid] = anzahl.get(sid, 0) + 1

    laufend = {}
    zeilen = []
    for name, sid, person in eintraege:
        if anzahl.get(sid, 0) > 1:  # mehrfach -> durchnummerieren
            laufend[sid] = laufend.get(sid, 0) + 1
            zeilen.append(f"{name} {laufend[sid]}: {person}")
        else:
            zeilen.append(f"{name}: {person}")
    return "\n".join(zeilen)


# Praefix vor einer Stimmen-Angabe in der Notiz: "Lead", "Leadvocal", "Voc:",
# "Vocal(s):", "Vox:", "Saenger(in):", sowie "Gesang:"/"Stimme:" (nur mit Doppelpunkt,
# damit Prosa wie "Gesang einsetzen" NICHT als Stimme zaehlt). "Leader"/"Leadinstr"
# bleiben dank \b unangetastet.
_STIMME_PREFIX = re.compile(
    r"^(?:(?:lead(?:stimme|gesang|voc(?:al)?s?|s[äa]nger(?:in)?)?|voc(?:al)?s?|vox|s[äa]nger(?:in)?)"
    r"\b[\s:.\-]*"
    r"|(?:gesang|stimme)\s*[:.\-]+\s*)", re.IGNORECASE)
# Erkannte Instrumente -- NUR diese landen im Instrument-Feld der Setliste.
_INSTRUMENTE = re.compile(
    r"\b(klavier|piano|keys?|keyboard|synth(?:esizer)?|pad|"
    r"e-?gitarre|e-?git|a-?gitarre|a-?git|gitarre|git|"
    r"bass|drums|schlagzeug|cajon|percussion|perc|"
    r"geige|violine|viola|bratsche|cello|kontrabass|"
    r"orgel|fl[öo]te|saxoph?on|sax|trompete|posaune|klarinette|"
    r"mandoline|ukulele|harfe|akkordeon)\b", re.IGNORECASE)
# Verneinung direkt vor einem Instrument ("ohne Drums") -> Instrument ignorieren.
_NEG_VOR = re.compile(r"(?:ohne|kein[e]?|nicht)\s+$", re.IGNORECASE)


def _instrumente_aus(text):
    """Echte Instrumente aus einem Text ziehen; eine Verneinung direkt davor
       ('ohne Drums') wird ignoriert."""
    out = []
    for m in _INSTRUMENTE.finditer(text):
        if _NEG_VOR.search(text[:m.start()]):
            continue
        out.append(m.group(0).strip())
    return out


def _ist_bemerkung(rohzeile, rest_zeile):
    """True, wenn eine Notizzeile als Bemerkung uebernommen werden soll: entweder
       enthaelt sie ein Schluesselwort, ODER nach Entfernen der Instrumente bleibt
       noch beschreibender Text uebrig (z.B. 'Felix singt vorn', 'ohne Drums').
       Reine Instrument-Zeilen ('Instr: EGit') liefern False -> keine Doppelung."""
    if re.search(r"gesang|start mit|intro|zwischenspiel", rohzeile, re.IGNORECASE):
        return True
    rest = _INSTRUMENTE.sub(" ", rest_zeile)
    rest = re.sub(r"[^A-Za-zÄÖÜäöüß]+", " ", rest).strip()
    return bool(rest)


def setliste_text(ct, event_id):
    """Holt den Ablaufplan und extrahiert Songs sowie deren Besetzung (Hauptstimme aus Zuständig/Responsible, Hauptinstrument aus Notiz)."""
    try:
        ag = ct.agenda(event_id)
    except ChurchToolsFehler:
        return ""
    
    items = ag.get("items") or []
    
    zeilen = []
    for it in items:
        if it.get("type") != "song":
            continue
        
        titel = it.get("title") or it.get("song", {}).get("title") or "Unbekannter Song"

        # 1) Hauptstimme aus 'responsible'. Mehrere Namen werden zu EINEM Feld mit
        #    " & " verbunden, damit ein Komma die Spalten im UI nicht zerschneidet.
        stimme = ""
        res = it.get("responsible")
        if isinstance(res, str):
            stimme = res.strip()
        elif isinstance(res, dict):
            if res.get("text"):
                stimme = res["text"].strip()
            else:
                namen = []
                for p in res.get("persons") or []:
                    name = p.get("name") or p.get("personName")
                    if not name and p.get("firstName"):
                        name = f"{p.get('firstName')} {p.get('lastName', '')}".strip()
                    if name:
                        namen.append(name)
                stimme = " & ".join(namen)
        elif isinstance(res, list):
            namen = [p.get("name") if isinstance(p, dict) else str(p) for p in res]
            stimme = " & ".join(n for n in namen if n)
        if not stimme:
            rp = it.get("responsiblePerson") or it.get("responsiblePersonName")
            if isinstance(rp, str):
                stimme = rp.strip()

        # 2) Notiz auswerten: Stimme (falls 'responsible' leer), Instrumente, Bemerkungen
        instrs, remarks = [], []
        note_stimme = ""
        for line in (it.get("note") or "").splitlines():
            line = line.strip()
            if not line:
                continue
            orig_line = line
            ist_stimme = bool(_STIMME_PREFIX.match(line))
            line = _STIMME_PREFIX.sub("", line)             # "Lead:/Voc:/Gesang:" weg
            if not ist_stimme:
                # "Instr:/Name:" o.ae. entfernen (z.B. "Name: Bratsche" -> "Bratsche")
                line = re.sub(r"^[A-ZÄÖÜ][a-zäöüß-]+\s*:\s*", "", line)
            instrs.extend(_instrumente_aus(line))
            if ist_stimme:
                # Rest der Stimmen-Zeile ohne Instrumente = Saenger(in)
                # (z.B. "Lead: Lea & Piano" -> Stimme "Lea", Instrument "Piano")
                rest = _INSTRUMENTE.sub("", line)
                rest = re.sub(r"[+&,/]", " ", rest)
                rest = re.sub(r"\s{2,}", " ", rest).strip(" .-")
                if rest and not note_stimme:
                    note_stimme = rest
            elif _ist_bemerkung(orig_line, line):
                remarks.append(orig_line.strip().rstrip(";,. "))

        # Instrumente deduplizieren (Reihenfolge erhalten, ohne Gross-/Kleinschreibung)
        _gesehen, _uniq = set(), []
        for i in instrs:
            if i.lower() not in _gesehen:
                _gesehen.add(i.lower()); _uniq.append(i)
        instrs = _uniq

        # Stimme aus der Notiz nur, wenn 'responsible' keine lieferte.
        if not stimme:
            stimme = note_stimme
        # Fuehrendes "Lead/Voc/..." entfernen, Komma -> " & " (Stimme bleibt EIN Feld).
        stimme = _STIMME_PREFIX.sub("", stimme).strip()
        stimme = re.sub(r"\s*,\s*", " & ", stimme)

        # Format: "- Titel (Stimme, Instrument, [Bemerkung])"
        extra = []
        if stimme:
            extra.append(stimme)
        if instrs:
            extra.append(", ".join(instrs))
        if remarks:
            extra.append(f"[{'; '.join(remarks)}]")

        if extra:
            zeilen.append(f"- {titel} ({', '.join(extra)})")
        else:
            zeilen.append(f"- {titel}")
            
    return "\n".join(zeilen)
