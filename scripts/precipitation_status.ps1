$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$logs = Join-Path $projectRoot 'data\logs'
$pidFile = Join-Path $logs 'precipitation-backfill.pid'
if (Test-Path -LiteralPath $pidFile) {
    $jobPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
    $jobProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $jobPid" -ErrorAction SilentlyContinue
    if ($jobProcess -and $jobProcess.Name -match '^python' -and
        $jobProcess.CommandLine -match 'backend\.etl\.arco_precipitation') {
        Write-Output "Precipitation import running (PID $jobPid)"
    } else {
        Write-Output "Precipitation import stopped (last PID $jobPid)"
    }
}
$latest = Get-ChildItem -LiteralPath $logs -Filter 'precipitation-backfill-*.out.log' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($latest) {
    Write-Output "Latest progress: $($latest.FullName)"
    Get-Content -LiteralPath $latest.FullName -Tail 5
}
$latestError = Get-ChildItem -LiteralPath $logs -Filter 'precipitation-backfill-*.err.log' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($latestError -and $latestError.Length -gt 0) {
    Write-Output "Latest error: $($latestError.FullName)"
    Get-Content -LiteralPath $latestError.FullName -Tail 8
}
& docker compose -f (Join-Path $projectRoot 'compose.yaml') exec -T db psql -U climate -d climate -Atc `
    "SELECT 'baseline_days=' || COUNT(DISTINCT day) || ', last=' || COALESCE(MAX(day)::text,'none') FROM precipitation_baseline_daily; SELECT 'display_days=' || COUNT(DISTINCT day) || ', last=' || COALESCE(MAX(day)::text,'none') FROM precipitation_daily; SELECT 'normals=' || COUNT(*) FROM precipitation_normals;" 2>$null
