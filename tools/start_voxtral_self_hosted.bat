@echo off
setlocal

echo Voxtral self-hosted helper for Nellie
echo.
echo Nellie expects a local OpenAI-compatible transcription endpoint at:
echo   http://127.0.0.1:8000/v1/audio/transcriptions
echo.
echo Recommended future shape:
echo   - XTTS inside the app
echo   - Voxtral in a separate local runtime
echo   - preferably WSL2 + vLLM or equivalent
echo.

set "NELLIE_STT_MODE=self_hosted"
set "NELLIE_STT_URL=http://127.0.0.1:8000"

echo Expected server base URL: %NELLIE_STT_URL%
echo.
echo This helper does not yet know your actual Voxtral launch command.
echo Once you have it, put it in config.yaml under:
echo   stt.voxtral_self_hosted_launch
echo and optionally:
echo   stt.voxtral_self_hosted_workdir
echo.
pause
