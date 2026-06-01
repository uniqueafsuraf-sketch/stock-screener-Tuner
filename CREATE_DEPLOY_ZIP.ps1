# Creates stockstunerstation-deploy.zip for GitHub upload (no Git required)
$root = $PSScriptRoot
$zip = Join-Path $root "stockstunerstation-deploy.zip"

$exclude = @('.venv', '__pycache__', 'stockstunerstation-deploy.zip', '.git')
$files = Get-ChildItem -Path $root -Recurse -File | Where-Object {
    $rel = $_.FullName.Substring($root.Length + 1)
    -not ($exclude | Where-Object { $rel -like "$_*" -or $rel -like "*\$_\*" })
}

if (Test-Path $zip) { Remove-Item $zip -Force }
$temp = Join-Path $env:TEMP "sts-deploy-$(Get-Random)"
New-Item -ItemType Directory -Path $temp -Force | Out-Null
foreach ($f in $files) {
    $rel = $f.FullName.Substring($root.Length + 1)
    $dest = Join-Path $temp $rel
    $dir = Split-Path $dest -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    Copy-Item $f.FullName $dest -Force
}
Compress-Archive -Path (Join-Path $temp '*') -DestinationPath $zip -Force
Remove-Item $temp -Recurse -Force
Write-Host "Created: $zip"
