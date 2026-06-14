@echo off
setlocal
REM Lobpreis-Planer Starter fuer Windows: startet den lokalen Server (falls noch
REM nicht aktiv) und oeffnet die Oberflaeche im Browser. Per Doppelklick oder
REM ueber die Verknuepfung aus installiere_starter.cmd nutzbar.

cd /d "%~dp0"

if "%LP_PORT%"=="" (set "PORT=8765") else (set "PORT=%LP_PORT%")
set "URL=http://127.0.0.1:%PORT%"

REM Python finden und VERIFIZIEREN (Store-Stubs aus App-Aliasen aussortieren).
set "PY="
for %%c in ("py -3" "python3" "python") do (
    %%~c -c "import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "PY=%%~c"
        goto :py_gefunden
    )
)
echo Python 3 wurde nicht gefunden.
echo.
echo Bitte von https://www.python.org installieren und beim Setup
echo "Add Python to PATH" aktivieren, dann erneut starten.
echo.
echo Falls Python installiert ist, aber stattdessen der Microsoft-Store
echo oeffnet: Einstellungen ^> Apps ^> Erweiterte App-Einstellungen
echo ^> Ausfuehrungsaliase ^> "Python" und "Python3" deaktivieren.
pause
exit /b 1
:py_gefunden

REM Laeuft schon ein Server auf dem Port? Dann nur den Browser oeffnen
REM (idempotent: kein zweiter Server beim erneuten Doppelklick).
%PY% -c "import socket,sys; s=socket.socket(); s.settimeout(0.3); sys.exit(0 if s.connect_ex(('127.0.0.1',%PORT%))==0 else 1)"
if not errorlevel 1 (
  start "" "%URL%"
  exit /b 0
)

REM Server in eigenem, minimiertem Fenster starten.
start "Lobpreis-Planer" /min %PY% ui.py --port %PORT%

REM Aktiv warten, bis der Server antwortet (max. ~30s) statt blind zu schlafen.
for /l %%i in (1,1,30) do (
  %PY% -c "import socket,sys; s=socket.socket(); s.settimeout(0.3); sys.exit(0 if s.connect_ex(('127.0.0.1',%PORT%))==0 else 1)"
  if not errorlevel 1 goto :open
  timeout /t 1 /nobreak >nul
)

:open
start "" "%URL%"
exit /b 0
