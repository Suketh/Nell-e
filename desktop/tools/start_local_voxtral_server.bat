@echo off
setlocal
cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
  echo Python environment not found at .venv\Scripts\python.exe
  exit /b 1
)

".venv\Scripts\python.exe" tools\local_voxtral_server.py --host 127.0.0.1 --port 8080 --model-size small.en --device auto --language en
