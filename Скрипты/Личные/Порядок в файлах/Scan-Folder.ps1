# Read-only inventory, Windows PowerShell 5.1+
param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference = 'Stop'
try {
  $item = Get-Item -LiteralPath $Root -Force
  if (-not $item.PSIsContainer) { throw 'Folder required' }
  $rootPath = $item.FullName.TrimEnd([char]92)
  $out = Join-Path $PSScriptRoot ('Результаты\scan_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
  New-Item -ItemType Directory -Force -Path $out | Out-Null
  $exclude = @('.git','node_modules','.venv','venv','__pycache__','.idea','.vs','$RECYCLE.BIN','System Volume Information')
  $queue = New-Object System.Collections.Queue
  $queue.Enqueue($rootPath)
  $files = New-Object 'System.Collections.Generic.List[object]'
  $folders = New-Object 'System.Collections.Generic.List[object]'
  $errors = New-Object 'System.Collections.Generic.List[string]'
  $bytes = [long]0
  while ($queue.Count -gt 0) {
    $dir = [string]$queue.Dequeue()
    $relDir = if ($dir -eq $rootPath) { '.' } else { $dir.Substring($rootPath.Length).TrimStart([char]92) }
    $folders.Add([pscustomobject]@{RelativePath=$relDir;FullPath=$dir})
    try { $items = @(Get-ChildItem -LiteralPath $dir -Force -ErrorAction Stop) }
    catch { $errors.Add($dir + ' : ' + $_.Exception.Message); continue }
    foreach ($f in $items) {
      if (($f.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { continue }
      if ($f.PSIsContainer) {
        if ($exclude -notcontains $f.Name) { $queue.Enqueue($f.FullName) }
        continue
      }
      $bytes += [long]$f.Length
      $files.Add([pscustomobject]@{
        RelativePath=$f.FullName.Substring($rootPath.Length).TrimStart([char]92)
        FileName=$f.Name
        Extension=$f.Extension.ToLowerInvariant()
        SizeBytes=[long]$f.Length
        Created=$f.CreationTime.ToString('yyyy-MM-dd HH:mm:ss')
        Modified=$f.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')
        ParentFolder=$relDir
      })
    }
  }
  # BOM for compatibility with Excel on Windows.
  $files | Export-Csv -LiteralPath (Join-Path $out 'files.csv') -NoTypeInformation -Delimiter ';' -Encoding UTF8
  $folders | Export-Csv -LiteralPath (Join-Path $out 'folders.csv') -NoTypeInformation -Delimiter ';' -Encoding UTF8
  $lines = @('# Инвентаризация папки','','Корень: ' + $rootPath,'Дата: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'),'Файлов: ' + $files.Count,'Папок: ' + $folders.Count,'Общий размер: ' + [math]::Round($bytes / 1MB,2) + ' МБ','','## Расширения')
  foreach ($g in ($files | Group-Object Extension | Sort-Object Count -Descending | Select-Object -First 30)) { $lines += ('- ' + $g.Name + ': ' + $g.Count) }
  $lines += @('','## Примечания','Только чтение метаданных; файлы не изменяются. Содержимое и хеши не читаются.','Пропущены служебные папки и символьные ссылки.','Ошибок доступа: ' + $errors.Count)
  [IO.File]::WriteAllLines((Join-Path $out 'summary.md'),[string[]]$lines,(New-Object Text.UTF8Encoding($true)))
  if ($errors.Count) { [IO.File]::WriteAllLines((Join-Path $out 'errors.txt'),[string[]]$errors,(New-Object Text.UTF8Encoding($true))) }
  Write-Host ('Готово: файлов ' + $files.Count + ', папок ' + $folders.Count) -ForegroundColor Green
  Start-Process explorer.exe -ArgumentList ('"' + $out + '"')
} catch {
  Write-Host ('Ошибка: ' + $_.Exception.Message) -ForegroundColor Red
  exit 1
}
