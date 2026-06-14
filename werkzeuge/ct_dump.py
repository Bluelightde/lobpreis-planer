#!/usr/bin/env python3
"""Zieht ChurchTools-Rohdaten (Events + Agenden) als lokale JSON-Fixtures.

Zweck: Setlisten-/Besetzungs-Analysen und Tests offline und ohne wiederholte
Netz-Calls fahren. Schreibt nach .cache/dump/ (gitignored): eine index.json mit
der Terminliste und je Termin eine agenda_<eid>.json (nur Termine mit Agenda).

Beispiele:
    python3 werkzeuge/ct_dump.py                          # letzte 12 Monate, DD1
    python3 werkzeuge/ct_dump.py --kuerzel DD2 --monate 24
    python3 werkzeuge/ct_dump.py --von 2025-01-01 --bis 2025-12-31 --ziel meine_fixtures
"""

import argparse
import json
import os
import sys
from datetime import date, timedelta

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASIS)
import lobpreis_planer as L          # noqa: E402
import churchtools as CT             # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kuerzel", default="DD1", help="Termin-Namensfilter (Default DD1)")
    ap.add_argument("--monate", type=int, default=12, help="Zeitraum zurueck in Monaten")
    ap.add_argument("--von", help="Startdatum YYYY-MM-DD (ueberschreibt --monate)")
    ap.add_argument("--bis", help="Enddatum YYYY-MM-DD (Default heute)")
    ap.add_argument("--ziel", default="dump",
                    help="Unterordner unter .cache/ (Default 'dump')")
    args = ap.parse_args()

    bis = args.bis or date.today().isoformat()
    von = args.von or (date.today() - timedelta(days=int(args.monate * 30.5))).isoformat()
    ziel = os.path.join(BASIS, ".cache", args.ziel)
    os.makedirs(ziel, exist_ok=True)

    c = L.lade_churchtools()
    if not c.get("token"):
        sys.exit("Kein ChurchTools-Token in config/config.json")
    ct = CT.CT(c["base_url"], token=c.get("token"), ssl_verify=c.get("ssl_verify", True))

    rows = []
    for ev in ct.events(von):
        sd = (ev.get("startDate") or ev.get("start") or "")[:10]
        name = ev.get("name") or ""
        if sd and von <= sd <= bis and args.kuerzel in name:
            rows.append({"id": ev.get("id"), "datum": sd, "name": name})
    rows.sort(key=lambda r: r["datum"], reverse=True)

    index = []
    n_agenda = 0
    for r in rows:
        eid = r["id"]
        eintrag = dict(r)
        try:
            ag = ct.agenda(eid)
        except CT.ChurchToolsFehler:
            eintrag["agenda"] = None       # 404 = keine Agenda hinterlegt
        else:
            with open(os.path.join(ziel, f"agenda_{eid}.json"), "w", encoding="utf-8") as f:
                json.dump(ag, f, ensure_ascii=False, indent=1)
            eintrag["agenda"] = f"agenda_{eid}.json"
            eintrag["songs"] = sum(1 for i in (ag.get("items") or []) if i.get("type") == "song")
            n_agenda += 1
        index.append(eintrag)

    with open(os.path.join(ziel, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"kuerzel": args.kuerzel, "von": von, "bis": bis, "termine": index},
                  f, ensure_ascii=False, indent=1)

    print(f"Dump '{args.kuerzel}' {von}..{bis} -> .cache/{args.ziel}")
    print(f"Termine: {len(rows)} | mit Agenda: {n_agenda} | index.json geschrieben")
    return 0


if __name__ == "__main__":
    sys.exit(main())
