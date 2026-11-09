$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$logs = Join-Path $projectRoot 'data\logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$log = Join-Path $logs 'auto-resume.log'
$enabled = Join-Path $logs 'auto-resume.enabled'
$pidFile = Join-Path $logs 'full-ingest.pid'
$startsLog = Join-Path $logs 'auto-resume-starts.log'

function Write-ResumeLog([string]$message) {
    Add-Content -LiteralPath $log -Value "$(Get-Date -Format o) $message"
}

if (-not (Test-Path -LiteralPath $enabled)) {
    Write-ResumeLog 'Automatic resume disabled; no action.'
    exit 0
}

try {
    if (Test-Path -LiteralPath $pidFile) {
        $oldPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $oldPid" -ErrorAction SilentlyContinue
        if ($process -and $process.Name -match '^python' -and $process.CommandLine -match 'backend\.etl\.ingest.*--stream') {
            exit 0
        }
    }

    $now = Get-Date
    $recentStarts = @()
    if (Test-Path -LiteralPath $startsLog) {
        foreach ($line in (Get-Content -LiteralPath $startsLog)) {
            $stamp = [datetime]::MinValue
            if ([datetime]::TryParse($line, [ref]$stamp) -and $stamp -gt $now.AddDays(-1)) {
                $recentStarts += $stamp
            }
        }
    }
    if ($recentStarts.Count -ge 3) {
        Write-ResumeLog 'Automatic restart paused: three attempts in 24 hours. Inspect the import error log.'
        exit 0
    }
    if ($recentStarts.Count -gt 0 -and ($now - ($recentStarts | Sort-Object -Descending | Select-Object -First 1)).TotalMinutes -lt 60) {
        exit 0
    }

    $latestError = Get-ChildItem -LiteralPath $logs -Filter 'full-ingest-*.err.log' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latestError) {
        $tail = (Get-Content -LiteralPath $latestError.FullName -Tail 100) -join "`n"
        if ($tail -match '(?i)user is disabled|user didn.t accept all required site policies|cost limits exceeded|permission denied|client error: forbidden|403 forbidden|invalid request|licen[cs]e.*not accepted') {
            Write-ResumeLog 'Automatic restart paused: CDS reported an access or invalid-request error. Inspect the import error log.'
            exit 0
        }
    }

    Push-Location -LiteralPath $projectRoot
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

        & docker compose -f compose.yaml up -d db 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Could not start PostGIS container.' }

        $databaseReady = $false
        for ($attempt = 1; $attempt -le 60; $attempt++) {
            & docker compose -f compose.yaml exec -T db pg_isready -U climate -d climate 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { $databaseReady = $true; break }
            Start-Sleep -Seconds 5
        }
        if (-not $databaseReady) { throw 'PostGIS unavailable after 5 minutes.' }

        $mode = (& docker compose -f compose.yaml exec -T db psql -U climate -d climate -Atc 'SELECT mode FROM dataset_info WHERE id=1' 2>$null | Out-String).Trim()
        if ($mode -eq 'era5_land') {
            Write-ResumeLog 'Import already complete; no action.'
            exit 0
        }
        if ($mode -ne 'building') { throw "Unexpected dataset mode '$mode'; refusing automatic import." }

        try {
            Invoke-WebRequest -Uri 'https://cds.climate.copernicus.eu/api/catalogue/v1/collections/derived-era5-land-daily-statistics' -Method Head -TimeoutSec 20 -UseBasicParsing | Out-Null
        } catch {
            throw 'CDS is unreachable; no import process was started.'
        }

        # start_full_ingest.ps1 checks the PID again and resumes from ingested_months.
        $result = & (Join-Path $PSScriptRoot 'start_full_ingest.ps1') 2>&1
        if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw ($result | Out-String) }
        Add-Content -LiteralPath $startsLog -Value $now.ToString('o')
        Write-ResumeLog (($result | Out-String).Trim())
    } finally {
        Pop-Location
    }
} catch {
    Write-ResumeLog "Automatic resume failed: $($_.Exception.Message)"
    exit 1
}
