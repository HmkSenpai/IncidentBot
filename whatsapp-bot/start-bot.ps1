# start-bot.ps1
# Relance proprement bot.js :
#   1. Tue toute ancienne instance de bot.js encore vivante (la cause n°1 des
#      "connexions fantômes" : deux process partageant le même dossier
#      auth_info/ → plus aucun message reçu jusqu'à suppression du dossier).
#   2. Puis lance en avant-plan une nouvelle instance.
#
# Usage direct :  powershell -NoProfile -ExecutionPolicy Bypass -File start-bot.ps1
# Ou via npm :    npm run restart
# Remarque : arrêter avec Ctrl+C est sûr (le verrou bot.lock est nettoyé).

$ErrorActionPreference = "Stop"

$botDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $botDir

$old = Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -like "*bot.js*" }

if ($old) {
    foreach ($p in $old) {
        Write-Host "[start-bot] Arrêt de l'ancienne instance de bot.js (PID $($p.ProcessId))..."
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 1
} else {
    Write-Host "[start-bot] Aucune ancienne instance de bot.js à arrêter."
}

Write-Host "[start-bot] Lancement de bot.js..."
node bot.js