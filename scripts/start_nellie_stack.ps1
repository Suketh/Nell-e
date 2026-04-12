param(
    [switch]$Web,
    [switch]$Desktop,
    [switch]$ServicesOnly,
    [switch]$ForceRestart,
    [switch]$MobileHttps,
    [switch]$MobileExpo,
    [switch]$SkipOllamaWarmup
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RunDir = Join-Path $ProjectRoot "data\run"
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

$ConversationPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$SttPython = Join-Path $ProjectRoot ".voxtral-venv\Scripts\python.exe"
$XttsPython = Join-Path $ProjectRoot ".xtts-venv\Scripts\python.exe"
$NpmCmd = "C:\Program Files\nodejs\npm.cmd"
$NpxCmd = "C:\Program Files\nodejs\npx.cmd"

function Get-PreferredLanIp {
    $ipconfigOutput = ipconfig
    $ipMatches = [regex]::Matches($ipconfigOutput, 'IPv4 Address[^\:]*:\s*(\d+\.\d+\.\d+\.\d+)')
    foreach ($match in $ipMatches) {
        $candidate = $match.Groups[1].Value
        if ($candidate -and $candidate.StartsWith("192.168.")) { return $candidate }
    }
    foreach ($match in $ipMatches) {
        $candidate = $match.Groups[1].Value
        if ($candidate -and $candidate.StartsWith("10.")) { return $candidate }
    }
    foreach ($match in $ipMatches) {
        $candidate = $match.Groups[1].Value
        if ($candidate -and $candidate.StartsWith("172.")) { return $candidate }
    }
    foreach ($match in $ipMatches) {
        $candidate = $match.Groups[1].Value
        if ($candidate -and -not $candidate.StartsWith("127.") -and -not $candidate.StartsWith("169.254.")) {
            return $candidate
        }
    }
    return "127.0.0.1"
}

function Test-HttpOk {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Get-ConfiguredOllamaModel {
    $configPath = Join-Path $ProjectRoot "config.yaml"
    if (-not (Test-Path $configPath)) {
        return ""
    }

    foreach ($line in Get-Content -Path $configPath) {
        $modelMatch = [regex]::Match($line, '^\s*text_model\s*:\s*(.+?)\s*$')
        if ($modelMatch.Success) {
            return $modelMatch.Groups[1].Value.Trim().Trim('"').Trim("'")
        }
    }
    return ""
}

function Warmup-OllamaModel {
    if ($SkipOllamaWarmup) {
        Write-Host "[ollama] warmup skipped"
        return
    }

    $ollamaCommand = Get-Command "ollama" -ErrorAction SilentlyContinue
    if (-not $ollamaCommand) {
        Write-Host "[ollama] command not found, skipping model warmup" -ForegroundColor DarkYellow
        return
    }

    $modelName = Get-ConfiguredOllamaModel
    if (-not $modelName) {
        Write-Host "[ollama] no text_model found in config.yaml, skipping model warmup" -ForegroundColor DarkYellow
        return
    }

    Write-Host "[ollama] verifying model -> $modelName"
    & $ollamaCommand.Source show $modelName *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "[ollama] model '$modelName' is not available locally. Run: ollama pull $modelName"
    }

    $logPath = Join-Path $RunDir "ollama-warmup.log"
    $errLogPath = Join-Path $RunDir "ollama-warmup.err.log"
    Remove-Item -Force -ErrorAction SilentlyContinue $logPath, $errLogPath

    Write-Host "[ollama] warming model before app start..."
    $warmup = Start-Process -FilePath $ollamaCommand.Source `
        -ArgumentList @("run", $modelName, "Reply exactly: OK") `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $logPath `
        -RedirectStandardError $errLogPath `
        -WindowStyle "Hidden" `
        -PassThru

    if (-not $warmup.WaitForExit(120000)) {
        Stop-Process -Id $warmup.Id -Force -ErrorAction SilentlyContinue
        throw "[ollama] model warmup timed out. See log: $logPath"
    }
    if ($warmup.ExitCode -ne 0) {
        $activeModels = & $ollamaCommand.Source ps 2> $null
        if ($activeModels -match [regex]::Escape($modelName)) {
            Write-Host "[ollama] warmup returned a non-zero exit code, but the model is active" -ForegroundColor DarkYellow
        } else {
            throw "[ollama] model warmup failed. See log: $errLogPath"
        }
    }

    Write-Host "[ollama] model ready -> $modelName"
}

function Get-PidPath {
    param([string]$Name)
    return Join-Path $RunDir "$Name.pid"
}

function Get-LogPath {
    param([string]$Name)
    return Join-Path $RunDir "$Name.log"
}

function Get-ErrLogPath {
    param([string]$Name)
    return Join-Path $RunDir "$Name.err.log"
}

function Stop-ManagedProcess {
    param([string]$Name)
    $pidPath = Get-PidPath $Name
    if (-not (Test-Path $pidPath)) {
        return
    }
    $pidValue = Get-Content -Path $pidPath -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pidValue) {
        try {
            Stop-Process -Id ([int]$pidValue) -Force -ErrorAction Stop
        } catch {
        }
    }
    Remove-Item -Force -ErrorAction SilentlyContinue $pidPath
}

function Start-ManagedProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory,
        [string]$HealthUrl,
        [string]$WindowStyle = "Hidden",
        [switch]$AllowDetachedStartup
    )

    $pidPath = Get-PidPath $Name
    $logPath = Get-LogPath $Name
    $errLogPath = Get-ErrLogPath $Name

    if ($ForceRestart) {
        Stop-ManagedProcess $Name
    }

    if ($HealthUrl -and (Test-HttpOk $HealthUrl)) {
        Write-Host "[$Name] already running"
        return
    }

    if (Test-Path $pidPath) {
        $existing = Get-Content -Path $pidPath -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($existing) {
            try {
                $proc = Get-Process -Id ([int]$existing) -ErrorAction Stop
                if ($proc) {
                    Write-Host "[$Name] process already exists (PID $existing)"
                    return
                }
            } catch {
                Remove-Item -Force -ErrorAction SilentlyContinue $pidPath
            }
        }
    }

    $process = Start-Process -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $logPath `
        -RedirectStandardError $errLogPath `
        -WindowStyle $WindowStyle `
        -PassThru

    Set-Content -Path $pidPath -Value $process.Id
    Write-Host "[$Name] started (PID $($process.Id))"

    if ($HealthUrl) {
        $deadline = (Get-Date).AddSeconds(60)
        Write-Host "[$Name] warming up..."
        while ((Get-Date) -lt $deadline) {
            Start-Sleep -Milliseconds 750
            if (Test-HttpOk $HealthUrl) {
                Write-Host "[$Name] healthy -> $HealthUrl"
                return
            }
            try {
                $null = Get-Process -Id $process.Id -ErrorAction Stop
            } catch {
                if ($AllowDetachedStartup) {
                    $detachedDeadline = (Get-Date).AddSeconds(10)
                    while ((Get-Date) -lt $detachedDeadline) {
                        Start-Sleep -Milliseconds 750
                        if (Test-HttpOk $HealthUrl) {
                            Write-Host "[$Name] healthy (detached) -> $HealthUrl"
                            return
                        }
                    }
                }
                throw "[$Name] exited during startup. See log: $logPath"
            }
            Write-Host "[$Name] still starting..." -ForegroundColor DarkYellow
        }
        throw "[$Name] did not become healthy in time. See log: $logPath"
    }
}

if (-not $Web -and -not $Desktop -and -not $ServicesOnly) {
    $Web = $true
}

if (-not (Test-Path $ConversationPython)) {
    throw "Missing desktop/backend Python: $ConversationPython"
}
if (-not (Test-Path $SttPython)) {
    throw "Missing STT Python: $SttPython"
}
if (-not (Test-Path $XttsPython)) {
    throw "Missing XTTS Python: $XttsPython"
}

$env:COQUI_TOS_AGREED = "1"
Start-ManagedProcess `
    -Name "xtts" `
    -FilePath $XttsPython `
    -ArgumentList @("server\xtts_tts_server.py", "--host", "127.0.0.1", "--port", "8891", "--language", "en", "--default-voice-sample", "assets/voices/Nellie1.wav") `
    -WorkingDirectory $ProjectRoot `
    -HealthUrl "http://127.0.0.1:8891/health" `
    -WindowStyle "Hidden"

Start-ManagedProcess `
    -Name "conversation" `
    -FilePath $ConversationPython `
    -ArgumentList @("server\conversation_server.py", "--host", "0.0.0.0", "--port", "8877") `
    -WorkingDirectory $ProjectRoot `
    -HealthUrl "http://127.0.0.1:8877/health" `
    -WindowStyle "Hidden"

Start-ManagedProcess `
    -Name "stt" `
    -FilePath $SttPython `
    -ArgumentList @("server\stt_server.py", "--host", "0.0.0.0", "--port", "8765", "--provider", "faster_whisper", "--model", "small", "--device", "cpu", "--compute-type", "int8") `
    -WorkingDirectory $ProjectRoot `
    -HealthUrl "http://127.0.0.1:8765/health" `
    -WindowStyle "Hidden"

Warmup-OllamaModel

if ($Web) {
    if (-not (Test-Path $NpmCmd)) {
        throw "Missing npm: $NpmCmd"
    }
    if ($MobileHttps) {
        $env:NELLIE_WEB_HTTPS = "1"
        Write-Host "[web] mobile HTTPS mode enabled"
    } else {
        Remove-Item Env:NELLIE_WEB_HTTPS -ErrorAction SilentlyContinue
    }
    Start-ManagedProcess `
        -Name "web" `
        -FilePath $NpmCmd `
        -ArgumentList @("run", "dev", "--", "--host", "0.0.0.0", "--port", "5173") `
        -WorkingDirectory (Join-Path $ProjectRoot "web") `
        -HealthUrl $(if ($MobileHttps) { "" } else { "http://127.0.0.1:5173" }) `
        -WindowStyle "Hidden" `
        -AllowDetachedStartup
}

if ($MobileExpo) {
    if (-not (Test-Path $NpxCmd)) {
        throw "Missing npx: $NpxCmd"
    }
    $LanIp = Get-PreferredLanIp
    $env:EXPO_PUBLIC_NELLIE_API_BASE = "http://${LanIp}:8877/v1"
    $env:EXPO_PUBLIC_NELLIE_STT_BASE = "http://${LanIp}:8765"
    $env:EXPO_PUBLIC_NELLIE_ADMIN_WEB_URL = "http://${LanIp}:5173"
    $env:REACT_NATIVE_PACKAGER_HOSTNAME = $LanIp
    $env:EXPO_NO_INTERACTIVE = "1"
    Write-Host "[mobile] expo LAN mode -> $LanIp"
    Write-Host "[mobile] API -> $($env:EXPO_PUBLIC_NELLIE_API_BASE)"
    Start-ManagedProcess `
        -Name "mobile" `
        -FilePath $NpxCmd `
        -ArgumentList @("expo", "start", "--lan", "--port", "8081", "--clear") `
        -WorkingDirectory (Join-Path $ProjectRoot "mobile") `
        -HealthUrl "" `
        -WindowStyle "Normal"
}

if ($Desktop) {
    Start-ManagedProcess `
        -Name "desktop" `
        -FilePath $ConversationPython `
        -ArgumentList @("app.py") `
        -WorkingDirectory $ProjectRoot `
        -HealthUrl "" `
        -WindowStyle "Normal"
}

Write-Host ""
Write-Host "Ready:"
Write-Host "  XTTS:         http://127.0.0.1:8891"
Write-Host "  Conversation: http://0.0.0.0:8877"
Write-Host "  STT:          http://0.0.0.0:8765"
if ($Web) {
    if ($MobileHttps) {
        Write-Host "  Web:          https://127.0.0.1:5173"
    } else {
        Write-Host "  Web:          http://127.0.0.1:5173"
    }
}
if ($MobileExpo) {
    $LanIp = Get-PreferredLanIp
    Write-Host "  Mobile Expo:  exp://$LanIp`:8081"
}
if ($Desktop) {
    Write-Host "  Desktop:      app.py launched"
}
