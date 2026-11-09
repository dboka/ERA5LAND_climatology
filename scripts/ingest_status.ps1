$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$logs = Join-Path $projectRoot 'data\logs'
$pidFile = Join-Path $logs 'full-ingest.pid'
if (Test-Path -LiteralPath $pidFile) {
    $jobPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
    $jobProcess = Get-Process -Id ([int]$jobPid) -ErrorAction SilentlyContinue
    if ($jobProcess -and $jobProcess.ProcessName -match '^python') {
        Write-Output "Import process running (PID $jobPid)"
    } else {
        Write-Output "Import process stopped (last PID $jobPid)"
    }
}
$latest = Get-ChildItem -LiteralPath $logs -Filter 'full-ingest-*.out.log' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($latest) {
    Write-Output "Latest progress: $($latest.FullName)"
    Get-Content -LiteralPath $latest.FullName -Tail 8
}
$stopLog = Get-ChildItem -LiteralPath $logs -Filter 'stop-after-*.log' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($stopLog) {
    $stopState = Get-Content -LiteralPath $stopLog.FullName -Tail 1
    if ($stopState -notmatch 'cancelled') {
        Write-Output "Stop control: $($stopLog.FullName)"
        Write-Output $stopState
    }
}
docker compose -f (Join-Path $projectRoot 'compose.yaml') exec -T db psql -U climate -d climate -Atc `
    "SELECT 'mode=' || COALESCE((SELECT mode FROM dataset_info WHERE id=1),'empty'); SELECT 'months=' || COUNT(*) FROM ingested_months; SELECT 'baseline_rows=' || COUNT(*) FROM baseline_daily;" 2>$null
