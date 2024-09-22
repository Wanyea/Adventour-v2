@echo off
REM Start Android emulator
cd C:\Users\wanye\AppData\Local\Android\Sdk
emulator -avd Pixel_7_API_30

REM Navigate to your project directory
cd D:\source\Adventour-v2\Adventour

REM Start Expo
npx expo start
