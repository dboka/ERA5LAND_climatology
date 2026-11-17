$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$logs = Join-Path $projectRoot 'data\logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$log = Join-Path $logs 'precipitation-auto-resume.log'
function Write-ResumeLog([string]$message) {
    Add-Content -LiteralPath $log -Value "$(Get-Date -Format o) $message"
}
try {
    $dockerReady = $false
    for ($attempt = 1; $attempt -le 90; $attempt++) {
        & docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $dockerReady = $true; break }
        if ($attempt -eq 1) {
            $desktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
            if (Test-Path -LiteralPath $desktop) {
                Write-ResumeLog 'Starting Docker Desktop.'
                Start-Process -FilePath $desktop -WindowStyle Hidden
            }
        }
        Start-Sleep -Seconds 10
    }
    if (-not $dockerReady) { throw 'Docker engine unavailable after 15 minutes.' }
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & docker compose -f (Join-Path $projectRoot 'compose.yaml') up -d db 2>&1 | Out-Null
        $composeExit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($composeExit -ne 0) { throw 'Could not start PostGIS container.' }
    $dbReady = $false
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        & docker compose -f (Join-Path $projectRoot 'compose.yaml') exec -T db pg_isready -U climate -d climate 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $dbReady = $true; break }
        Start-Sleep -Seconds 5
    }
    if (-not $dbReady) { throw 'PostGIS unavailable after 5 minutes.' }
    $normalCount = (& docker compose -f (Join-Path $projectRoot 'compose.yaml') exec -T db psql `
        -U climate -d climate -Atc 'SELECT COUNT(*) FROM precipitation_normals' 2>$null | Out-String).Trim()
    if ($normalCount -eq '68808') { Write-ResumeLog 'Precipitation archive already complete.'; exit 0 }
    $result = & (Join-Path $PSScriptRoot 'start_precipitation_backfill.ps1') 2>&1
    Write-ResumeLog (($result | Out-String).Trim())
} catch {
    Write-ResumeLog "Automatic resume failed: $($_.Exception.Message)"
    exit 1
}
