param(
    [string]$EnvFile = ".env.remote"
)

$ErrorActionPreference = "Stop"
$serverRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $serverRoot

if (-not (Test-Path -LiteralPath $EnvFile)) {
    throw "Missing $EnvFile. Copy .env.remote.example and fill it with local paths; do not commit secrets."
}

$env:ENV_FILE = (Resolve-Path -LiteralPath $EnvFile).Path
$pythonCandidates = @(
    (Join-Path $serverRoot ".venv\Scripts\python.exe"),
    (Join-Path $serverRoot "adventour-server-venv\Scripts\python.exe")
)
$python = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $python) { $python = "python" }

& $python -m remote_service --check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -m remote_service
exit $LASTEXITCODE
