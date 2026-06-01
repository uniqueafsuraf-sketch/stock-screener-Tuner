# Starts StocksTunerStation + Cloudflare tunnel; writes public URL to data/public_url.txt
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$venvPy = Join-Path $root ".venv\Scripts\python.exe"
$cloudflared = Join-Path $root "tools\cloudflared.exe"
$urlFile = Join-Path $root "data\public_url.txt"
$port = 5050

if (-not (Test-Path $venvPy)) {
    & (Join-Path $root "install.bat")
    if (-not (Test-Path $venvPy)) { throw "Python venv missing after install" }
}

if (-not (Test-Path $cloudflared)) {
    New-Item -ItemType Directory -Force -Path (Join-Path $root "tools") | Out-Null
    Write-Host "Downloading cloudflared..."
    $ProgressPreference = "SilentlyContinue"
    Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile $cloudflared
}

# Stop stale listeners on dashboard ports
python -c "from dashboard.launch import kill_port_listeners; [kill_port_listeners(p) for p in (5050,8765,5051,8080)]" 2>$null
if ($LASTEXITCODE -ne 0) {
    & $venvPy -c "from dashboard.launch import kill_port_listeners; [kill_port_listeners(p) for p in (5050,8765,5051,8080)]"
}
Start-Sleep -Seconds 2

# Start Flask in background
$serverLog = Join-Path $root "data\server.log"
New-Item -ItemType Directory -Force -Path (Join-Path $root "data") | Out-Null
$serverErr = Join-Path $root "data\server_err.log"
$server = Start-Process -FilePath $venvPy -ArgumentList "start_dashboard.py", "--no-browser" -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput $serverLog -RedirectStandardError $serverErr

Write-Host "Waiting for server on port $port..."
$ok = $false
for ($i = 0; $i -lt 40; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/health" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $ok = $true; break }
    } catch {}
    Start-Sleep -Seconds 1
}
if (-not $ok) { throw "Server did not start on port $port. See data\server.log" }

# Start tunnel and capture URL
$tunnelLog = Join-Path $root "data\tunnel.log"
if (Test-Path $tunnelLog) { Remove-Item $tunnelLog -Force }
$tunnelErr = Join-Path $root "data\tunnel_err.log"
$tunnel = Start-Process -FilePath $cloudflared -ArgumentList "tunnel", "--url", "http://127.0.0.1:$port", "--no-autoupdate" -WorkingDirectory (Join-Path $root "tools") -WindowStyle Hidden -RedirectStandardOutput $tunnelLog -RedirectStandardError $tunnelErr -PassThru

$publicUrl = $null
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 1
    $text = ""
    if (Test-Path $tunnelLog) { $text += Get-Content $tunnelLog -Raw -ErrorAction SilentlyContinue }
    if (Test-Path $tunnelErr) { $text += Get-Content $tunnelErr -Raw -ErrorAction SilentlyContinue }
    if ($text -match "(https://[a-z0-9-]+\.trycloudflare\.com)") {
        $publicUrl = $Matches[1]
        break
    }
}

if (-not $publicUrl) {
    throw "Could not get public URL from tunnel. See data\tunnel.log"
}

Set-Content -Path $urlFile -Value $publicUrl -Encoding UTF8
Write-Host "PUBLIC_URL=$publicUrl"
Write-Host "PID_SERVER=$($server.Id)"
Write-Host "PID_TUNNEL=$($tunnel.Id)"
