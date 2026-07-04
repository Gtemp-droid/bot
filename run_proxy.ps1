# Self-elevating PowerShell script
# If not admin, relaunch as admin
if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Start-Process powershell -Verb RunAs -ArgumentList "-NoExit -NoProfile -ExecutionPolicy Bypass -Command cd '$PSScriptRoot'; python proxy.py"
    exit
}

# We're admin now
Set-Location $PSScriptRoot
Write-Host "========================================"
Write-Host " Dofus 1.29 MITM Proxy"
Write-Host "========================================"
Write-Host ""
Write-Host "Game must be running!"
Write-Host ""

python proxy.py
pause
