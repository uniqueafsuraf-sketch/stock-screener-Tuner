# Ping Render every 10 minutes so the free tier stays awake (24/7).
# Run on a PC that stays on, or schedule in Windows Task Scheduler.
param(
    [string]$Url = "https://stock-screener-tuner-1.onrender.com/api/ping"
)

$ErrorActionPreference = "SilentlyContinue"
while ($true) {
    try {
        $r = Invoke-WebRequest -Uri $Url -TimeoutSec 60 -UseBasicParsing
        Write-Host "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ping $($r.StatusCode)"
    } catch {
        Write-Host "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ping failed: $($_.Exception.Message)"
    }
    Start-Sleep -Seconds 600
}
