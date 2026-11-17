$projectRoot = Split-Path -Parent $PSScriptRoot
$task = Get-ScheduledTask -TaskName 'GlobalClimateDailyUpdate' -ErrorAction SilentlyContinue
if ($task) {
    $info = $task | Get-ScheduledTaskInfo
    Write-Output "Task: $($task.State); last run $($info.LastRunTime); result $($info.LastTaskResult); next run $($info.NextRunTime)"
} else {
    Write-Output 'Task: not installed'
}
$latestLog = Get-ChildItem -LiteralPath (Join-Path $projectRoot 'data\logs') -Filter 'daily-update-*.log' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($latestLog) {
    Write-Output "Log: $($latestLog.FullName)"
    Get-Content -LiteralPath $latestLog.FullName -Tail 8
}
$metaFile = Join-Path $projectRoot 'public\data\meta.json'
if (Test-Path -LiteralPath $metaFile) {
    $meta = Get-Content -LiteralPath $metaFile -Raw | ConvertFrom-Json
    Write-Output "Static temperature latest: $($meta.latest_date)"
}
$precipMetaFile = Join-Path $projectRoot 'public\data\precipitation\meta.json'
if (Test-Path -LiteralPath $precipMetaFile) {
    $precipMeta = Get-Content -LiteralPath $precipMetaFile -Raw | ConvertFrom-Json
    Write-Output "Static precipitation latest: $($precipMeta.latest_date)"
}
Push-Location $projectRoot
try {
    & docker compose exec -T db psql -U climate -d climate -Atc `
        "SELECT 'PostGIS temperature latest: ' || MAX(day) || '; countries: ' || COUNT(DISTINCT iso3) FROM daily; SELECT 'PostGIS precipitation latest: ' || MAX(day) || '; countries: ' || COUNT(DISTINCT iso3) FROM precipitation_daily" 2>$null
} finally {
    Pop-Location
}
