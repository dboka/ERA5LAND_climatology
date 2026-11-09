$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $PSScriptRoot 'run_daily_update.ps1'
if (-not (Test-Path -LiteralPath $runner)) { throw 'Daily update runner is missing.' }

$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$powerShellExe = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$action = New-ScheduledTaskAction -Execute $powerShellExe `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$runner`"" `
    -WorkingDirectory $projectRoot
$daily = New-ScheduledTaskTrigger -Daily -At ((Get-Date).Date.AddHours(8))
$logon = New-ScheduledTaskTrigger -AtLogOn -User $identity
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 30) -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'GlobalClimateDailyUpdate' -Action $action `
    -Trigger @($daily,$logon) -Principal $principal -Settings $settings `
    -Description 'Append ERA5-Land ARCO UTC days to PostGIS and rebuild local GitHub Pages snapshot.' `
    -Force | Out-Null
Write-Output "Installed GlobalClimateDailyUpdate for ${identity}: daily at 08:00 local time and at logon."
