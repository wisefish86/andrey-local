# Generates Windows shortcuts for launchable scripts in this repository.
# Only manages shortcuts marked with the description signature; never executes targets.
param([switch]$WhatIf)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$output = Join-Path $root 'Ярлыки'
$signature = 'Managed by AndreyLocal Shortcut Catalog v1'
$iconsRoot = Join-Path $root 'Ресурсы\Иконки'
$configPath = Join-Path $iconsRoot 'icon-map.json'
$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$iconDirectory = Join-Path $iconsRoot 'ICO'
if (-not $WhatIf -and -not (Test-Path -LiteralPath $output)) { New-Item -ItemType Directory -Path $output -Force | Out-Null }
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
    Where-Object { $_.Extension -in @('.bat', '.pyw') -and $_.FullName -notmatch '[\\/](Results|__pycache__|Archive|Архив|backup|бэкапы|бэкап|# Починить)[\\/]' -and $_.BaseName -notmatch '(?i)(backup|бэкап|install|установить|test|тест)' })
}
$items += @(Get-ChildItem -LiteralPath $root -File |
  Where-Object { $_.Extension -in @('.bat') -and $_.Name -notmatch '^(Установить|Авто)' })
$items = @($items | Where-Object { $_.FullName -ne $PSCommandPath } | Sort-Object FullName -Unique)

# User-facing names are verbs/actions, not internal implementation filenames.
$names = @{
  'Синхронизация.bat' = 'Синхронизировать файлы'
  'Запуск импорта.bat' = 'Импортировать в Notion'
  'Сканировать-папку.bat' = 'Сканировать папку'
  'Обновить ярлыки.bat' = 'Обновить каталог ярлыков'
  'Запустить замену раскладки.bat' = 'Включить замену ввода в Flow Launcher'
  'Открыть панель громкости.bat' = 'Открыть панель громкости для выступлений'
  'Создать файл-маркер ЯД.bat' = 'Создать маркеры ЯД'
  'Нормализация аудио видео.bat' = 'Нормализовать звук видео'
  '[заказы] 1. Начало работы.bat' = '01 — Начало работы с заказом (перетащить)'
  '[заказы] 2. Отправка макета на согласование.bat' = '02 — Отправить макет на согласование (перетащить)'
  '[заказы] 3. Подготовка к печати.bat' = '03 — Подготовить к печати (перетащить)'
  '[заказы] 4. Архивация и отправка на производство.bat' = '04 — Архивировать и отправить на производство (перетащить)'
  '[заказы] 5. Удаление лишнего.bat' = '05 — Удалить лишнее (перетащить)'
  '[скрипт] Удалить из названия файлов ֎ если они в подпапках.bat' = 'Удалить символ из имён файлов в подпапках'
  'run_csv_cleaner.bat' = 'Очистить CSV от лишних столбцов'
  'PDF-сборщик (перетяни файлы).bat' = 'Собрать PDF-превью (перетащить)'
  '[скрипт] Добавление водяного знака и конв. в WebP 75%.bat' = 'Добавить водяной знак и конвертировать в WebP'
  '[скрипт] Конвертировать в WebP 75%.bat' = 'Конвертировать в WebP 75%'
}
$errorsFound = @()
foreach ($file in $items) {
  # A companion BAT owns the user-facing shortcut for a GUI script.
  if ($file.Extension -eq '.pyw') {
    $neighbors = @(Get-ChildItem -LiteralPath $file.DirectoryName -File -Filter '*.bat' -ErrorAction SilentlyContinue |
      Where-Object { $_.BaseName -notmatch '(?i)(backup|бэкап|install|установить|test|тест)' })
    if ($neighbors.Count -gt 0) { continue }
  }
  $relativeDir = $file.DirectoryName.Substring($root.Length).TrimStart('\')
  $category = if ($relativeDir -eq '') { 'Системные' } else { $relativeDir }
  # A short, actionable catalog section for all five order workflows.
  # The .lnk target remains the original BAT beside its Python script,
  # so drag-and-drop passes the order path via the shortcut to %~1.
  if ($relativeDir -like 'Скрипты\Работа\Заказы\*') {
    $category = 'Работа\Заказы'
  }
  $folder = Join-Path $output $category
  $title = if ($names.ContainsKey($file.Name)) { $names[$file.Name] } else { $file.BaseName }
  $title = Make-SafeName $title
  # Windows Shell Link COM may replace nonstandard Unicode symbols with '?'.
  $title = $title.Replace([string][char]0x058E, ' - ').Replace('?', '_')
  $shortcutPath = Join-Path $folder ($title + '.lnk')
  # Convenience launcher in the root of the shortcut catalog; same underlying BAT.
  if ($file.Name -eq 'Обновить ярлыки.bat') {
    $folder = $output
    $shortcutPath = Join-Path $folder ($title + '.lnk')
  }
  if ($WhatIf) { Write-Host "Would update: $shortcutPath"; continue }
  if (-not (Test-Path -LiteralPath $folder)) { New-Item -ItemType Directory -Path $folder -Force | Out-Null }
  # Do not overwrite a shortcut that was created or customized by the user.
  if (Test-Path -LiteralPath $shortcutPath) {
    $previous = $wsh.CreateShortcut($shortcutPath)
    if ($previous.Description -ne $signature) { continue }
  }
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
    Write-Host ("Created/updated: " + $shortcutPath)
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
if (-not $WhatIf) { Write-Host "Shortcuts updated in: $output" }
