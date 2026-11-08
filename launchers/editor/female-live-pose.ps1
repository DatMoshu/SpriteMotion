param([int]$Port = 8768)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$bootstrap = (Get-Command python -ErrorAction Stop).Source
$checkoutVenv = & $bootstrap (Join-Path $repoRoot 'tools/worktree-venv/run.py') --path
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve external checkout environment.' }
$pythonExe = $env:SPRITEMOTION_PYTHON
if (-not $pythonExe) { $pythonExe = Join-Path $checkoutVenv 'Scripts/python.exe' }
& $bootstrap (Join-Path $repoRoot 'tools/storage/run.py') startup --checkout $repoRoot --python $pythonExe
if ($LASTEXITCODE -ne 0) { throw 'Storage/environment validation failed.' }
$editorUrl = "http://127.0.0.1:$Port/editor/"
try {
    $response = Invoke-WebRequest $editorUrl -TimeoutSec 2
    if ($response.Content -match 'Live pose editor') { Start-Process $editorUrl; exit }
} catch { }
$serverScript = Join-Path $repoRoot 'games/ultima-online/region-masks/pose_editor_server.py'
Start-Process -FilePath $pythonExe -ArgumentList @("`"$serverScript`"", '--port', "$Port") -WorkingDirectory $repoRoot -WindowStyle Hidden
Write-Host "Live pose editor: $editorUrl"
Start-Process $editorUrl
