# Run once from local andrey-local after fetching these files.
$ErrorActionPreference = 'Stop'
$taskName = 'AndreyLocal Inbox Auto Sync'
$scriptPath = Join-Path $PSScriptRoot 'Автосинхронизация.ps1'
if (-not (Test-Path -LiteralPath $scriptPath)) { throw "Script missing: $scriptPath" }
$arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $scriptPath + '"'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 2) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "Enabled: $taskName (every 2 minutes when signed in)." -ForegroundColor Green
Write-Host 'To disable: Unregister-ScheduledTask -TaskName "AndreyLocal Inbox Auto Sync" -Confirm:$false'
