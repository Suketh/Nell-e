$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RunDir = Join-Path $ProjectRoot "data\run"

function Test-HttpOk {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Get-ServiceState {
    param(
        [string]$Name,
        [string]$Url
    )

    if (Test-HttpOk $Url) {
        return "UP"
    }

    $pidPath = Join-Path $RunDir "$Name.pid"
    if (Test-Path $pidPath) {
        $pidValue = Get-Content -Path $pidPath -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($pidValue) {
            try {
                $null = Get-Process -Id ([int]$pidValue) -ErrorAction Stop
                return "STARTING"
            } catch {
                return "DOWN"
            }
        }
    }
    return "DOWN"
}

Write-Host ("XTTS:         " + (Get-ServiceState "xtts" "http://127.0.0.1:8891/health"))
Write-Host ("Conversation: " + (Get-ServiceState "conversation" "http://127.0.0.1:8877/health"))
Write-Host ("STT:          " + (Get-ServiceState "stt" "http://127.0.0.1:8765/health"))
Write-Host ("Web:          " + (Get-ServiceState "web" "http://127.0.0.1:5173"))
