$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RunDir = Join-Path $ProjectRoot "data\run"

function Stop-ManagedProcess {
    param([string]$Name)
    $pidPath = Join-Path $RunDir "$Name.pid"
    if (-not (Test-Path $pidPath)) {
        Write-Host "[$Name] no pid file"
        return
    }
    $pidValue = Get-Content -Path $pidPath -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pidValue) {
        try {
            Stop-Process -Id ([int]$pidValue) -Force -ErrorAction Stop
            Write-Host "[$Name] stopped"
        } catch {
            Write-Host "[$Name] not running"
        }
    }
    Remove-Item -Force -ErrorAction SilentlyContinue $pidPath
}

function Stop-ListenerOnPort {
    param([int]$Port)
    $matches = netstat -ano | Select-String ":$Port"
    $pids = @()
    foreach ($line in $matches) {
        $text = ($line.ToString() -replace "\s+", " ").Trim()
        $parts = $text.Split(" ")
        if ($parts.Length -ge 5) {
            $pidValue = $parts[-1]
            if ($pidValue -match "^\d+$") {
                $pids += [int]$pidValue
            }
        }
    }
    $pids = $pids | Select-Object -Unique
    foreach ($pidValue in $pids) {
        try {
            Stop-Process -Id $pidValue -Force -ErrorAction Stop
            Write-Host "[port $Port] stopped PID $pidValue"
        } catch {
        }
    }
}

Stop-ManagedProcess "desktop"
Stop-ManagedProcess "mobile"
Stop-ListenerOnPort 8081
Stop-ManagedProcess "web"
Stop-ManagedProcess "stt"
Stop-ManagedProcess "conversation"
Stop-ManagedProcess "xtts"
