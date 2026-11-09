$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Python virtual environment is missing.' }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'node_modules'))) { throw 'Node dependencies are missing; run npm install.' }

Push-Location $projectRoot
try {
    docker compose up -d db | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'PostGIS did not start.' }
    . (Join-Path $PSScriptRoot 'postgis-env.ps1')
    $env:CLIMATE_DEMO = '0'
    $mode = & $python -c "from backend.db import scalar; print(scalar('SELECT mode FROM dataset_info WHERE id=1'))"
    if ($LASTEXITCODE -ne 0 -or $mode.Trim() -ne 'era5_land') { throw 'Real ERA5-Land database is not ready.' }

    $logs = Join-Path $projectRoot 'data\logs'
    New-Item -ItemType Directory -Path $logs -Force | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $apiPort = Get-NetTCPConnection -State Listen -LocalPort 8013 -ErrorAction SilentlyContinue
    if (-not $apiPort) {
        $api = Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','backend.app:app','--host','127.0.0.1','--port','8013') `
            -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs "api-$stamp.out.log") `
            -RedirectStandardError (Join-Path $logs "api-$stamp.err.log") -PassThru
        Set-Content -LiteralPath (Join-Path $logs 'local-api.pid') -Value $api.Id
    }
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $meta = Invoke-RestMethod -Uri 'http://127.0.0.1:8013/api/meta' -TimeoutSec 2
            if ($meta.mode -eq 'era5_land') { $ready = $true; break }
            throw 'Port 8013 serves non-ERA5-Land data.'
        } catch {
            if ($_.Exception.Message -match 'non-ERA5-Land') { throw }
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $ready) { throw 'Real-data API did not become ready on port 8013.' }

    $sitePort = Get-NetTCPConnection -State Listen -LocalPort 5173 -ErrorAction SilentlyContinue
    if (-not $sitePort) {
        $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
        $site = Start-Process -FilePath $npm -ArgumentList @('run','dev') -WorkingDirectory $projectRoot `
            -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs "site-$stamp.out.log") `
            -RedirectStandardError (Join-Path $logs "site-$stamp.err.log") -PassThru
        Set-Content -LiteralPath (Join-Path $logs 'local-site.pid') -Value $site.Id
    }
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri 'http://127.0.0.1:5173/' -TimeoutSec 2 -UseBasicParsing
            if ($response.StatusCode -eq 200) { $ready = $true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $ready) { throw 'Website did not become ready on port 5173.' }
    Write-Output "Website: http://127.0.0.1:5173/"
    Write-Output "API: http://127.0.0.1:8013/api/meta"
    Write-Output "Mode: $($meta.mode); data through $($meta.latest_date); $($meta.countries_with_data) countries with data."
} finally {
    Pop-Location
}
