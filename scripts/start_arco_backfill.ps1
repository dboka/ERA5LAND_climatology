$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Python virtual environment is missing.' }
. (Join-Path $PSScriptRoot 'postgis-env.ps1')
$logs = Join-Path $projectRoot 'data\logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$pidFile = Join-Path $logs 'arco-backfill.pid'
if (Test-Path -LiteralPath $pidFile) {
    $oldPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
    $oldProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $oldPid" -ErrorAction SilentlyContinue
    if ($oldProcess -and $oldProcess.Name -match '^python' -and $oldProcess.CommandLine -match 'backend\.etl\.arco_backfill') {
        Write-Output "ARCO backfill already running (PID $oldPid)."
        exit 0
    }
}
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$outputLog = Join-Path $logs "arco-backfill-$stamp.out.log"
$errorLog = Join-Path $logs "arco-backfill-$stamp.err.log"
$process = Start-Process -FilePath $python -ArgumentList @('-m','backend.etl.arco_backfill') `
    -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $outputLog `
    -RedirectStandardError $errorLog -PassThru
Set-Content -LiteralPath $pidFile -Value $process.Id
Write-Output "Started ARCO historical import: PID $($process.Id)"
Write-Output "Progress log: $outputLog"
Write-Output "Errors: $errorLog"
