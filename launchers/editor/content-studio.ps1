$ErrorActionPreference = 'Stop'
$studioRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$candidates = @(
    $env:SPRITEMOTION_PYTHON,
    (Join-Path $studioRoot '.venvs/spritemotion/Scripts/python.exe'),
    (Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
)
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCommand) { $candidates += $pythonCommand.Source }
$studioPython = $null
foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate)) {
        & $candidate -c 'import PIL, numpy' 2>$null
        if ($LASTEXITCODE -eq 0) { $studioPython = $candidate; break }
    }
}
if (-not $studioPython) { throw 'Install Python with Pillow and NumPy, or set SPRITEMOTION_PYTHON.' }
Set-Location -LiteralPath $studioRoot
Write-Host 'Open http://127.0.0.1:8772 in your browser. Close this terminal to stop the studio.'
& $studioPython tools/uo-content/studio.py
