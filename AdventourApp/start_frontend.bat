@echo off
setlocal

set AVD_NAME=Pixel_7_Pro_API_30

echo Starting Metro bundler...
start "" cmd /k "npx react-native start"

timeout /t 2

echo Checking for running emulator...
adb devices | findstr /R /C:"device$" >nul
IF ERRORLEVEL 1 (
    echo No emulator found. Launching emulator: %AVD_NAME%
    start "" /D "%ANDROID_HOME%\emulator" cmd /c "emulator.exe -avd %AVD_NAME% -no-snapshot-load -gpu auto -feature AllowSnapshotMigration"
) ELSE (
    echo Emulator is already running.
)

echo Launching app on Android...
npx react-native run-android

pause
