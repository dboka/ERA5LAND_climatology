$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Python virtual environment is missing.' }
. (Join-Path $PSScriptRoot 'postgis-env.ps1')
$logs = Join-Path $projectRoot 'data\logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$pidFile = Join-Path $logs 'arco-2026.pid'
if (Test-Path -LiteralPath $pidFile) {
    $oldPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
    $oldProcess = Get-Process -Id ([int]$oldPid) -ErrorAction SilentlyContinue
    if ($oldProcess -and $oldProcess.ProcessName -match '^python') {
        throw "ARCO 2026 import is already running (PID $oldPid)."
    }
}
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$outputLog = Join-Path $logs "arco-2026-$stamp.out.log"
$errorLog = Join-Path $logs "arco-2026-$stamp.err.log"
$process = Start-Process -FilePath $python -ArgumentList @('-m','backend.etl.arco_2026') `
    -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $outputLog `
    -RedirectStandardError $errorLog -PassThru
Set-Content -LiteralPath $pidFile -Value $process.Id
Write-Output "Started ARCO 2026 country-day import: PID $($process.Id)"
Write-Output "Progress log: $outputLog"
Write-Output "Errors: $errorLog"
