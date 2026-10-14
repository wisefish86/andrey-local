# Read-only folder inventory for Windows PowerShell 5.1+
# ASCII-only source avoids Windows PowerShell 5.1 UTF-8-without-BOM issues.
param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference = 'Stop'
try {
  $rootItem = Get-Item -LiteralPath $Root -Force -ErrorAction Stop
  if (-not $rootItem.PSIsContainer) { throw 'Please drag a folder, not a file.' }
  $rootPath = $rootItem.FullName.TrimEnd([char]92)
  $rootName = $rootItem.Name
  if ([string]::IsNullOrWhiteSpace($rootName)) { $rootName = 'Drive' }
  $safeName = [regex]::Replace($rootName, '[^\p{L}\p{N}._ -]', '_').Trim(' ','.')
  if (-not $safeName) { $safeName = 'Folder' }
  if ($safeName.Length -gt 65) { $safeName = $safeName.Substring(0,65) }
  $outDir = Join-Path $PSScriptRoot 'Results'
  New-Item -ItemType Directory -Force -Path $outDir | Out-Null
  $outFile = Join-Path $outDir ($safeName + '_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.json')

  $exclude = @('.git','node_modules','.venv','venv','__pycache__','.idea','.vs','$RECYCLE.BIN','System Volume Information')
  $queue = New-Object System.Collections.Queue
  $queue.Enqueue($rootPath)
  $entries = New-Object 'System.Collections.Generic.List[object]'
  $scanErrors = New-Object 'System.Collections.Generic.List[string]'
  $folderCount = 0
  $fileCount = 0
  $totalBytes = [long]0
  while ($queue.Count -gt 0) {
    $dir = [string]$queue.Dequeue()
    $relativeDir = if ($dir -eq $rootPath) { '.' } else { $dir.Substring($rootPath.Length).TrimStart([char]92) }
    $folderCount++
    $entries.Add([pscustomobject]@{Type='folder';Path=$relativeDir})
    try { $children = @(Get-ChildItem -LiteralPath $dir -Force -ErrorAction Stop) }
    catch { $scanErrors.Add($dir + ': ' + $_.Exception.Message); continue }
    foreach ($entry in $children) {
      if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { continue }
      if ($entry.PSIsContainer) {
        if ($exclude -notcontains $entry.Name) { $queue.Enqueue($entry.FullName) }
      } else {
        $fileCount++
        $totalBytes += [long]$entry.Length
        $entries.Add([pscustomobject]@{
          Type='file'
          Path=$entry.FullName.Substring($rootPath.Length).TrimStart([char]92)
          Bytes=[long]$entry.Length
          Created=$entry.CreationTime.ToString('yyyy-MM-ddTHH:mm:ss')
          Modified=$entry.LastWriteTime.ToString('yyyy-MM-ddTHH:mm:ss')
        })
      }
    }
  }
  $report = [ordered]@{
    SchemaVersion=2
    ScannedFolder=$rootName
    RootPath=$rootPath
    ScannedAt=(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss')
    FileCount=$fileCount
    FolderCount=$folderCount
    TotalBytes=$totalBytes
    Entries=@($entries.ToArray())
    Errors=@($scanErrors.ToArray())
  }
  $json = ConvertTo-Json -InputObject $report -Depth 6
  [IO.File]::WriteAllText($outFile,$json,(New-Object System.Text.UTF8Encoding($true)))
  Write-Host ('Done. Files: ' + $fileCount + '; folders: ' + $folderCount) -ForegroundColor Green
  Write-Host ('Report: ' + $outFile)
  Start-Process explorer.exe -ArgumentList ('"' + $outDir + '"')
} catch {
  Write-Host ('Error: ' + $_.Exception.Message) -ForegroundColor Red
  exit 1
}
