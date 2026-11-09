param(
    [Parameter(Mandatory = $true)][int]$ProcessId,
    [Parameter(Mandatory = $true)][string]$Month,
    [Parameter(Mandatory = $true)][string]$ProgressLog
)

$ErrorActionPreference = 'Stop'
$statusLog = Join-Path (Split-Path -Parent $ProgressLog) "stop-after-$Month.log"
$needle = "Ingested era5_land_t2m_daily_$Month.partial:"

while ($true) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    if (-not $process -or $process.Name -notmatch '^python') {
        Add-Content -LiteralPath $statusLog -Value "$(Get-Date -Format o) Import process already stopped."
        exit 0
    }

    if (Test-Path -LiteralPath $ProgressLog) {
        $lastLines = Get-Content -LiteralPath $ProgressLog -Tail 4
        if ($lastLines | Where-Object { $_.StartsWith($needle) }) {
            # This line is printed only after the month's database transaction commits.
            Stop-Process -Id $ProcessId -Force
            Add-Content -LiteralPath $statusLog -Value "$(Get-Date -Format o) Stopped PID $ProcessId after checkpoint $Month."
            exit 0
        }
    }
    Start-Sleep -Milliseconds 250
}
