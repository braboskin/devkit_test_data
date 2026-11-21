$PSNativeCommandUseErrorActionPreference = $false
$ErrorActionPreference = 'Continue'

# kb/scripts -> kb
$root    = Split-Path -Parent $PSScriptRoot
$mdPath  = Join-Path $root 'docs\SCHEMA.md'
$sqlPath = Join-Path $env:TEMP ('kb-schema-' + [guid]::NewGuid().ToString('N') + '.sql')
$tmp     = Join-Path $env:TEMP ('kb-pg-' + [guid]::NewGuid().ToString('N'))
$data    = Join-Path $tmp 'data'
$proc    = $null

# locate PostgreSQL binaries
$bin = $env:PG_BIN
if (-not $bin -or -not (Test-Path (Join-Path $bin 'postgres.exe'))) {
  $bin = $null
  if (Test-Path 'C:\Program Files\PostgreSQL') {
    $cands = Get-ChildItem 'C:\Program Files\PostgreSQL' -Directory |
      Sort-Object Name -Descending |
      ForEach-Object { Join-Path $_.FullName 'bin' }
    foreach ($c in $cands) {
      if (Test-Path (Join-Path $c 'postgres.exe')) { $bin = $c; break }
    }
  }
}
if (-not $bin) { throw 'PostgreSQL not found. Set PG_BIN env variable.' }

try {
  # 1. extract ```sql blocks in order
  $md = Get-Content -Raw -Encoding UTF8 $mdPath
  $lines = $md -split "`r?`n"
  $in = $false
  $sql = New-Object System.Collections.Generic.List[string]
  foreach ($line in $lines) {
    if ($line -match '^```sql\s*$') { $in = $true; continue }
    if ($in -and $line -match '^```\s*$') { $in = $false; continue }
    if ($in) { $sql.Add($line) }
  }
  Set-Content -Encoding UTF8 -Path $sqlPath -Value ($sql -join "`n")
  Write-Output "SQL lines extracted: $($sql.Count)"

  # 2. temporary cluster
  New-Item -ItemType Directory -Path $tmp -Force | Out-Null
  & "$bin\initdb.exe" -D $data -U postgres --auth=trust --encoding=UTF8 *> "$tmp\initdb.log"
  if (-not (Test-Path (Join-Path $data 'PG_VERSION'))) {
    Get-Content "$tmp\initdb.log" -Tail 40
    throw 'initdb failed'
  }
  Write-Output 'initdb: OK'

  # 3. start postgres directly (pg_ctl needs restricted token, unavailable in sandbox)
  $proc = Start-Process -FilePath "$bin\postgres.exe" `
      -ArgumentList @('-D', $data, '-p', '55432') `
      -RedirectStandardOutput "$tmp\pg.out" -RedirectStandardError "$tmp\pg.err" `
      -PassThru -WindowStyle Hidden
  Write-Output "postgres PID: $($proc.Id)"

  $ready = 1
  for ($i = 0; $i -lt 60; $i++) {
    & "$bin\pg_isready.exe" -h 127.0.0.1 -p 55432 *> $null
    $ready = $LASTEXITCODE
    if ($ready -eq 0) { break }
    if ($proc.HasExited) { break }
    Start-Sleep -Milliseconds 500
  }
  Write-Output "pg_isready exit: $ready"
  if ($ready -ne 0) {
    Get-Content "$tmp\pg.err" -Tail 40
    throw 'postgres start failed'
  }

  # 4. run schema
  & "$bin\psql.exe" -h 127.0.0.1 -p 55432 -U postgres -d postgres `
      -v ON_ERROR_STOP=1 -f $sqlPath *> "$tmp\psql.log"
  $rc = $LASTEXITCODE
  Write-Output "PSQL_EXIT=$rc"
  Get-Content "$tmp\psql.log" | Select-Object -Last 80

  # 5. sanity
  if ($rc -eq 0) {
    Write-Output '--- sanity ---'
    & "$bin\psql.exe" -h 127.0.0.1 -p 55432 -U postgres -d postgres -t -A -c @"
SET search_path TO kb, public;
SELECT 'tables=' || count(*) FILTER (WHERE table_type='BASE TABLE')
    || ' views=' || count(*) FILTER (WHERE table_type='VIEW')
FROM information_schema.tables WHERE table_schema='kb';
SELECT 'metric_types=' || count(*) FROM kb.metric_type;
SELECT 'event_types=' || count(*) FROM kb.event_type;
SELECT 'agent_profiles=' || count(*) FROM kb.agent_profile;
SELECT 'observations=' || count(*) FROM kb.observation;
SELECT 'transactions=' || count(*) FROM kb.v_transaction;
"@ *> "$tmp\check.log"
    Get-Content "$tmp\check.log"
  }
}
catch {
  Write-Output "ERROR: $_"
  foreach ($f in @('initdb.log','pg.out','pg.err','psql.log')) {
    if (Test-Path (Join-Path $tmp $f)) {
      Write-Output "--- $f ---"
      Get-Content (Join-Path $tmp $f) -Tail 40
    }
  }
}
finally {
  if ($proc) {
    try { if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } } catch {}
  }
  Start-Sleep -Seconds 1
  Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
  Remove-Item -Force $sqlPath -ErrorAction SilentlyContinue
  Write-Output 'Cleanup done.'
}
