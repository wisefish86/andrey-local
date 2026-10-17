# Backup named configuration files to Yandex Disk, outside Git.
# Windows PowerShell 5.1 compatible. Files are never deleted from backups.
param([switch]$ShowReport)
$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$configuration = Join-Path $scriptDir 'backup.json'
$started = Get-Date
$results = New-Object System.Collections.Generic.List[object]
$copied = 0; $unchanged = 0; $failed = 0
$mutex = New-Object System.Threading.Mutex($false, 'Local\AndreyLocalSettingsBackup')
$locked = $false
$destination = $null
try {
    $locked = $mutex.WaitOne(0)
    if (-not $locked) { Write-Output 'Another backup is running.'; exit 0 }
    $config = Get-Content -LiteralPath $configuration -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($config.version -ne 1) { throw 'Unsupported backup.json version.' }
    $destination = [Environment]::ExpandEnvironmentVariables([string]$config.destination)
    if (-not [IO.Path]::IsPathRooted($destination)) { throw 'Destination must be an absolute path.' }
    $destination = [IO.Path]::GetFullPath($destination).TrimEnd('\')
    $driveRoot = [IO.Path]::GetPathRoot($destination)
    if (-not (Test-Path -LiteralPath $driveRoot -PathType Container)) { throw "Backup drive unavailable: $driveRoot" }
    # Never create a backup under the Git repository.
    $repoRoot = [IO.Path]::GetFullPath((Join-Path $scriptDir '..\..\..'))
    if ($destination.StartsWith($repoRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase) -or
        $destination.Equals($repoRoot.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Destination must be outside andrey-local.'
    }
    if (-not (Test-Path -LiteralPath $destination -PathType Container)) {
        New-Item -ItemType Directory -Path $destination -Force | Out-Null
    }
    foreach ($group in @($config.items)) {
        foreach ($entry in @($group.files)) {
            $source = [Environment]::ExpandEnvironmentVariables([string]$entry.source)
            $relative = ([string]$entry.target).Replace('/', '\')
            $name = [string]$group.name
            try {
                if (-not [IO.Path]::IsPathRooted($source)) { throw 'Source must be absolute.' }
                if ([IO.Path]::IsPathRooted($relative) -or $relative -match '(^|\\)\.\.(\\|$)' -or [string]::IsNullOrWhiteSpace($relative)) {
                    throw 'Invalid target path.'
                }
                $source = [IO.Path]::GetFullPath($source)
                $target = [IO.Path]::GetFullPath((Join-Path $destination $relative))
                if (-not $target.StartsWith($destination + '\', [StringComparison]::OrdinalIgnoreCase)) {
                    throw 'Target escapes backup directory.'
                }
                if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw 'Source file not found.' }
                if ($source.Equals($target, [StringComparison]::OrdinalIgnoreCase)) { throw 'Source equals target.' }
                $sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
                if ((Test-Path -LiteralPath $target -PathType Leaf) -and
                    (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -eq $sourceHash) {
                    $unchanged++
                    $results.Add([pscustomobject]@{Name=$name; File=$relative; Status='Unchanged'; Error='' })
                    continue
                }
                $parent = Split-Path -Parent $target
                if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
                    New-Item -ItemType Directory -Path $parent -Force | Out-Null
                }
                $temp = $target + '.backup-' + [guid]::NewGuid().ToString('N') + '.tmp'
                try {
                    Copy-Item -LiteralPath $source -Destination $temp -ErrorAction Stop
                    if ((Get-FileHash -LiteralPath $temp -Algorithm SHA256).Hash -ne $sourceHash) {
                        throw 'SHA256 verification failed.'
                    }
                    if (Test-Path -LiteralPath $target -PathType Leaf) {
                        # Existing copy is preserved until replacement is ready.
                        [IO.File]::Replace($temp, $target, $null)
                    } else {
                        [IO.File]::Move($temp, $target)
                    }
                } finally {
                    if (Test-Path -LiteralPath $temp -PathType Leaf) {
                        Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
                    }
                }
                $copied++
                $results.Add([pscustomobject]@{Name=$name; File=$relative; Status='Copied'; Error='' })
            } catch {
                $failed++
                $results.Add([pscustomobject]@{Name=$name; File=$relative; Status='ERROR'; Error=$_.Exception.Message })
            }
        }
    }
    $report = [pscustomobject]@{
        Started=$started.ToString('o'); Finished=(Get-Date).ToString('o')
        Destination=$destination; Copied=$copied; Unchanged=$unchanged; Failed=$failed
        Files=@($results.ToArray())
    }
    $reportFile = Join-Path $destination 'backup-last-report.json'
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportFile -Encoding UTF8
    $message = "Settings backup complete.`r`nCopied: $copied`r`nUnchanged: $unchanged`r`nErrors: $failed`r`nReport: $reportFile"
    Write-Output $message
    if ($ShowReport) {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show($message, 'Settings Backup') | Out-Null
    }
    if ($failed -gt 0) { exit 2 }
} catch {
    $message = 'Settings backup FAILED: ' + $_.Exception.Message
    Write-Error $message
    if ($ShowReport) {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show($message, 'Settings Backup Error', 'OK', 'Error') | Out-Null
    }
    exit 1
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
