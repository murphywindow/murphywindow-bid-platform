param(
    [int]$Port = $(if ($env:MURPHY_BID_PORT) { [int]$env:MURPHY_BID_PORT } else { 8765 }),
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
$VenvPath = Join-Path $ProjectRoot '.venv'
$PythonPath = Join-Path $VenvPath 'Scripts\python.exe'
$RequirementsPath = Join-Path $ProjectRoot 'requirements.txt'
$StampPath = Join-Path $VenvPath '.requirements-sha256'

if (-not (Test-Path -LiteralPath $PythonPath)) {
    Write-Host 'Creating local Python virtual environment...'
    py -3 -m venv $VenvPath
}

$RequirementsHash = (Get-FileHash -LiteralPath $RequirementsPath -Algorithm SHA256).Hash
$InstalledHash = if (Test-Path -LiteralPath $StampPath) { Get-Content -LiteralPath $StampPath -Raw } else { '' }
if ($InstalledHash.Trim() -ne $RequirementsHash) {
    Write-Host 'Installing pinned dependencies...'
    & $PythonPath -m pip install --disable-pip-version-check -r $RequirementsPath
    Set-Content -LiteralPath $StampPath -Value $RequirementsHash -NoNewline
}

$Url = "http://127.0.0.1:$Port"
Write-Host "Murphy Window Bid Platform: $Url"
Write-Host 'Press Ctrl+C to stop the local server safely.'
if (-not $NoBrowser) {
    Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile', '-Command', "Start-Sleep -Seconds 2; Start-Process '$Url'"
}
& $PythonPath -m uvicorn app.main:app --host 127.0.0.1 --port $Port

