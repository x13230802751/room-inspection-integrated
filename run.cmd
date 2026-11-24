@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch.ps1" %*
set "TASK1_EXIT=%ERRORLEVEL%"
if not "%TASK1_EXIT%"=="0" if not "%TASK1_NO_PAUSE%"=="1" pause
exit /b %TASK1_EXIT%
