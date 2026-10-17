# Registers/updates the backup task using schedule from backup.json.
# daily: time HH:mm; every_hours: intervalHours (1..24), with start at the supplied time.
$ErrorActionPreference = 'Stop'
$configFile = Join-Path $PSScriptRoot 'backup.json'
$backupScript = Join-Path $PSScriptRoot 'Backup.ps1'
if (-not (Test-Path -LiteralPath $backupScript -PathType Leaf)) { throw 'Backup.ps1 not found.' }
$config = Get-Content -LiteralPath $configFile -Raw -Encoding UTF8 | ConvertFrom-Json
if ($null -eq $config.schedule) { throw 'schedule section is missing in backup.json.' }
$mode = [string]$config.schedule.mode
$at = [string]$config.schedule.time
if ($at -notmatch '^(?:[01][0-9]|2[0-3]):[0-5][0-9]$') { throw 'schedule.time must be HH:mm, e.g. 21:00.' }
$start = [datetime]::ParseExact($at, 'HH:mm', [Globalization.CultureInfo]::InvariantCulture)
if ($mode -eq 'daily') {
    $trigger = New-ScheduledTaskTrigger -Daily -At $start
    $description = "Daily settings backup at $at"
} elseif ($mode -eq 'every_hours') {
    $n = 0
    if (-not [int]::TryParse([string]$config.schedule.intervalHours, [ref]$n) -or $n -lt 1 -or $n -gt 24) {
        throw 'schedule.intervalHours must be an integer from 1 to 24.'
    }
    # Long repetition window. Re-run installer if interval/config changes.
    $trigger = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Hours $n) -RepetitionDuration (New-TimeSpan -Days 3650)
    $description = "Settings backup every $n hours, starting $at"
} else {
    throw "Unknown schedule.mode: $mode (use daily or every_hours)."
}
$taskName = 'Andrey Local - Settings Backup'
$exe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$action = New-ScheduledTaskAction -Execute $exe -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $backupScript + '"')
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description $description -Force | Out-Null
Write-Host "Installed: $taskName ($description)"
Write-Host 'Schedule changes require running the installer BAT again.'
