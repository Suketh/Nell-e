$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".voxtral-venv\Scripts\python.exe"
$ModelPath = Join-Path $ProjectRoot "models\Voxtral-Mini-4B-Realtime-2602"
$ServerScript = Join-Path $ProjectRoot "server\stt_server.py"

if (-not (Test-Path $Python)) {
    throw "Missing .voxtral-venv python at $Python"
}

if (-not (Test-Path $ModelPath)) {
    throw "Missing Voxtral model at $ModelPath"
}

& $Python $ServerScript `
    --provider local_voxtral `
    --voxtral-model-path $ModelPath `
    --language sv
