param(
    [string]$EnvFile = ".env.android.local",
    [string]$AvdName = "",
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$appDir = Join-Path $root "AdventourApp"
$envPath = Join-Path $appDir $EnvFile

if (-not (Test-Path $envPath)) {
    Copy-Item (Join-Path $appDir ".env.android.local.example") $envPath
    Write-Host "Created $envPath from .env.android.local.example"
}

if (-not $env:ANDROID_HOME) {
    throw "ANDROID_HOME is not set. Install Android Studio, then set ANDROID_HOME to your Android SDK folder."
}

Push-Location $appDir
try {
    if (-not $SkipInstall) {
        Write-Host "Installing npm dependencies if needed..."
        npm install
    }

    $adb = Join-Path $env:ANDROID_HOME "platform-tools\adb.exe"
    $emulator = Join-Path $env:ANDROID_HOME "emulator\emulator.exe"
    $devices = & $adb devices
    $hasDevice = $devices -match "`tdevice$"

    if (-not $hasDevice) {
        if (-not $AvdName) {
            Write-Host "No running Android device found. Available AVDs:"
            & $emulator -list-avds
            throw "Start an emulator from Android Studio, or rerun with -AvdName <name>."
        }

        Write-Host "Starting Android emulator $AvdName..."
        Start-Process -FilePath $emulator -ArgumentList @("-avd", $AvdName, "-no-snapshot-load") -WindowStyle Hidden

        Write-Host "Waiting for emulator boot..."
        & $adb wait-for-device

        $attempts = 0
        do {
            Start-Sleep -Seconds 5
            $attempts += 1
            $booted = ""
            try {
                $booted = & $adb shell getprop sys.boot_completed 2>$null
            }
            catch {
                Write-Host "Emulator is still starting ($attempts)..."
            }

            if ($attempts -gt 60) {
                throw "Timed out waiting for emulator boot."
            }
        } while ($booted -notmatch "1")

        Write-Host "Emulator booted."
    }

    Write-Host "Reversing Metro port for Android debug builds..."
    & $adb reverse tcp:8081 tcp:8081 | Out-Null

    $metroRunning = $false
    try {
        $metroStatus = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8081/status" -TimeoutSec 2
        $metroRunning = $metroStatus.Content -match "packager-status:running"
    }
    catch {
        $metroRunning = $false
    }

    if ($metroRunning) {
        Write-Host "Metro is already running on http://localhost:8081."
    }
    else {
        Write-Host "Starting Metro in a separate terminal..."
        Start-Process powershell -ArgumentList @(
            "-NoExit",
            "-Command",
            "cd '$appDir'; `$env:ENVFILE='$EnvFile'; npx react-native start --reset-cache"
        )
    }

    Write-Host "Installing Android app with ENVFILE=$EnvFile..."
    $env:ENVFILE = $EnvFile
    npx react-native run-android --no-packager
}
finally {
    Pop-Location
}
