# Thin Windows install entry. Operates only in this clone.
# Reuses .venv when it already exists. Does not delete it.
# Does not change the machine execution policy and does not write git config.
# If PowerShell refuses to run this file, run these commands yourself from the repo root:
#   py -3 -m venv .venv
#   .\.venv\Scripts\python.exe -m pip install --upgrade pip
#   .\.venv\Scripts\python.exe -m pip install .\lauren-team-kit
#   .\.venv\Scripts\python.exe -m lauren_team_kit doctor
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $VenvPy) {
    Write-Host "reuse existing .venv (not overwritten)"
} else {
    if ($env:LAUREN_PYTHON -and (Test-Path -LiteralPath $env:LAUREN_PYTHON)) {
        & $env:LAUREN_PYTHON -m venv .venv
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv .venv
    } else {
        & python -m venv .venv
    }
}
& $VenvPy -m pip install --upgrade pip
& $VenvPy -m pip install (Join-Path $Root "lauren-team-kit")
Write-Host "doctor: $VenvPy -m lauren_team_kit doctor"
Write-Host "scenario: $VenvPy -m lauren_team_kit.scenarios c1 --root $Root"
exit $LASTEXITCODE
