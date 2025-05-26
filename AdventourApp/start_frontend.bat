@echo off
echo Starting Metro bundler...
start cmd /k "npx react-native start"

timeout /t 2

echo Launching app on Android...
npx react-native run-android

pause
