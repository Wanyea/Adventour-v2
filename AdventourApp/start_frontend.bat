@echo off
setlocal

set AVD_NAME=Pixel_7_Pro_API_30
set LOG_FILE=build-log.txt

echo ====================================
echo AdventourApp Dev Launcher
echo ====================================

:: 1. Start Metro if not already running
echo [1/4] Starting Metro bundler...
start "" cmd /k "npx react-native start"

timeout /t 2

:: 2. Check for running emulator
echo [2/4] Checking for running emulator...
adb devices | findstr /R /C:"device$" >nul
IF ERRORLEVEL 1 (
    echo No emulator found. Launching emulator: %AVD_NAME%
    start "" /D "%ANDROID_HOME%\emulator" cmd /c "emulator.exe -avd %AVD_NAME% -no-snapshot-load -gpu auto -feature AllowSnapshotMigration"
    timeout /t 10
) ELSE (
    echo Emulator is already running.
)

:: 3. Build and install the app
echo [3/4] Installing app to emulator...
call npx react-native run-android > %LOG_FILE% 2>&1

:: 4. Launch app manually (to avoid hanging)
echo [4/4] Launching app...
adb shell monkey -p com.adventourapp -c android.intent.category.LAUNCHER 1

echo ------------------------------------
echo Done! View %LOG_FILE% for build logs.
pause