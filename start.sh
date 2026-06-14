#!/bin/bash
# Lobpreis-Planer Starter: startet den lokalen Server (falls noch nicht aktiv)
# und oeffnet die Oberflaeche im Browser. Laeuft unter Linux UND macOS; per
# Doppelklick (Desktop-Symbol bzw. .app, siehe installiere_starter*.sh/.command)
# oder aus dem Terminal nutzbar. Fuer Windows gibt es start.bat.

# In das Verzeichnis dieses Skripts wechseln (Symlinks portabel aufloesen --
# "readlink -f" gibt es auf macOS/BSD nicht, daher die Schleife).
QUELLE="${BASH_SOURCE[0]}"
while [ -h "$QUELLE" ]; do
    VERZ="$(cd -P "$(dirname "$QUELLE")" && pwd)"
    QUELLE="$(readlink "$QUELLE")"
    [ "${QUELLE#/}" = "$QUELLE" ] && QUELLE="$VERZ/$QUELLE"
done
cd "$(cd -P "$(dirname "$QUELLE")" && pwd)" || exit 1

PORT="${LP_PORT:-8765}"
URL="http://127.0.0.1:${PORT}"

# Lauscht schon etwas auf dem Port? (idempotent: kein zweiter Server, keine
# "Address already in use"-Fehlermeldung beim erneuten Doppelklick).
port_offen() {
    python3 - "$1" <<'PY'
import socket, sys
s = socket.socket(); s.settimeout(0.3)
raise SystemExit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
PY
}

SERVER_PID=""
if ! port_offen "$PORT"; then
    python3 ui.py --port "$PORT" &
    SERVER_PID=$!
    # Aktiv warten, bis der Server antwortet (max. ~10s) statt blind zu schlafen.
    for _ in $(seq 1 50); do
        port_offen "$PORT" && break
        sleep 0.2
    done
fi

# Browser oeffnen.
if command -v xdg-open > /dev/null; then
    xdg-open "$URL"
elif command -v open > /dev/null; then
    open "$URL"
fi

# Haben wir den Server selbst gestartet, am Leben halten, bis er endet
# (z.B. Tab schliessen -> Auto-Shutdown). Lief er schon, kehren wir sofort zurueck.
if [ -n "$SERVER_PID" ]; then
    wait "$SERVER_PID"
fi
