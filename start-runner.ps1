# start-runner.ps1 - start the self-hosted GitHub Actions runner (atlas-pc).
#
# Usage (from the project root, after PC reboot):
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\start-runner.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\start-runner.ps1 -Status
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\start-runner.ps1 -Stop
#
# The runner must be configured once (token): scripts\setup-ci-runner.ps1 in repo/atlas.
# This script does not need a token and starts the runner in a separate window.

[CmdletBinding()]
param(
    [string]$RunnerDir = "C:\actions-runner-atlas",
    [switch]$Stop,
    [switch]$Status
)

$ErrorActionPreference = 'Stop'

function Get-RunnerProcess {
    Get-Process -Name 'Runner.Listener', 'Runner.Worker' -ErrorAction SilentlyContinue
}

function Show-Status {
    $procs = Get-RunnerProcess
    if (-not $procs) {
        Write-Host "runner: not running"
        return $false
    }
    $procs | ForEach-Object { Write-Host "runner: running pid=$($_.Id) ($($_.ProcessName))" }
    return $true
}

if ($Status) {
    [void](Show-Status)
    if (Test-Path (Join-Path $RunnerDir '.runner')) {
        Write-Host "config: $RunnerDir\.runner"
    } else {
        Write-Host "config: missing in $RunnerDir (run scripts\setup-ci-runner.ps1)"
    }
    return
}

if ($Stop) {
    $procs = Get-RunnerProcess
    if (-not $procs) {
        Write-Host "runner: already stopped"
        return
    }
    $procs | Stop-Process -Force -ErrorAction SilentlyContinue
    # close the cmd window started by run.cmd, if any
    Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 'run\.cmd' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 800
    if (Get-RunnerProcess) { throw "runner still running after stop" }
    Write-Host "runner: stopped"
    return
}

if (-not (Test-Path (Join-Path $RunnerDir '.runner'))) {
    throw "Runner is not configured in $RunnerDir. Run once: powershell -NoProfile -ExecutionPolicy Bypass -File repo\atlas\scripts\setup-ci-runner.ps1 -Token <TOKEN>"
}

if (Show-Status) {
    Write-Host "runner: already running, nothing to do"
    return
}

Write-Host "== Starting runner from $RunnerDir"
Start-Process -FilePath (Join-Path $RunnerDir 'run.cmd') -WorkingDirectory $RunnerDir
Start-Sleep -Seconds 4

if (Show-Status) {
    Write-Host "== Runner window is open; keep it running while CI is needed"
    Write-Host "   GitHub: https://github.com/xaylpq/atlas/settings/actions/runners"
} else {
    $diag = Join-Path $RunnerDir '_diag'
    $log = Get-ChildItem $diag -Filter 'Runner_*.log' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($log) { Get-Content $log.FullName -Tail 20 }
    throw "Runner did not start; see logs in $diag"
}
