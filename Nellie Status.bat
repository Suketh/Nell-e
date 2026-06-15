@echo off
setlocal
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File ".\scripts\status_nellie_stack.ps1"
pause
endlocal
