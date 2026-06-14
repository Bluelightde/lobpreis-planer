@echo off
REM ============================================================
REM  Lobpreis-Planer -- Ein-Klick-Installation (Desktop + Startmenue)
REM  Einfach DOPPELKLICKEN. Kein PowerShell-Befehl noetig.
REM ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_installiere_starter.ps1"
echo.
pause
