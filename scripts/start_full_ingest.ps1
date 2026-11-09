$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Python virtual environment is missing.' }
. (Join-Path $PSScriptRoot 'postgis-env.ps1')
$logs = Join-Path $projectRoot 'data\logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$pidFile = Join-Path $logs 'full-ingest.pid'
if (Test-Path -LiteralPath $pidFile) {
    $oldPid = Get-Content -LiteralPath $pidFile -Raw
    $oldProcess = Get-Process -Id ([int]$oldPid.Trim()) -ErrorAction SilentlyContinue
    if ($oldProcess -and $oldProcess.ProcessName -match '^python') {
        throw "Full ERA5-Land ingest is already running (PID $oldPid)."
    }
}
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$outputLog = Join-Path $logs "full-ingest-$stamp.out.log"
$errorLog = Join-Path $logs "full-ingest-$stamp.err.log"
$process = Start-Process -FilePath $python -ArgumentList @('-m','backend.etl.ingest','--stream') `
    -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $outputLog `
    -RedirectStandardError $errorLog -PassThru
Set-Content -LiteralPath $pidFile -Value $process.Id
Write-Output "Started full ERA5-Land import: PID $($process.Id)"
Write-Output "Progress log: $outputLog"
Write-Output "Errors and CDS messages: $errorLog"
