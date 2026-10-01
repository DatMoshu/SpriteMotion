param([int]$Port = 8768)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$pythonExe = Join-Path $repoRoot '.venvs/spritemotion/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { $pythonExe = (Get-Command python -ErrorAction Stop).Source }
$editorUrl = "http://127.0.0.1:$Port/editor/"
try {
    $response = Invoke-WebRequest $editorUrl -TimeoutSec 2
    if ($response.Content -match 'Live pose editor') { Start-Process $editorUrl; exit }
} catch { }
$serverScript = Join-Path $repoRoot 'games/ultima-online/region-masks/pose_editor_server.py'
Start-Process -FilePath $pythonExe -ArgumentList @("`"$serverScript`"", '--port', "$Port") -WorkingDirectory $repoRoot -WindowStyle Hidden
Write-Host "Live pose editor: $editorUrl"
Start-Process $editorUrl
