@echo off
setlocal
set "ADB=D:\Program Files\Netease\MuMu\nx_main\adb.exe"
if not exist "%ADB%" set "ADB=C:\Program Files\Netease\MuMu\nx_main\adb.exe"
if not exist "%ADB%" (
  echo MuMu adb.exe not found. Edit the ADB path in this file.
  exit /b 1
)
"%ADB%" devices -l
"%ADB%" shell dumpsys package com.sahanaz.mumu.vectorcleaner ^| findstr /i "versionCode versionName"
"%ADB%" shell pm path app.lawnchair
endlocal
pause
