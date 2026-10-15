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
  'run_csv_cleaner.bat' = 'Очистить CSV от лишних столбцов'
  'PDF-сборщик (перетяни файлы).bat' = 'Собрать PDF-превью (перетащить)'
  '[скрипт] Добавление водяного знака и конв. в WebP 75%.bat' = 'Добавить водяной знак и конвертировать в WebP'
  '[скрипт] Конвертировать в WebP 75%.bat' = 'Конвертировать в WebP 75%'
}
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
  if ($relativeDir -like 'Скрипты\\Работа\\Заказы\\*') {
    $category = 'Работа\\Заказы'
  }
  $folder = Join-Path $output $category
  $title = if ($names.ContainsKey($file.Name)) { $names[$file.Name] } else { $file.BaseName }
  $title = Make-SafeName $title
  $shortcutPath = Join-Path $folder ($title + '.lnk')
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
  $shortcut.TargetPath = $file.FullName
  $shortcut.Arguments = ''
  $icon = Resolve-Icon $file.BaseName $category
  if ($icon) { $shortcut.IconLocation = $icon }
  else {
    $shortcut.IconLocation = $file.FullName + ',0'
  }
  $shortcut.Save()
}
# Never delete any existing shortcuts. Old and custom links are maintained by the user.
if (-not $WhatIf) { Write-Host "Shortcuts updated in: $output" }
