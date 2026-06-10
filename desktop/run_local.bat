@echo off
setlocal
title Nellie

set "PROJECT_DIR=%~dp0"
set "PYTHON_EXE=%PROJECT_DIR%.venv\Scripts\python.exe"
set "CHATTERBOX_PYTHON=%PROJECT_DIR%.venv_chatterbox\Scripts\python.exe"
set "SOX_DIR=%PROJECT_DIR%tools\sox"

if not exist "%PYTHON_EXE%" (
  echo Python 3.11 runtime not found:
  echo %PYTHON_EXE%
  exit /b 1
)

if not exist "%CHATTERBOX_PYTHON%" (
  echo Chatterbox-Turbo runtime not found:
  echo %CHATTERBOX_PYTHON%
  echo XTTS fallback remains available, but run the Chatterbox setup before using Turbo.
)

if exist "%SOX_DIR%\sox.exe" (
  set "PATH=%SOX_DIR%;%PATH%"
)

cd /d "%PROJECT_DIR%"
"%PYTHON_EXE%" app.py
exit /b %ERRORLEVEL%
