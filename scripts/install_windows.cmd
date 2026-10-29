@echo off
setlocal
set "ADB=D:\Program Files\Netease\MuMu\nx_main\adb.exe"
if not exist "%ADB%" set "ADB=C:\Program Files\Netease\MuMu\nx_main\adb.exe"
if not exist "%ADB%" (
  echo MuMu adb.exe not found. Edit the ADB path in this file.
  exit /b 1
)
set "APK=%~dp0..\dist\MuMu-Desktop-Cleaner-v1.0.apk"
if not exist "%APK%" (
  echo APK not found: "%APK%"
  exit /b 1
)
"%ADB%" devices -l
"%ADB%" install -r "%APK%"
endlocal
pause
