$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$logs = Join-Path $projectRoot 'data\logs'
$pidFile = Join-Path $logs 'arco-backfill.pid'
if (Test-Path -LiteralPath $pidFile) {
    $jobPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
    $jobProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $jobPid" -ErrorAction SilentlyContinue
    if ($jobProcess -and $jobProcess.Name -match '^python' -and $jobProcess.CommandLine -match 'backend\.etl\.arco_backfill') {
        Write-Output "ARCO historical import running (PID $jobPid)"
    } else {
        Write-Output "ARCO historical import stopped (last PID $jobPid)"
    }
}
$latest = Get-ChildItem -LiteralPath $logs -Filter 'arco-backfill-*.out.log' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($latest) {
    Write-Output "Latest progress: $($latest.FullName)"
    Get-Content -LiteralPath $latest.FullName -Tail 5
}
$latestError = Get-ChildItem -LiteralPath $logs -Filter 'arco-backfill-*.err.log' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($latestError -and $latestError.Length -gt 0) {
    Write-Output "Latest error: $($latestError.FullName)"
    Get-Content -LiteralPath $latestError.FullName -Tail 5
}
& docker compose -f (Join-Path $projectRoot 'compose.yaml') exec -T db psql -U climate -d climate -Atc `
    "SELECT 'baseline_days=' || COUNT(DISTINCT day) || ', last=' || MAX(day) FROM baseline_daily; SELECT 'display_days=' || COUNT(DISTINCT day) || ', last=' || MAX(day) FROM daily; SELECT 'normals=' || COUNT(*) FROM normals; SELECT 'mode=' || mode FROM dataset_info WHERE id=1;" 2>$null
