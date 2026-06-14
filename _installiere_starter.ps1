# Erstellt Verknuepfungen (Desktop + Startmenue) fuer den Lobpreis-Planer,
# mit dem Fader-Icon (web\lobpreis-planer.ico). Einmal ausfuehren -- danach
# genuegt ein Doppelklick auf die Verknuepfung. Am einfachsten ueber den
# Doppelklick-Wrapper installiere_starter.cmd starten.
$ErrorActionPreference = "Stop"
$repo   = Split-Path -Parent $MyInvocation.MyCommand.Path
$target = Join-Path $repo "start.bat"
$icon   = Join-Path $repo "web\lobpreis-planer.ico"

if (-not (Test-Path $target)) { throw "start.bat nicht gefunden: $target" }
if (-not (Test-Path $icon))   { throw "Icon nicht gefunden: $icon" }

$ws = New-Object -ComObject WScript.Shell

function New-LpShortcut($pfad) {
    $sc = $ws.CreateShortcut($pfad)
    $sc.TargetPath       = $target
    $sc.WorkingDirectory = $repo
    $sc.IconLocation     = $icon
    $sc.WindowStyle      = 7   # minimiert (kein stoerendes Konsolenfenster)
    $sc.Description       = "Lobpreis-Planer: Besetzung -> Buehnen-Skizze + X32-Belegungsplan"
    $sc.Save()
    Write-Host "Verknuepfung erstellt: $pfad"
}

$desktop = [Environment]::GetFolderPath("Desktop")
New-LpShortcut (Join-Path $desktop "Lobpreis-Planer.lnk")

$programs = [Environment]::GetFolderPath("Programs")
New-LpShortcut (Join-Path $programs "Lobpreis-Planer.lnk")

Write-Host ""
Write-Host "Fertig. Den Lobpreis-Planer jetzt per Doppelklick auf das Desktop-Symbol"
Write-Host "oder ueber das Startmenue ('Lobpreis-Planer') starten."
