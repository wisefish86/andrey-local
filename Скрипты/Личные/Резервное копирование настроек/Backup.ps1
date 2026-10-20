# Backup named configuration files to Yandex Disk, outside Git.
# Windows PowerShell 5.1 compatible. Files are never deleted from backups.
param([switch]$ShowReport)
$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$configuration = Join-Path $scriptDir 'backup.json'
$started = Get-Date
$results = New-Object System.Collections.Generic.List[object]
$copied = 0; $unchanged = 0; $failed = 0; $deferred = 0
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
        $entries = New-Object System.Collections.Generic.List[object]
        foreach ($explicit in @($group.files)) {
            if ($null -ne $explicit) { $entries.Add($explicit) }
        }
        if ($null -ne $group.discovery) {
            $d = $group.discovery
            $name = [string]$group.name
            $runningNames = @($d.skipWhenProcessesRunning | Where-Object { $_ })
            $isRunning = $false
            foreach ($processName in $runningNames) {
                if (Get-Process -Name ([string]$processName) -ErrorAction SilentlyContinue) {
                    $isRunning = $true
                    break
                }
            }
            if ($isRunning) {
                $deferred++
                $results.Add([pscustomobject]@{Name=$name; File=([string]$d.pattern); Status='Deferred'; Error='Application is running; wait until it closes.'})
            } else {
                try {
                    $root = [Environment]::ExpandEnvironmentVariables([string]$d.root)
                    if (-not [IO.Path]::IsPathRooted($root) -or -not (Test-Path -LiteralPath $root -PathType Container)) {
                        throw "Discovery root not found: $root"
                    }
                    $root = [IO.Path]::GetFullPath($root).TrimEnd('\')
                    $prefix = ([string]$d.targetPrefix).Replace('/', '\').TrimEnd('\')
                    if ([string]::IsNullOrWhiteSpace($prefix)) { throw 'Discovery targetPrefix is empty.' }
                    $pattern = [string]$d.pattern
                    if ([string]::IsNullOrWhiteSpace($pattern)) { throw 'Discovery pattern is empty.' }
                    $patterns = @($d.patterns | Where-Object { $_ })
                    if ($patterns.Count -eq 0) { $patterns = @($pattern) }
                    $pathRegex = [string]$d.includePathRegex
                    $found = @(Get-ChildItem -LiteralPath $root -File -Recurse -ErrorAction Stop | Where-Object {
                        $item = $_
                        $accepted = $false
                        foreach ($glob in $patterns) { if ($item.Name -like [string]$glob) { $accepted = $true; break } }
                        if (-not $accepted) { return $false }
                        if (-not [string]::IsNullOrWhiteSpace($pathRegex)) {
                            $rel = $item.FullName.Substring($root.Length).TrimStart('\')
                            return ($rel -match $pathRegex)
                        }
                        return $true
                    })
                    if ($found.Count -eq 0) { throw "No matching files found beneath: $root" }
                    foreach ($foundFile in $found) {
                        $pathPart = $foundFile.FullName.Substring($root.Length).TrimStart('\')
                        $entries.Add([pscustomobject]@{source=$foundFile.FullName; target=($prefix + '\' + $pathPart)})
                    }
                } catch {
                    $failed++
                    $results.Add([pscustomobject]@{Name=$name; File='*.gms'; Status='ERROR'; Error=$_.Exception.Message})
                }
            }
        }
        foreach ($entry in $entries) {
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
                        # Keep the previous version until the new file is safely installed.
                        # File.Replace requires a valid backup path on some .NET runtimes.
                        $previous = $target + '.previous-' + [guid]::NewGuid().ToString('N') + '.bak'
                        [IO.File]::Replace($temp, $target, $previous)
                        if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $sourceHash) {
                            # Restore the previous copy if the replacement is not valid.
                            Copy-Item -LiteralPath $previous -Destination $target -Force -ErrorAction Stop
                            throw 'SHA256 verification failed after replacement.'
                        }
                        Remove-Item -LiteralPath $previous -Force -ErrorAction Stop
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
        Destination=$destination; Copied=$copied; Unchanged=$unchanged; Deferred=$deferred; Failed=$failed
        Files=@($results.ToArray())
    }
    $reportFile = Join-Path $destination 'backup-last-report.json'
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportFile -Encoding UTF8
    $message = "Settings backup complete.`r`nCopied: $copied`r`nUnchanged: $unchanged`r`nDeferred: $deferred`r`nErrors: $failed`r`nReport: $reportFile"
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
