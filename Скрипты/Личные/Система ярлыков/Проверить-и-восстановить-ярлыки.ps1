# Diagnose and optionally repair shortcuts created by AndreyLocal.
# Windows PowerShell 5.1; default mode is read-only.
[CmdletBinding()]
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$signature = 'Managed by AndreyLocal Shortcut Catalog v1'
$wsh = New-Object -ComObject WScript.Shell
$scriptRoot = Join-Path $root 'Скрипты'
if (-not (Test-Path -LiteralPath $scriptRoot -PathType Container)) { throw "Scripts directory is missing: $scriptRoot" }
$excludePattern = '[\\/](Results|__pycache__|Archive|Архив|backup|бэкапы|бэкап|# Починить)[\\/]'
$launchers = @(
  Get-ChildItem -LiteralPath $scriptRoot -Recurse -File |
    Where-Object { $_.Extension -in @('.bat', '.pyw', '.ahk') -and $_.FullName -notmatch $excludePattern }
)
$launchers += @(Get-ChildItem -LiteralPath $root -File | Where-Object { $_.Extension -eq '.bat' })
$launchers = @($launchers | Sort-Object FullName -Unique | Where-Object {
  if ($_.Extension -ne '.pyw') { return $true }
  @(Get-ChildItem -LiteralPath $_.DirectoryName -File -Filter '*.bat' -ErrorAction SilentlyContinue).Count -eq 0
})
$allLinks = @(Get-ChildItem -LiteralPath $scriptRoot -Recurse -File -Filter '*.lnk' |
  Where-Object { $_.FullName -notmatch $excludePattern })
$allLinks += @(Get-ChildItem -LiteralPath $root -File -Filter '*.lnk')
$allLinks = @($allLinks | Sort-Object FullName -Unique)
$rows = @()
foreach ($linkFile in $allLinks) {
  try {
    $link = $wsh.CreateShortcut($linkFile.FullName)
    if ([string]$link.Description -ne $signature) { continue }
    $folder = $linkFile.DirectoryName
    $candidates = @($launchers | Where-Object { $_.DirectoryName -eq $folder })
    $target = [string]$link.TargetPath
    $args = [string]$link.Arguments
    $matches = @($candidates | Where-Object {
      [string]::Equals($_.FullName, $target, [StringComparison]::OrdinalIgnoreCase) -or
      ($_.Extension -eq '.bat' -and
       [string]::Equals($target, $env:ComSpec, [StringComparison]::OrdinalIgnoreCase) -and
       $args.Contains('"' + $_.FullName + '"'))
    })
    $reason = ''
    if ($matches.Count -eq 0) {
      # Recovery is permitted only for an exact generator filename, never for a guess.
      $matches = @($candidates | Where-Object {
        $name = ($_.BaseName -replace '[<>:"/\\|?*]', '_').Trim().TrimEnd('.')
        $name = $name.Replace([string][char]0x058E, ' - ').Replace('?', '_')
        [string]::Equals(($name + ' - ярлык.lnk'), $linkFile.Name, [StringComparison]::OrdinalIgnoreCase)
      })
      $reason = 'target mismatch; matched exact generated filename'
    }
    if ($matches.Count -ne 1) {
      $rows += [pscustomobject]@{ Status='REVIEW'; Link=$linkFile.FullName; Launcher=''; Reason='No unique same-folder launcher match' }
      continue
    }
    $source = $matches[0]
    $validDirect = [string]::Equals($target, $source.FullName, [StringComparison]::OrdinalIgnoreCase)
    $validCmd = $source.Extension -eq '.bat' -and
      [string]::Equals($target, $env:ComSpec, [StringComparison]::OrdinalIgnoreCase) -and
      $args.Contains('"' + $source.FullName + '"')
    $status = if ($validDirect -or $validCmd) { 'OK' } else { 'REPAIR' }
    $rows += [pscustomobject]@{ Status=$status; Link=$linkFile.FullName; Launcher=$source.FullName; Reason=$reason }
  } catch {
    $rows += [pscustomobject]@{ Status='REVIEW'; Link=$linkFile.FullName; Launcher=''; Reason=$_.Exception.Message }
  }
}
$rows | Format-Table Status, Link, Reason -Wrap -AutoSize | Out-Host
$repairs = @($rows | Where-Object { $_.Status -eq 'REPAIR' })
Write-Host ("Managed shortcuts: {0}; repair: {1}; review: {2}" -f $rows.Count, $repairs.Count, @($rows | Where-Object Status -eq 'REVIEW').Count)
if (-not $Apply) { Write-Host 'Preview only. Use -Apply to repair the listed shortcuts.'; return }
if ($repairs.Count -eq 0) { Write-Host 'Nothing to repair.'; return }
$backupFolder = Join-Path $PSScriptRoot ('Backups\ShortcutRepair-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $backupFolder -Force | Out-Null
$log = @()
foreach ($item in $repairs) {
  try {
    # Recheck immediately before the write; never overwrite manually retagged links.
    $link = $wsh.CreateShortcut($item.Link)
    if ([string]$link.Description -ne $signature) { throw 'Management signature changed' }
    if (-not (Test-Path -LiteralPath $item.Launcher -PathType Leaf)) { throw 'Launcher no longer exists' }
    $relative = $item.Link.Substring($root.Length).TrimStart('\')
    $backup = Join-Path $backupFolder $relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $backup) -Force | Out-Null
    Copy-Item -LiteralPath $item.Link -Destination $backup -ErrorAction Stop
    # Preserve custom arguments and icons. Only repair the broken destination and workdir.
    $source = Get-Item -LiteralPath $item.Launcher
    if ($source.Extension -eq '.bat') {
      $link.TargetPath = $env:ComSpec
      $link.Arguments = '/d /s /c ""' + $source.FullName + '" "'
    } else {
      $link.TargetPath = $source.FullName
      $link.Arguments = ''
    }
    $link.WorkingDirectory = $source.DirectoryName
    $link.Save()
    $log += [pscustomobject]@{ Link=$item.Link; Backup=$backup; Status='Repaired' }
    Write-Host ('Repaired: ' + $item.Link) -ForegroundColor Green
  } catch {
    $log += [pscustomobject]@{ Link=$item.Link; Backup=''; Status=('Error: ' + $_.Exception.Message) }
    Write-Warning ('Failed: ' + $item.Link + ' - ' + $_.Exception.Message)
  }
}
$log | Export-Csv -LiteralPath (Join-Path $backupFolder 'repair-log.csv') -NoTypeInformation -Encoding UTF8
Write-Host ('Backup and log: ' + $backupFolder)
if (@($log | Where-Object { $_.Status -ne 'Repaired' }).Count -gt 0) { exit 1 }
