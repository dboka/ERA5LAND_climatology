$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$logs = Join-Path $projectRoot 'data\logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$log = Join-Path $logs ("daily-update-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
Start-Transcript -LiteralPath $log -Force | Out-Null

function Invoke-Native([scriptblock]$command, [string]$description) {
    # Windows PowerShell 5 can surface ordinary native stderr as an ErrorRecord.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $command
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0) { throw "$description failed (exit $code)." }
}

try {
    if (-not (Test-Path -LiteralPath $python)) { throw 'Python virtual environment is missing.' }
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'node_modules'))) { throw 'Node dependencies are missing.' }
    Push-Location $projectRoot
    try {
        Write-Output "Daily update started: $(Get-Date -Format o)"
        $dockerReady = $false
        for ($attempt = 1; $attempt -le 90; $attempt++) {
            $previous = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try {
                docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
                $dockerExit = $LASTEXITCODE
            } finally {
                $ErrorActionPreference = $previous
            }
            if ($dockerExit -eq 0) { $dockerReady = $true; break }
            if ($attempt -eq 1) {
                $desktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
                if (Test-Path -LiteralPath $desktop) {
                    Write-Output 'Starting Docker Desktop.'
                    Start-Process -FilePath $desktop -WindowStyle Hidden | Out-Null
                }
            }
            Start-Sleep -Seconds 10
        }
        if (-not $dockerReady) { throw 'Docker engine unavailable after 15 minutes.' }
        Invoke-Native { docker compose up -d db } 'PostGIS start'
        $dbReady = $false
        for ($attempt = 1; $attempt -le 60; $attempt++) {
            $previous = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try {
                docker compose exec -T db pg_isready -U climate -d climate 2>$null | Out-Null
                $dbExit = $LASTEXITCODE
            } finally {
                $ErrorActionPreference = $previous
            }
            if ($dbExit -eq 0) { $dbReady = $true; break }
            Start-Sleep -Seconds 5
        }
        if (-not $dbReady) { throw 'PostGIS unavailable after 5 minutes.' }

        . (Join-Path $PSScriptRoot 'postgis-env.ps1')
        $env:CLIMATE_DEMO = '0'
        & (Join-Path $PSScriptRoot 'start_local_site.ps1')
        Invoke-Native { & $python -u -m backend.etl.arco_daily_update } 'ARCO daily import'
        Invoke-Native { & $python -m backend.export_static } 'Static data export'
        $env:VITE_STATIC_DATA = '1'
        $env:GITHUB_PAGES = '1'
        Invoke-Native { npm.cmd run build } 'GitHub Pages build'
        Write-Output "Daily update finished: $(Get-Date -Format o)"
    } finally {
        Pop-Location
    }
    exit 0
} catch {
    Write-Output "Daily update failed: $($_.Exception.Message)"
    exit 1
} finally {
    Stop-Transcript | Out-Null
}
