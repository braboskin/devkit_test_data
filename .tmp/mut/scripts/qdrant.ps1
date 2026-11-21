param(
    [ValidateSet('download', 'start', 'stop', 'status')]
    [string]$Action = 'status'
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$qdrantDir = Join-Path $root '.qdrant'
$exe = Join-Path $qdrantDir 'qdrant.exe'
$pidFile = Join-Path $qdrantDir 'qdrant.pid'
$log = Join-Path $qdrantDir 'qdrant.log'
$err = Join-Path $qdrantDir 'qdrant.err.log'
$version = '1.20.2'

function Get-QdrantPid {
    if (Test-Path $pidFile) {
        $value = Get-Content $pidFile -ErrorAction SilentlyContinue
        if ($value) { return [int]$value }
    }
    return $null
}

switch ($Action) {
    'download' {
        if (Test-Path $exe) {
            Write-Output "Qdrant уже скачан: $exe"
            exit 0
        }
        New-Item -ItemType Directory -Force -Path $qdrantDir | Out-Null
        $url = "https://github.com/qdrant/qdrant/releases/download/v$version/qdrant-x86_64-pc-windows-msvc.zip"
        $zip = Join-Path $qdrantDir 'qdrant.zip'
        Write-Output "Скачиваю $url"
        Invoke-WebRequest -Uri $url -OutFile $zip
        Expand-Archive -Path $zip -DestinationPath $qdrantDir -Force
        Write-Output "Готово: $exe"
    }
    'start' {
        if (-not (Test-Path $exe)) {
            throw "qdrant.exe не найден. Сначала: .\scripts\qdrant.ps1 download"
        }
        $existing = Get-QdrantPid
        if ($existing -and (Get-Process -Id $existing -ErrorAction SilentlyContinue)) {
            Write-Output "Qdrant уже запущен (pid $existing)"
            exit 0
        }
        New-Item -ItemType Directory -Force -Path (Join-Path $qdrantDir 'storage') | Out-Null
        $env:QDRANT__STORAGE__STORAGE_PATH = (Join-Path $qdrantDir 'storage')
        $env:QDRANT__SERVICE__HTTP_PORT = '6333'
        $env:QDRANT__SERVICE__GRPC_PORT = '6334'
        $env:QDRANT__TELEMETRY_DISABLED = 'true'
        $process = Start-Process -FilePath $exe -WorkingDirectory $qdrantDir `
            -RedirectStandardOutput $log -RedirectStandardError $err `
            -WindowStyle Hidden -PassThru
        $process.Id | Set-Content $pidFile
        for ($i = 0; $i -lt 30; $i++) {
            Start-Sleep -Milliseconds 500
            try {
                $response = Invoke-WebRequest 'http://127.0.0.1:6333/healthz' `
                    -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
                if ($response.StatusCode -eq 200) {
                    Write-Output "Qdrant запущен (pid $($process.Id))"
                    exit 0
                }
            } catch {
                # ещё стартует
            }
        }
        throw "Qdrant не ответил за 15 секунд. Смотрите $log"
    }
    'stop' {
        $existing = Get-QdrantPid
        if ($existing) {
            Stop-Process -Id $existing -Force -ErrorAction SilentlyContinue
            Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
            Write-Output "Qdrant остановлен (pid $existing)"
        } else {
            Write-Output 'Qdrant не запущен'
        }
    }
    'status' {
        $existing = Get-QdrantPid
        if ($existing -and (Get-Process -Id $existing -ErrorAction SilentlyContinue)) {
            try {
                $response = Invoke-WebRequest 'http://127.0.0.1:6333/healthz' `
                    -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
                Write-Output "Qdrant: running (pid $existing), health $($response.StatusCode)"
            } catch {
                Write-Output "Qdrant: process $existing, health error"
            }
        } else {
            Write-Output 'Qdrant: stopped'
        }
    }
}
