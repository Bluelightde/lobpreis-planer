#!/bin/bash
# Baut ein doppelklickbares macOS-App-Bundle "Lobpreis-Planer.app" in
# ~/Applications -- mit Fader-Icon. Danach via Launchpad/Spotlight oder
# Doppelklick startbar (kein Terminal noetig). Diese .command-Datei selbst ist
# ebenfalls doppelklickbar (Finder oeffnet sie einmalig im Terminal).
set -e

# Repo-Verzeichnis portabel ermitteln (macOS/BSD haben kein "readlink -f").
QUELLE="${BASH_SOURCE[0]}"
while [ -h "$QUELLE" ]; do
    VERZ="$(cd -P "$(dirname "$QUELLE")" && pwd)"
    QUELLE="$(readlink "$QUELLE")"
    [ "${QUELLE#/}" = "$QUELLE" ] && QUELLE="$VERZ/$QUELLE"
done
REPO="$(cd -P "$(dirname "$QUELLE")" && pwd)"

START="$REPO/start.sh"
ICNS="$REPO/web/lobpreis-planer.icns"
[ -f "$START" ] || { echo "FEHLER: start.sh nicht gefunden ($START)."; exit 1; }
[ -f "$ICNS" ]  || { echo "FEHLER: Icon nicht gefunden ($ICNS)."; exit 1; }
chmod +x "$START"

APP="$HOME/Applications/Lobpreis-Planer.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Lobpreis-Planer</string>
  <key>CFBundleDisplayName</key><string>Lobpreis-Planer</string>
  <key>CFBundleIdentifier</key><string>de.lobpreis.planer</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>lobpreis-planer</string>
  <key>CFBundleIconFile</key><string>lobpreis-planer</string>
  <key>LSMinimumSystemVersion</key><string>10.10</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

# Launcher im Bundle: PATH um die ueblichen Python-Orte ergaenzen (GUI-Start
# hat ein knappes PATH) und start.sh aufrufen. Repo-Pfad ist fest verdrahtet.
cat > "$APP/Contents/MacOS/lobpreis-planer" <<EOF
#!/bin/bash
export PATH="/usr/local/bin:/opt/homebrew/bin:/Library/Frameworks/Python.framework/Versions/Current/bin:\$PATH"
exec "$START"
EOF
chmod +x "$APP/Contents/MacOS/lobpreis-planer"

cp "$ICNS" "$APP/Contents/Resources/lobpreis-planer.icns"
touch "$APP"   # Icon-/Bundle-Cache anstupsen

echo "App-Bundle erstellt: $APP"
echo "Starten ueber Launchpad/Spotlight ('Lobpreis-Planer') oder per Doppelklick."
