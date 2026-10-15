# Generates Windows shortcuts for launchable scripts in this repository.
# Only manages shortcuts marked with the description signature; never executes targets.
param([switch]$WhatIf)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$output = Join-Path $root 'Ярлыки'
$signature = 'Managed by AndreyLocal Shortcut Catalog v1'
$known = @{}
$iconsRoot = Join-Path $root 'Ресурсы\Иконки'
$shellIcons = Join-Path $env:SystemRoot 'System32\shell32.dll'
$wsh = New-Object -ComObject WScript.Shell

function Make-SafeName([string]$name) {
  return ($name -replace '[<>:"/\\|?*]', '_').Trim().TrimEnd('.')
}
function Resolve-Icon([string]$stem) {
  $ico = Join-Path $iconsRoot ($stem + '.ico')
  if (Test-Path -LiteralPath $ico -PathType Leaf) { return $ico }
  return ($shellIcons + ',3')
}

# Only discover files in known locations; never scan inbox/reference/archive or generated output.
$items = @()
$scriptDir = Join-Path $root 'Скрипты'
if (Test-Path -LiteralPath $scriptDir) {
  $items += @(Get-ChildItem -LiteralPath $scriptDir -File -Recurse |
    Where-Object { $_.Extension -in @('.bat', '.cmd', '.pyw', '.ps1') -and $_.FullName -notmatch '[\\/](Results|__pycache__|Archive|Архив)[\\/]' })
}
$items += @(Get-ChildItem -LiteralPath $root -File |
  Where-Object { $_.Extension -in @('.bat', '.cmd') -and $_.Name -notmatch '^(Установить|Авто)' })
$items = @($items | Where-Object { $_.FullName -ne $PSCommandPath } | Sort-Object FullName -Unique)

foreach ($file in $items) {
  # A BAT/CMD wrapper takes precedence over the corresponding PowerShell script.
  if ($file.Extension -eq '.ps1') {
    if ((Test-Path -LiteralPath (Join-Path $file.DirectoryName ($file.BaseName + '.bat'))) -or
        (Test-Path -LiteralPath (Join-Path $file.DirectoryName ($file.BaseName + '.cmd')))) { continue }
  }
  $relativeDir = $file.DirectoryName.Substring($root.Length).TrimStart('\')
  $category = if ($relativeDir -eq '') { 'Системные' } else { $relativeDir }
  $folder = Join-Path $output $category
  $title = Make-SafeName $file.BaseName
  $shortcutPath = Join-Path $folder ($title + '.lnk')
  $known[$shortcutPath.ToLowerInvariant()] = $true
  if ($WhatIf) { Write-Host "Would update: $shortcutPath"; continue }
  if (-not (Test-Path -LiteralPath $folder)) { New-Item -ItemType Directory -Path $folder -Force | Out-Null }
  # Do not overwrite a shortcut that was created or customized by the user.
  if (Test-Path -LiteralPath $shortcutPath) {
    $previous = $wsh.CreateShortcut($shortcutPath)
    if ($previous.Description -ne $signature) { continue }
  }
  $shortcut = $wsh.CreateShortcut($shortcutPath)
  $shortcut.Description = $signature
  $shortcut.WorkingDirectory = $file.DirectoryName
  if ($file.Extension -eq '.ps1') {
    $shortcut.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $file.FullName + '"'
  } else {
    $shortcut.TargetPath = $file.FullName
    $shortcut.Arguments = ''
  }
  $shortcut.IconLocation = Resolve-Icon $file.BaseName
  $shortcut.Save()
}
# Intentionally never delete stale/custom shortcuts. Review obsolete ones manually.
if (-not $WhatIf) { Write-Host "Shortcuts updated in: $output" }
