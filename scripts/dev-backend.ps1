param(
    [string]$EnvFile = ".env.local",
    [int]$Port = 8080,
    [switch]$Install,
    [switch]$LearnedRanker,
    [string]$LearnedRankerPath
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$serverDir = Join-Path $root "Server"
$venvDir = Join-Path $serverDir ".venv"
$pythonExe = Join-Path $venvDir "Scripts\python.exe"
$pipExe = Join-Path $venvDir "Scripts\pip.exe"
$envPath = Join-Path $serverDir $EnvFile

if (-not (Test-Path $envPath)) {
    Copy-Item (Join-Path $serverDir ".env.local.example") $envPath
    Write-Host "Created $envPath from .env.local.example"
}

$envFileLines = Get-Content -LiteralPath $envPath
$hasDatabaseUrl = $envFileLines | Where-Object { $_ -match '^\s*DATABASE_URL\s*=' -and $_ -notmatch '^\s*#' } | Select-Object -First 1
if (-not $hasDatabaseUrl) {
    $env:DATABASE_URL = "sqlite:///adventour_dev.db"
    Write-Warning "No DATABASE_URL found in $envPath. Using sqlite:///adventour_dev.db for this local backend run."
}

$validVenv = $false
if (Test-Path $pythonExe) {
    try {
        & $pythonExe --version *> $null
        $validVenv = $LASTEXITCODE -eq 0
    }
    catch {
        $validVenv = $false
    }
}

if ((Test-Path $venvDir) -and -not $validVenv) {
    Write-Host "Existing backend virtual environment is not runnable. Recreating it..."
    Remove-Item -LiteralPath $venvDir -Recurse -Force
}

if (-not (Test-Path $pythonExe)) {
    Write-Host "Creating backend virtual environment..."
    py -3 -m venv $venvDir
    $Install = $true
}

if ($Install) {
    Write-Host "Installing backend dependencies..."
    & $pipExe install -r (Join-Path $serverDir "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "Backend dependency install failed. Check network access or rerun after dependencies are available."
    }
}

Write-Host "Starting Adventour backend on http://0.0.0.0:$Port"
Write-Host "Local machine URL: http://localhost:$Port"
Write-Host "Android emulator URL: http://10.0.2.2:$Port"

Push-Location $serverDir
try {
    $env:FLASK_ENV = "development"
    $env:PORT = "$Port"
    $env:ENV_FILE = $envPath
    if ($LearnedRanker -or $LearnedRankerPath) {
        if (-not $LearnedRankerPath) {
            $LearnedRankerPath = Join-Path $serverDir "instance\recommender\recommender-model.latest.json"
        }

        $resolvedRankerPath = [System.IO.Path]::GetFullPath($LearnedRankerPath)
        if (Test-Path $resolvedRankerPath) {
            $env:ADVENTOUR_LEARNED_RANKER_PATH = $resolvedRankerPath
            Write-Host "Learned ranker model: $resolvedRankerPath"
        }
        else {
            Write-Warning "Learned ranker model not found at $resolvedRankerPath. Start without -LearnedRanker or run Server\recommender_refresh_model.py first."
        }
    }
    & $pythonExe app.py
}
finally {
    Pop-Location
}
