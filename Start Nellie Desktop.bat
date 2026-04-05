@echo off
setlocal
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File ".\scripts\start_nellie_stack.ps1" -Desktop
pause
endlocal
