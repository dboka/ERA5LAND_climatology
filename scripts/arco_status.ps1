$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$logs = Join-Path $projectRoot 'data\logs'
$pidFile = Join-Path $logs 'arco-2026.pid'
if (Test-Path -LiteralPath $pidFile) {
    $jobPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
    $jobProcess = Get-Process -Id ([int]$jobPid) -ErrorAction SilentlyContinue
    if ($jobProcess -and $jobProcess.ProcessName -match '^python') {
        Write-Output "ARCO process running (PID $jobPid)"
    } else {
        Write-Output "ARCO process stopped (last PID $jobPid)"
    }
}
$latest = Get-ChildItem -LiteralPath $logs -Filter 'arco-2026-*.out.log' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($latest) {
    Write-Output "Latest progress: $($latest.FullName)"
    Get-Content -LiteralPath $latest.FullName -Tail 4
}
docker compose -f (Join-Path $projectRoot 'compose.yaml') exec -T db psql -U climate -d climate -Atc `
    "SELECT 'days=' || COUNT(DISTINCT day) FROM daily WHERE day >= DATE '2026-01-01' AND day < DATE '2027-01-01'; SELECT 'rows=' || COUNT(*) FROM daily WHERE day >= DATE '2026-01-01' AND day < DATE '2027-01-01'; SELECT 'normals=' || COUNT(*) FROM normals;" 2>$null
