# Run once from local andrey-local after fetching these files.
$ErrorActionPreference = 'Stop'
$taskName = 'AndreyLocal Inbox Auto Sync'
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$scriptPath = Join-Path $repoRoot 'Автосинхронизация.ps1'
if (-not (Test-Path -LiteralPath $scriptPath)) { throw "Script missing: $scriptPath" }
# wscript.exe is a GUI host: the PowerShell console stays fully hidden.
$launcherPath = Join-Path $repoRoot 'Тихий запуск синхронизации.vbs'
if (-not (Test-Path -LiteralPath $launcherPath)) { throw "Launcher missing: $launcherPath" }
$arguments = '"' + $launcherPath + '" "' + $scriptPath + '"'
$action = New-ScheduledTaskAction -Execute (Join-Path $env:SystemRoot 'System32\wscript.exe') -Argument $arguments -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 2) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "Enabled: $taskName (every 2 minutes when signed in)." -ForegroundColor Green
Write-Host 'To disable: Unregister-ScheduledTask -TaskName "AndreyLocal Inbox Auto Sync" -Confirm:$false'
