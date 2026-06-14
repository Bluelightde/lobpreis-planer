#!/usr/bin/env python3
"""Setlisten-Schnellpruefung gegen ChurchTools -- meldet NUR Auffaelligkeiten.

Zweck: die wiederkehrende Frage "stimmt die Setlisten-Anzeige noch?" beantworten,
ohne 50 vollstaendige Setlisten auszugeben. Holt die Termine einer Gruppe/eines
Kuerzels, laesst sie durch churchtools.setliste_text() laufen und prueft das
Ergebnis gegen ein paar Heuristiken. Standardausgabe ist kompakt: eine
Statuszeile plus nur die auffaelligen Songs.

Agenden werden unter .cache/agenda/<eid>.json zwischengespeichert (mit --frisch
umgehbar), damit wiederholte Laeufe nichts erneut laden.

Beispiele:
    python3 werkzeuge/setlisten_check.py                 # letzte 12 Monate, DD1
    python3 werkzeuge/setlisten_check.py --monate 24
    python3 werkzeuge/setlisten_check.py --kuerzel DD2 --all
    python3 werkzeuge/setlisten_check.py --von 2025-01-01 --bis 2025-12-31
"""

import argparse
import json
import os
import sys
import re
from datetime import date, timedelta

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASIS)
import lobpreis_planer as L          # noqa: E402  (Konfig-Loader wiederverwenden)
import churchtools as CT             # noqa: E402

CACHE = os.path.join(BASIS, ".cache", "agenda")

# Woerter, die niemals ein Saenger-Name sind -- tauchen sie als "Stimme" auf,
# wurde die Notiz falsch zerlegt (Regressionswaechter fuer den Leadvoc-Fix).
_STOPWORTE = {
    "intro", "outro", "bridge", "refrain", "chorus", "vers", "verse",
    "pre-chorus", "prechorus", "track", "backingtrack", "playback",
    "alle", "all", "instrumental", "vortragslied", "medley",
}

# Voc-/Lead-Marker, die in einer BEMERKUNG auftauchen -> Saenger wurde vermutlich
# nicht als Stimme erkannt (z.B. "[Mit Track; LeadVoc: David]").
_VOC_IN_BEMERKUNG = re.compile(
    r"(?i)\b(?:lead\s*voc(?:al)?s?|voc(?:al)?s?|vox)\s*[:.\-]\s*\S")


def _agenda(ct, eid, frisch):
    """Agenda holen, mit Platten-Cache. None bei HTTP-Fehler (z.B. 404 = keine Agenda)."""
    pfad = os.path.join(CACHE, f"{eid}.json")
    if not frisch and os.path.isfile(pfad):
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    try:
        ag = ct.agenda(eid)
    except CT.ChurchToolsFehler:
        return None
    os.makedirs(CACHE, exist_ok=True)
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(ag, f)
    return ag


def _letzte_klammer(zeile):
    """Inhalt der LETZTEN runden Klammer einer Setlisten-Zeile (= Besetzung).
       Titel duerfen selbst Klammern enthalten ('Psalm 23 (Ich bin ...)')."""
    tiefe, start, beste = 0, -1, None
    for i, ch in enumerate(zeile):
        if ch == "(":
            if tiefe == 0:
                start = i
            tiefe += 1
        elif ch == ")" and tiefe:
            tiefe -= 1
            if tiefe == 0 and start >= 0:
                beste = zeile[start + 1:i]
    return beste


def _pruefe_zeile(zeile):
    """Liste von Auffaelligkeits-Gruenden fuer eine '- Titel (...)'-Zeile."""
    gruende = []
    if ";;" in zeile or ",;" in zeile or ", ," in zeile:
        gruende.append("doppeltes Trennzeichen")
    # nicht abgeschnittenes Stimmen-Praefix (Leadvoc/Voc:/Lead: im Stimme-Feld)
    bes = _letzte_klammer(zeile) or ""
    for stueck in re.findall(r"\[([^\]]*)\]", zeile):   # Bemerkungs-Inhalte
        if _VOC_IN_BEMERKUNG.search(stueck):
            gruende.append("Stimme evtl. in Bemerkung (Voc-Marker)")
            break
    feld = bes.split(",")[0].strip()        # erstes Feld = Stimme (kein Komma darin)
    if feld.startswith("["):                # nur Bemerkung, keine Stimme -> ok
        feld = ""
    if CT._STIMME_PREFIX.match(feld):
        gruende.append(f"Praefix nicht entfernt: '{feld}'")
    wort = feld.lower().strip(" .:-")
    if wort in _STOPWORTE:
        gruende.append(f"Stimme ist Schluesselwort: '{feld}'")
    elif wort and CT._INSTRUMENTE.fullmatch(wort.replace("-", "")):
        gruende.append(f"Stimme ist Instrument: '{feld}'")
    return gruende


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kuerzel", default="DD1", help="Termin-Namensfilter (Default DD1)")
    ap.add_argument("--monate", type=int, default=12, help="Zeitraum zurueck in Monaten")
    ap.add_argument("--von", help="Startdatum YYYY-MM-DD (ueberschreibt --monate)")
    ap.add_argument("--bis", help="Enddatum YYYY-MM-DD (Default heute)")
    ap.add_argument("--all", action="store_true", help="alle Setlisten ausgeben, nicht nur auffaellige")
    ap.add_argument("--frisch", action="store_true", help="Cache ignorieren, frisch laden")
    args = ap.parse_args()

    bis = args.bis or date.today().isoformat()
    von = args.von or (date.today() - timedelta(days=int(args.monate * 30.5))).isoformat()

    c = L.lade_churchtools()
    if not c.get("token"):
        sys.exit("Kein ChurchTools-Token in config/config.json")
    ct = CT.CT(c["base_url"], token=c.get("token"), ssl_verify=c.get("ssl_verify", True))

    rows = []
    for ev in ct.events(von):
        sd = (ev.get("startDate") or ev.get("start") or "")[:10]
        name = ev.get("name") or ""
        if sd and von <= sd <= bis and args.kuerzel in name:
            rows.append((sd, ev.get("id"), name))
    rows.sort(reverse=True)

    n_songs = n_leer = n_404 = n_auff = 0
    treffer = []
    for tag, eid, name in rows:
        ag = _agenda(ct, eid, args.frisch)
        if ag is None:
            n_404 += 1
            continue
        hat_song = any(i.get("type") == "song" for i in (ag.get("items") or []))
        txt = CT.setliste_text(ct, eid)
        if not hat_song or not txt.strip():
            n_leer += 1
            continue
        n_songs += 1
        auff = [(z, g) for z in txt.splitlines() if (g := _pruefe_zeile(z))]
        if auff:
            n_auff += 1
            treffer.append((tag, name, txt, auff))
        if args.all:
            print(f"=== {tag} #{eid} {name} ===\n{txt}\n")

    print(f"Setlisten-Check '{args.kuerzel}'  {von} .. {bis}")
    print(f"geprueft: {len(rows)} | mit Songs: {n_songs} | leer: {n_leer} | "
          f"Agenda-404: {n_404} | AUFFAELLIG: {n_auff}")
    if not treffer:
        print("OK -- keine Auffaelligkeiten.")
        return 0
    print()
    for tag, name, txt, auff in treffer:
        print(f"!! {tag}  {name}")
        for zeile, gruende in auff:
            print(f"   {zeile}")
            print(f"       -> {'; '.join(gruende)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
