#!/bin/bash
# Installiert einen Desktop-Starter fuer den Lobpreis-Planer:
#   - Eintrag im Anwendungsmenue (~/.local/share/applications)
#   - optional ein Doppelklick-Symbol auf dem Desktop
# So startet die App ohne Terminal -- einmal ausfuehren, danach reicht ein Klick.
set -e

REPO="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
START="$REPO/start.sh"
ICON="$REPO/web/favicon.svg"
APPS="$HOME/.local/share/applications"
DESKTOP_FILE="$APPS/lobpreis-planer.desktop"

command -v python3 > /dev/null || { echo "FEHLER: python3 nicht gefunden -- bitte Python 3 installieren."; exit 1; }
[ -f "$START" ] || { echo "FEHLER: start.sh nicht gefunden ($START)."; exit 1; }
[ -f "$ICON" ]  || { echo "FEHLER: Icon nicht gefunden ($ICON)."; exit 1; }
chmod +x "$START"

mkdir -p "$APPS"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Lobpreis-Planer
Comment=Besetzung -> Buehnen-Skizze + X32-Belegungsplan
Exec="$START"
Icon=$ICON
Terminal=false
Categories=AudioVideo;Audio;
StartupNotify=true
EOF
chmod +x "$DESKTOP_FILE"

# Menue-Datenbank aktualisieren (best effort, nicht alle Systeme haben das Tool).
if command -v update-desktop-database > /dev/null; then
    update-desktop-database "$APPS" || true
fi
echo "Anwendungsmenue-Eintrag installiert: $DESKTOP_FILE"

# Desktop-Symbol anlegen. Den Desktop-Ordner sprachunabhaengig ermitteln
# (xdg-user-dir kennt z.B. den deutschen "Schreibtisch").
DESK=""
if command -v xdg-user-dir > /dev/null; then
    DESK="$(xdg-user-dir DESKTOP)"
fi
if [ -z "$DESK" ] || [ ! -d "$DESK" ]; then
    for d in "$HOME/Schreibtisch" "$HOME/Desktop"; do
        [ -d "$d" ] && DESK="$d" && break
    done
fi
if [ -n "$DESK" ] && [ -d "$DESK" ]; then
    cp "$DESKTOP_FILE" "$DESK/lobpreis-planer.desktop"
    chmod +x "$DESK/lobpreis-planer.desktop"
    # GNOME/Nautilus: Symbol als vertrauenswuerdig markieren (sonst "nicht vertraut").
    if command -v gio > /dev/null; then
        gio set "$DESK/lobpreis-planer.desktop" metadata::trusted true || true
    fi
    echo "Desktop-Symbol angelegt:           $DESK/lobpreis-planer.desktop"
fi

echo
echo "Fertig. Den Lobpreis-Planer jetzt ueber das Anwendungsmenue ('Lobpreis-Planer')"
echo "oder per Doppelklick auf das Desktop-Symbol starten."
