# start-atlas.ps1 — поднять локальный стенд Atlas: API + ПК-воркер.
#
# Запуск:  pwsh -File .\start-atlas.ps1
# Проверка: pwsh -File .\start-atlas.ps1 -CheckOnly
# Остановка: pwsh -File .\start-atlas.ps1 -Stop
#
# Секреты читаются из .secrets\atlas.env (в git не попадает).
# Скрипт идемпотентен: уже запущенный сервер переиспользуется, воркер не дублируется.

[CmdletBinding()]
param(
    [switch]$Stop,
    [switch]$CheckOnly,
    [switch]$SkipWorker,
    [int]$Port = 8000,
    [int]$HealthTimeoutSec = 30
)

$ErrorActionPreference = 'Stop'

$Root      = $PSScriptRoot
$Repo      = Join-Path $Root 'repo\atlas'
$Python    = Join-Path $Repo '.venv\Scripts\python.exe'
$Secrets   = Join-Path $Root '.secrets'
$EnvFile   = Join-Path $Secrets 'atlas.env'
$KeyFile   = Join-Path $Secrets 'atlas-fernet.key'
$LogDir    = Join-Path $Root '.tmp\stand'
$ServerPid = Join-Path $LogDir 'server.pid'
$WorkerPid = Join-Path $LogDir 'worker.pid'
$BaseUrl   = "http://127.0.0.1:$Port"

function Write-Step([string]$Text) { Write-Host "== $Text" -ForegroundColor Cyan }
function Write-Warn([string]$Text) { Write-Host "!! $Text" -ForegroundColor Yellow }

function Import-EnvFile {
    if (-not (Test-Path $EnvFile)) { return }
    foreach ($line in Get-Content $EnvFile) {
        if ($line -match '^\s*#' -or $line -match '^\s*$') { continue }
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
            $name = $Matches[1]
            $value = $Matches[2].Trim()
            if ($value) { [Environment]::SetEnvironmentVariable($name, $value, 'Process') }
        }
    }
}

function Get-Pid([string]$Path) {
    if (-not (Test-Path $Path)) { return 0 }
    $raw = (Get-Content $Path -Raw).Trim()
    if ($raw -match '^\d+$') { return [int]$raw }
    return 0
}

function Test-Alive([int]$ProcessId) {
    if ($ProcessId -le 0) { return $false }
    return [bool](Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Stop-FromPid([string]$Path, [string]$Name) {
    $id = Get-Pid $Path
    if (Test-Alive $id) {
        Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
        Write-Host "  $Name остановлен (pid $id)"
    }
    Remove-Item $Path -Force -ErrorAction SilentlyContinue
}

function Test-Health {
    try {
        $r = Invoke-WebRequest -Uri "$BaseUrl/health" -UseBasicParsing -TimeoutSec 3
        return ($r.StatusCode -eq 200)
    } catch { return $false }
}

function Get-PortOwner {
    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $c) { return 0 }
    return [int]$c[0].OwningProcess
}

function Wait-Health {
    $deadline = (Get-Date).AddSeconds($HealthTimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-Health) { return $true }
        Start-Sleep -Milliseconds 700
    }
    return $false
}

function Show-Tail([string]$Path) {
    if (Test-Path $Path) {
        Write-Host "  последние строки ${Path}:" -ForegroundColor DarkGray
        Get-Content $Path -Tail 15 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
    }
}

# --- секреты и окружение ---------------------------------------------------
Import-EnvFile

if (-not (Test-Path $Python)) { throw "Не найден Python: $Python" }
if (-not (Test-Path $KeyFile)) { throw "Не найден $KeyFile (создай/перенеси Fernet-ключ; иначе Яндекс-токен не расшифруется)" }

if (-not $env:ATLAS_DB_URL) {
    $db = Join-Path $Secrets 'atlas.db'
    $env:ATLAS_DB_URL = 'sqlite:///' + (($db -replace '\\','/'))
}
if (-not $env:ATLAS_STORAGE_DIR) { $env:ATLAS_STORAGE_DIR = Join-Path $Secrets 'atlas-storage' }
if (-not $env:ATLAS_EMBEDDINGS) { $env:ATLAS_EMBEDDINGS = 'fake' }
if (-not $env:ATLAS_QDRANT_URL) { $env:ATLAS_QDRANT_URL = ':memory:' }
if (-not $env:ATLAS_MAX_UPLOAD_MB) { $env:ATLAS_MAX_UPLOAD_MB = '100' }
if (-not $env:ATLAS_WORKER_LEASE_MINUTES) { $env:ATLAS_WORKER_LEASE_MINUTES = '30' }
if (-not $env:ATLAS_WORKER_HEARTBEAT_SECONDS) { $env:ATLAS_WORKER_HEARTBEAT_SECONDS = '60' }
$env:ATLAS_FERNET_KEY = (Get-Content $KeyFile -Raw).Trim()
$env:ATLAS_BASE_URL = $BaseUrl

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path $env:ATLAS_STORAGE_DIR | Out-Null

$oauthEnabled = [bool]($env:YANDEX_CLIENT_ID -and $env:YANDEX_CLIENT_SECRET)

# --- остановка -------------------------------------------------------------
if ($Stop) {
    Write-Step 'Остановка стенда'
    $id = Get-Pid $WorkerPid
    if (Test-Alive $id) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue; Write-Host "  worker остановлен (pid $id)" }
    Remove-Item $WorkerPid -Force -ErrorAction SilentlyContinue
    $id = Get-Pid $ServerPid
    if (Test-Alive $id) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue; Write-Host "  server остановлен (pid $id)" }
    Remove-Item $ServerPid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
    $owner = Get-PortOwner
    if ($owner -gt 0) {
        $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$owner" -ErrorAction SilentlyContinue).CommandLine
        if ($cmd -match 'app\.backend\.main|uvicorn') {
            Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
            Write-Host "  server остановлен (pid $owner, найден по порту)"
        } else {
            Write-Warn "порт $Port всё ещё занят pid $owner — это не процесс скрипта, не трогаю"
        }
    }
    return
}

# --- проверка --------------------------------------------------------------
if ($CheckOnly) {
    Write-Step 'Проверка стенда'
    $owner = Get-PortOwner
    $health = Test-Health
    Write-Host "  server: $(if ($owner) { "pid $owner" } else { 'не запущен' })"
    Write-Host "  health: $(if ($health) { 'ok' } else { 'FAIL' })"
    if ($health) {
        try {
            $o = Invoke-RestMethod "$BaseUrl/openapi.json" -TimeoutSec 5
            $routes = @($o.paths.PSObject.Properties.Name | Where-Object { $_ -match 'reindex|yadisk/authorize|yadisk/callback' })
            Write-Host "  follow-up routes: $($routes -join ', ')"
        } catch { Write-Warn "openapi: $($_.Exception.Message)" }
    }
    $wpid = Get-Pid $WorkerPid
    Write-Host "  worker: $(if (Test-Alive $wpid) { "pid $wpid" } else { 'не запущен' })"
    Write-Host "  oauth: $(if ($oauthEnabled) { 'env задан' } else { 'env НЕ задан (authorize → 503)' })"
    return
}

# --- сервер ----------------------------------------------------------------
Write-Step "Стенд Atlas ($BaseUrl)"
$owner = Get-PortOwner
if ($owner -gt 0) {
    if (-not (Test-Health)) { throw "Порт $Port занят pid $owner, но /health не отвечает. Останови процесс вручную." }
    Write-Host "  server уже запущен (pid $owner) — переиспользую"
    Set-Content -Path $ServerPid -Value $owner -Encoding ascii
} else {
    Write-Step 'Миграции БД'
    $alembicOut = Join-Path $LogDir 'alembic.out.log'
    $alembicErr = Join-Path $LogDir 'alembic.err.log'
    $ap = Start-Process -FilePath $Python `
        -ArgumentList @('-m','alembic','upgrade','head') `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput $alembicOut `
        -RedirectStandardError $alembicErr `
        -WindowStyle Hidden -Wait -PassThru
    if ($ap.ExitCode -ne 0) { Show-Tail $alembicErr; throw "alembic upgrade failed (exit $($ap.ExitCode))" }
    Write-Host '  ok'

    Write-Step 'Запуск uvicorn'
    $sp = Start-Process -FilePath $Python `
        -ArgumentList @('-m','uvicorn','app.backend.main:app','--host','127.0.0.1','--port',"$Port") `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput (Join-Path $LogDir 'server.out.log') `
        -RedirectStandardError  (Join-Path $LogDir 'server.err.log') `
        -WindowStyle Hidden -PassThru
    Set-Content -Path $ServerPid -Value $sp.Id -Encoding ascii
    Write-Host "  pid $($sp.Id)"

    if (-not (Wait-Health)) {
        Show-Tail (Join-Path $LogDir 'server.err.log')
        throw "Сервер не поднялся за $HealthTimeoutSec c (лог: $LogDir\server.err.log)"
    }
    $actual = Get-PortOwner
    if ($actual -gt 0) { Set-Content -Path $ServerPid -Value $actual -Encoding ascii }
}

if (-not (Test-Health)) {
    Show-Tail (Join-Path $LogDir 'server.err.log')
    throw "Health check не прошёл"
}
Write-Host '  health: ok'
Write-Host "  oauth: $(if ($oauthEnabled) { 'включён' } else { 'выключен (заполни YANDEX_* в .secrets\atlas.env)' })"

# --- воркер ----------------------------------------------------------------
if ($SkipWorker) {
    Write-Warn 'worker пропущен (-SkipWorker)'
} elseif (-not $env:ATLAS_WORKER_TOKEN) {
    Write-Warn 'worker не запущен: нет ATLAS_WORKER_TOKEN в .secrets\atlas.env (создай токен в Настройках Atlas)'
} else {
    Write-Step 'Запуск воркера'
    $wpid = Get-Pid $WorkerPid
    if (Test-Alive $wpid) {
        Write-Host "  worker уже запущен (pid $wpid) — переиспользую"
    } else {
        $wp = Start-Process -FilePath $Python `
            -ArgumentList @('scripts\worker.py','--interval','5','--concurrency','1') `
            -WorkingDirectory $Repo `
            -RedirectStandardOutput (Join-Path $LogDir 'worker.out.log') `
            -RedirectStandardError  (Join-Path $LogDir 'worker.err.log') `
            -WindowStyle Hidden -PassThru
        Set-Content -Path $WorkerPid -Value $wp.Id -Encoding ascii
        Start-Sleep -Seconds 2
        if ($wp.HasExited) {
            Write-Warn "worker завершился (exit $($wp.ExitCode)); см. $LogDir\worker.err.log"
            Show-Tail (Join-Path $LogDir 'worker.err.log')
        } else {
            Write-Host "  pid $($wp.Id)"
        }
    }
}

Write-Step 'Готово'
Write-Host "  UI:       $BaseUrl/"
Write-Host "  health:   $BaseUrl/health"
Write-Host "  логи:     $LogDir"
Write-Host "  остановка: pwsh -File .\start-atlas.ps1 -Stop"
