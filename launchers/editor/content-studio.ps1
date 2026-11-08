$ErrorActionPreference = 'Stop'
$studioRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$bootstrap = (Get-Command python -ErrorAction Stop).Source
& $bootstrap (Join-Path $studioRoot 'tools/storage/run.py') startup --checkout $studioRoot --paths-only
if ($LASTEXITCODE -ne 0) { throw 'External storage validation failed.' }
$checkoutVenv = & $bootstrap (Join-Path $studioRoot 'tools/worktree-venv/run.py') --path
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve external checkout environment.' }
$candidates = @(
    $env:SPRITEMOTION_PYTHON,
    (Join-Path $checkoutVenv 'Scripts/python.exe')
)
$studioPython = $null
foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate)) {
        & $candidate -c 'import PIL, numpy' 2>$null
        if ($LASTEXITCODE -eq 0) { $studioPython = $candidate; break }
    }
}
if (-not $studioPython) { throw 'Install Python with Pillow and NumPy, or set SPRITEMOTION_PYTHON.' }
& $bootstrap (Join-Path $studioRoot 'tools/storage/run.py') startup --checkout $studioRoot --python $studioPython
if ($LASTEXITCODE -ne 0) { throw 'Python environment belongs to another checkout.' }
Set-Location -LiteralPath $studioRoot
Write-Host 'Open http://127.0.0.1:8772 in your browser. Close this terminal to stop the studio.'
& $studioPython tools/uo-content/studio.py
