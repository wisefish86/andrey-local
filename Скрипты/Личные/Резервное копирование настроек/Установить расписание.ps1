# Run once on the Windows computer to install daily backup at 21:00.
# Requires an interactive Windows session; no administrator rights when registering for current user.
param([string]$At = '21:00')
$ErrorActionPreference = 'Stop'
if ($At -notmatch '^(?:[01][0-9]|2[0-3]):[0-5][0-9]$') { throw 'Use 24-hour HH:mm, for example 21:00.' }
$backupScript = Join-Path $PSScriptRoot 'Backup.ps1'
if (-not (Test-Path -LiteralPath $backupScript -PathType Leaf)) { throw 'Backup.ps1 not found.' }
$taskName = 'Andrey Local - Settings Backup'
$action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $backupScript + '"')
$trigger = New-ScheduledTaskTrigger -Daily -At ([datetime]::ParseExact($At, 'HH:mm', [Globalization.CultureInfo]::InvariantCulture))
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description 'Backup Flow Launcher and Espanso settings to Yandex Disk.' -Force | Out-Null
Write-Host "Installed task: $taskName (daily at $At)."
Write-Host "Test the backup manually with Backup.ps1 -ShowReport."
