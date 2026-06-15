@echo off
setlocal

echo Voxtral WSL2 launch template for Nellie
echo.
echo This file is only a template.
echo It does not start Voxtral until you replace the placeholder command.
echo.
echo Target endpoint for Nellie:
echo   http://127.0.0.1:8000/v1/audio/transcriptions
echo.
echo Example shape:
echo   wsl -d Ubuntu -- bash -lc "<your real voxtral server command>"
echo.
echo Put the finished command into config.yaml under:
echo   stt.voxtral_self_hosted_launch
echo.
pause
