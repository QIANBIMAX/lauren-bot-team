# Thin Windows entry. Does not change the execution policy.
# If PowerShell blocks this file, run the same command directly:
#   py -3 -m lauren_team_kit.scenarios <name> --root <repo>
# Do not run Set-ExecutionPolicy Unrestricted for the machine.
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Name,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$VenvPy = Join-Path $Repo "lauren-team-kit\.venv\Scripts\python.exe"
if ($env:LAUREN_PYTHON -and (Test-Path -LiteralPath $env:LAUREN_PYTHON)) {
    & $env:LAUREN_PYTHON -m lauren_team_kit.scenarios $Name --root $Repo @Rest
} elseif (Test-Path -LiteralPath $VenvPy) {
    & $VenvPy -m lauren_team_kit.scenarios $Name --root $Repo @Rest
} else {
    & py -3 -m lauren_team_kit.scenarios $Name --root $Repo @Rest
}
exit $LASTEXITCODE
