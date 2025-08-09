@echo off
setlocal

set AVD_NAME=Pixel_7_API_30
set LOG_FILE=build-log.txt

echo ====================================
echo AdventourApp Dev Launcher
echo ====================================

:: Check if ANDROID_HOME is set
if "%ANDROID_HOME%"=="" (
    echo ERROR: ANDROID_HOME environment variable is not set!
    echo Please set ANDROID_HOME to your Android SDK location.
    pause
    exit /b 1
)

:: 1. Start Metro if not already running
echo [1/4] Starting Metro bundler...
start "" cmd /k "npx react-native start"

:: 2. Check for running emulator
echo [2/4] Checking for running emulator...
adb devices | findstr /R /C:"device$" >nul
IF ERRORLEVEL 1 (
    echo No emulator found. Launching emulator: %AVD_NAME%
    echo Using ANDROID_HOME: %ANDROID_HOME%
    start "" "%ANDROID_HOME%\emulator\emulator.exe" -avd %AVD_NAME% -no-snapshot-load -gpu auto

    echo Waiting for emulator to boot...
    :wait_loop
    adb shell getprop sys.boot_completed 2>nul | findstr "1" >nul
    if errorlevel 1 (
        timeout /t 5 >nul
        goto wait_loop
    )
    echo Emulator booted.
) ELSE (
    echo Emulator is already running.
)

:: 3. Build and install the app
echo [3/4] Installing app to emulator...
call npx react-native run-android

:: 4. Launch app manually (to avoid hanging)
echo [4/4] Launching app...
adb shell monkey -p com.adventourapp -c android.intent.category.LAUNCHER 1

echo ------------------------------------
echo Done! View %LOG_FILE% for build logs.
pause