# Generates Windows shortcuts for launchable scripts in this repository.
# Preserves all existing shortcuts and detects renamed shortcuts by their target.
param([switch]$WhatIf)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$signature = 'Managed by AndreyLocal Shortcut Catalog v1'
$iconsRoot = Join-Path $root 'Ресурсы\Иконки'
$configPath = Join-Path $iconsRoot 'icon-map.json'
$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$iconDirectory = Join-Path $iconsRoot 'ICO'
$wsh = New-Object -ComObject WScript.Shell

function Make-SafeName([string]$name) {
  return ($name -replace '[<>:"/\\|?*]', '_').Trim().TrimEnd('.')
}
function Resolve-Icon([string]$stem, [string]$folderName) {
  $lookup = ($stem + ' ' + $folderName).ToLowerInvariant()
  $matched = 'script-default'
  # Explicit assignments take priority over broad keyword matching.
  $exact = $config.assignments.PSObject.Properties[$stem]
  if ($null -ne $exact) {
    $matched = [string]$exact.Value
  } else {
    foreach ($rule in $config.rules) {
      if ($lookup.Contains([string]$rule.contains)) { $matched = [string]$rule.icon; break }
    }
  }
  $candidate = Join-Path $iconDirectory ($matched + '.ico')
  if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
  $fallback = Join-Path $iconDirectory 'script-default.ico'
  if (Test-Path -LiteralPath $fallback -PathType Leaf) { return $fallback }
  # Never substitute the folder icon: skip assignment until ICO assets arrive.
  return $null
}

# Only discover files in known locations; never scan inbox/reference/archive or generated output.
$items = @()
$scriptDir = Join-Path $root 'Скрипты'
if (Test-Path -LiteralPath $scriptDir) {
  $items += @(Get-ChildItem -LiteralPath $scriptDir -File -Recurse |
    Where-Object { $_.Extension -in @('.bat', '.pyw', '.ahk') -and $_.FullName -notmatch '[\\/](Results|__pycache__|Archive|Архив|backup|бэкапы|бэкап|# Починить)[\\/]' })
}
$items += @(Get-ChildItem -LiteralPath $root -File |
  Where-Object { $_.Extension -in @('.bat') })
$items = @($items | Where-Object { $_.FullName -ne $PSCommandPath } | Sort-Object FullName -Unique)

$errorsFound = @()
foreach ($file in $items) {
  # A companion BAT owns the user-facing shortcut for a GUI script.
  if ($file.Extension -eq '.pyw') {
    $neighbors = @(Get-ChildItem -LiteralPath $file.DirectoryName -File -Filter '*.bat' -ErrorAction SilentlyContinue |
      Where-Object { $true })
    if ($neighbors.Count -gt 0) { continue }
  }
  # One shortcut next to each launcher. Never manage the user's separate Ярлыки folder.
  $relativeDir = $file.DirectoryName.Substring($root.Length).TrimStart('\')
  $category = if ($relativeDir -eq '') { 'Системные' } else { $relativeDir }
  $folder = $file.DirectoryName
  $title = Make-SafeName $file.BaseName
  $title = $title.Replace([string][char]0x058E, ' - ').Replace('?', '_')
  $shortcutPath = Join-Path $folder ($title + ' - ярлык.lnk')
  # Preserve a shortcut even when the user renamed it. Compare its destination,
  # not just its filename; never edit or delete existing shortcuts.
  if (Test-Path -LiteralPath $shortcutPath) { continue }
  $alreadyLinked = $false
  foreach ($existingFile in @(Get-ChildItem -LiteralPath $folder -File -Filter '*.lnk' -ErrorAction SilentlyContinue)) {
    try {
      $existing = $wsh.CreateShortcut($existingFile.FullName)
      $existingTarget = [string]$existing.TargetPath
      if ([string]::Equals($existingTarget, $file.FullName, [StringComparison]::OrdinalIgnoreCase)) {
        $alreadyLinked = $true
        break
      }
      # Some BAT paths require cmd.exe as the shortcut executable.
      if ($file.Extension -eq '.bat' -and
          [string]::Equals($existingTarget, $env:ComSpec, [StringComparison]::OrdinalIgnoreCase) -and
          ([string]$existing.Arguments).Contains('"' + $file.FullName + '"')) {
        $alreadyLinked = $true
        break
      }
    } catch {
      Write-Warning ("Cannot inspect shortcut (preserved): " + $existingFile.FullName)
    }
  }
  if ($alreadyLinked) { continue }
  if ($WhatIf) { Write-Host "Would create: $shortcutPath"; continue }
  $stage = 'CreateShortcut'
  try {
    $shortcut = $wsh.CreateShortcut($shortcutPath)
    $stage = 'Description'
    $shortcut.Description = $signature
    $stage = 'WorkingDirectory'
    $shortcut.WorkingDirectory = $file.DirectoryName
    $stage = 'Arguments'
    $shortcut.Arguments = ''
    try {
      $stage = 'TargetPath'
      $shortcut.TargetPath = $file.FullName
    } catch {
      # WSH rejects certain BAT paths (ArgumentException 0x80070057).
      # cmd.exe is a stable executable target; Explorer appends drag-and-drop
      # paths to the shortcut command line, preserving the file arguments.
      if ($file.Extension -ne '.bat') { throw }
      $stage = 'TargetPath fallback cmd'
      $shortcut.TargetPath = $env:ComSpec
      $shortcut.Arguments = '/d /s /c ""' + $file.FullName + '" "'
      Write-Warning ("Using cmd.exe for shortcut: " + $file.FullName)
    }
    $stage = 'Resolve-Icon'
    $icon = Resolve-Icon $file.BaseName $category
    $stage = 'IconLocation'
    if ($icon) { $shortcut.IconLocation = $icon }
    elseif ($file.Extension -eq '.bat') { $shortcut.IconLocation = $env:ComSpec + ',0' }
    else { $shortcut.IconLocation = $file.FullName + ',0' }
    $stage = 'Save'
    $shortcut.Save()
    Write-Host ("Created: " + $shortcutPath)
  } catch {
    $errorsFound += [PSCustomObject]@{ File = $file.FullName; Step = $stage; Error = $_.Exception.Message }
    Write-Warning ("SHORTCUT ERROR [" + $stage + "]: " + $file.FullName + " -> " + $_.Exception.Message)
  }
}
# Never delete any existing shortcuts. Old and custom links are maintained by the user.
if ($errorsFound.Count -gt 0) {
  Write-Host ""
  Write-Host ("FAILED SHORTCUTS: " + $errorsFound.Count) -ForegroundColor Red
  foreach ($problem in $errorsFound) {
    Write-Host ("File: " + $problem.File) -ForegroundColor Yellow
    Write-Host ("Step: " + $problem.Step + " | " + $problem.Error) -ForegroundColor Red
  }
  Write-Host "Other shortcuts were created; existing shortcuts were not deleted." -ForegroundColor Yellow
  exit 1
}
if (-not $WhatIf) { Write-Host 'Shortcuts created beside launchers. Existing shortcuts were preserved.' }
