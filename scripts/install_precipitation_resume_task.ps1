$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $PSScriptRoot 'resume_precipitation_after_logon.ps1'
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$powerShellExe = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$action = New-ScheduledTaskAction -Execute $powerShellExe `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$runner`"" `
    -WorkingDirectory $projectRoot
$logon = New-ScheduledTaskTrigger -AtLogOn -User $identity
$daily = New-ScheduledTaskTrigger -Daily -At ((Get-Date).Date.AddHours(8))
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 30) -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'GlobalClimatePrecipitationResume' -Action $action `
    -Trigger @($logon,$daily) -Principal $principal -Settings $settings `
    -Description 'Resume ERA5-Land precipitation ARCO import to PostGIS at logon and daily.' `
    -Force | Out-Null
Write-Output "Installed GlobalClimatePrecipitationResume for ${identity}: at logon and daily at 08:00."
