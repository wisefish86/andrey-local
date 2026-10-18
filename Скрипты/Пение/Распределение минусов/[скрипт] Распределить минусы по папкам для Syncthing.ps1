﻿# Перенос папок из плейлиста MusicBee
# Универсальная версия

# === НАСТРОЙКИ ===
$processName = "MusicBee" # Имя процесса MusicBee

# Список задач (название папки, имя плейлиста, целевая папка)
$tasks = @(
    @{
        Name = "Основной репертуар"
        PlaylistPath = "C:\Users\Andrey\AppData\Roaming\MusicBee\Saved Settings\Layouts\Минусы (задачи)\Автоматизированные\Перенести в папку 'Основной репертуар'.m3u"
        TargetPath = "D:\YandexDisk\Проекты\Пение\Минусы\1. Основной репертуар"
    },
    @{
        Name = "В разработке"
        PlaylistPath = "C:\Users\Andrey\AppData\Roaming\MusicBee\Saved Settings\Layouts\Минусы (задачи)\Автоматизированные\Перенести в папку '- В разработке'.m3u"
        TargetPath = "D:\YandexDisk\Проекты\Пение\Минусы\1. Основной репертуар\- В разработке"
    },
    @{
        Name = "Повторить"
        PlaylistPath = "C:\Users\Andrey\AppData\Roaming\MusicBee\Saved Settings\Layouts\Минусы (задачи)\Автоматизированные\Перенести в папку '- Повторить'.m3u"
        TargetPath = "D:\YandexDisk\Проекты\Пение\Минусы\1. Основной репертуар\- Повторить"
    },
    @{
        Name = "Запасные"
        PlaylistPath = "C:\Users\Andrey\AppData\Roaming\MusicBee\Saved Settings\Layouts\Минусы (задачи)\Автоматизированные\Перенести в папку '# Запас'.m3u"
        TargetPath = "D:\YandexDisk\Проекты\Пение\Минусы\1. Основной репертуар\# Запасные"
    },
    @{
        Name = "Тестирую"
        PlaylistPath = "C:\Users\Andrey\AppData\Roaming\MusicBee\Saved Settings\Layouts\Минусы (задачи)\Автоматизированные\Перенести в папку '- Тестирую'.m3u"
        TargetPath = "D:\YandexDisk\Проекты\Пение\Минусы\1. Основной репертуар\- Тестирую"
    }
)

# === ЛОГ В ПАПКЕ СКРИПТА ===
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptBaseName = [System.IO.Path]::GetFileNameWithoutExtension($MyInvocation.MyCommand.Name)
$logFile = Join-Path $scriptDir "$scriptBaseName.log"

# Перезаписываем старый лог при запуске
if (Test-Path -LiteralPath $logFile) {
    Remove-Item -LiteralPath $logFile -Force
}

# Функция для записи в лог и на экран
function Write-Log {
    param(
        [string]$Message,
        [string]$Color = "Gray"
    )
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] $Message"
    Write-Host $logMessage -ForegroundColor $Color
    
    if (-not (Test-Path -LiteralPath $logFile)) {
        $logMessage | Out-File -LiteralPath $logFile -Encoding UTF8
    } else {
        Add-Content -LiteralPath $logFile -Value $logMessage
    }
}

# Функция для принудительного закрытия MusicBee
function Stop-MusicBee {
    Write-Log "=== ПРОВЕРКА ПРОЦЕССА MUSICBEE ===" -Color "Cyan"
    
    $musicBeeProcess = Get-Process -Name $processName -ErrorAction SilentlyContinue
    
    if ($musicBeeProcess) {
        Write-Log "  ⚠️ Обнаружен процесс MusicBee (PID: $($musicBeeProcess.Id))" -Color "Yellow"
        Write-Log "  Принудительно закрываю MusicBee..." -Color "Yellow"
        
        try {
            Stop-Process -Name $processName -Force -ErrorAction Stop
            Write-Log "  ✅ MusicBee успешно закрыта!" -Color "Green"
            
            # Даём время на полное закрытие
            Start-Sleep -Seconds 2
        } catch {
            Write-Log "  ❌ Не удалось закрыть MusicBee: $_" -Color "Red"
            Write-Log "  Попробуйте закрыть программу вручную и запустите скрипт снова" -Color "Yellow"
            Read-Host "Нажмите Enter для выхода"
            exit 1
        }
    } else {
        Write-Log "  ✅ MusicBee не запущена, продолжаем работу..." -Color "Green"
    }
    Write-Log ""
}

# Функция для обработки одной задачи
function Process-Task {
    param(
        [string]$TaskName,
        [string]$PlaylistPath,
        [string]$TargetPath
    )
    
    Write-Log "========================================" -Color "Cyan"
    Write-Log "=== ЗАДАЧА: $TaskName ===" -Color "Cyan"
    Write-Log "========================================" -Color "Cyan"
    
    # 1. Проверяем существует ли плейлист
    Write-Log "  Проверка плейлиста: $PlaylistPath"
    if (-not (Test-Path -LiteralPath $PlaylistPath)) {
        Write-Log "    ❌ ПЛЕЙЛИСТ НЕ НАЙДЕН! Пропускаем задачу..." -Color "Red"
        return
    }
    
    $fileSize = (Get-Item -LiteralPath $PlaylistPath).Length
    Write-Log "    ✅ Плейлист найден (размер: $fileSize байт)" -Color "Green"
    
    # 2. Проверяем целевую папку
    Write-Log "  Проверка целевой папки: $TargetPath"
    if (-not (Test-Path -LiteralPath $TargetPath)) {
        Write-Log "    ⚠️ Целевая папка не существует, создаю..." -Color "Yellow"
        try {
            New-Item -ItemType Directory -Path $TargetPath -Force | Out-Null
            Write-Log "    ✅ Целевая папка создана" -Color "Green"
        } catch {
            Write-Log "    ❌ НЕ УДАЛОСЬ СОЗДАТЬ ПАПКУ: $_" -Color "Red"
            return
        }
    } else {
        Write-Log "    ✅ Целевая папка существует" -Color "Green"
    }
    
    # 3. Проверяем права на запись в целевую папку
    $testFile = Join-Path $TargetPath "test_write.tmp"
    try {
        "test" | Out-File -LiteralPath $testFile -ErrorAction Stop
        Remove-Item -LiteralPath $testFile
        Write-Log "    ✅ Есть права на запись в целевую папку" -Color "Green"
    } catch {
        Write-Log "    ❌ НЕТ ПРАВ НА ЗАПИСЬ в целевую папку! Пропускаем задачу..." -Color "Red"
        return
    }
    
    Write-Log ""
    
    # === ЧИТАЕМ ПЛЕЙЛИСТ ===
    Write-Log "  Чтение плейлиста..." -Color "Yellow"
    
    $content = $null
    $usedEncoding = $null
    
    # Пробуем UTF-8
    try {
        $content = Get-Content -LiteralPath $PlaylistPath -Encoding UTF8 -ErrorAction Stop
        $usedEncoding = "UTF-8"
        Write-Log "    ✅ Плейлист прочитан (кодировка: $usedEncoding, строк: $($content.Count))" -Color "Green"
    } catch {
        Write-Log "    ⚠️ Не удалось прочитать в UTF-8, пробую Default..." -Color "Yellow"
        try {
            $content = Get-Content -LiteralPath $PlaylistPath -Encoding Default -ErrorAction Stop
            $usedEncoding = "Default (ANSI)"
            Write-Log "    ✅ Плейлист прочитан (кодировка: $usedEncoding, строк: $($content.Count))" -Color "Green"
        } catch {
            Write-Log "    ❌ НЕ УДАЛОСЬ ПРОЧИТАТЬ ПЛЕЙЛИСТ: $_" -Color "Red"
            return
        }
    }
    
    Write-Log ""
    
    # Показываем первые 5 строк плейлиста для диагностики
    Write-Log "  Первые 5 строк плейлиста:" -Color "Yellow"
    $displayLines = $content | Select-Object -First 5
    $lineNum = 1
    foreach ($line in $displayLines) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            Write-Log "    ${lineNum}: [пустая строка]" -Color "DarkGray"
        } else {
            Write-Log "    ${lineNum}: $line" -Color "Gray"
        }
        $lineNum++
    }
    Write-Log ""
    
    # === ОБРАБОТКА ===
    Write-Log "  Начало обработки..." -Color "Cyan"
    
    $movedCount = 0
    $skippedCount = 0
    $errorCount = 0
    $processedFolders = @()
    
    # Добавляем обработку пустых строк
    $nonEmptyLines = $content | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    
    if ($nonEmptyLines.Count -eq 0) {
        Write-Log "    ⚠️ Плейлист пуст или содержит только пустые строки!" -Color "Yellow"
    } else {
        Write-Log "    Всего непустых строк: $($nonEmptyLines.Count)" -Color "DarkGray"
        
        foreach ($line in $nonEmptyLines) {
            $line = $line.Trim()
            
            # Пропускаем комментарии
            if ($line.StartsWith("#")) {
                Write-Log "    [КОММЕНТАРИЙ] $line" -Color "DarkGray"
                continue
            }
            
            Write-Log "" 
            Write-Log "    >>> Обработка: $line" -Color "Cyan"
            
            try {
                # Получаем папку, содержащую файл
                $sourceFolder = Split-Path -Path $line -Parent -ErrorAction Stop
                
                if ([string]::IsNullOrWhiteSpace($sourceFolder)) {
                    Write-Log "      ❌ Не удалось определить папку из пути" -Color "Red"
                    $errorCount++
                    continue
                }
                
                Write-Log "      📁 Исходная папка: $sourceFolder" -Color "Gray"
                
                # Проверяем, не обрабатывали ли мы уже эту папку
                if ($processedFolders -contains $sourceFolder) {
                    Write-Log "      ⏭️ Папка уже обработана, пропускаем" -Color "Yellow"
                    $skippedCount++
                    continue
                }
                
                $processedFolders += $sourceFolder
                
                # Проверяем существование исходной папки
                if (-not (Test-Path -LiteralPath $sourceFolder)) {
                    Write-Log "      ❌ Папка НЕ СУЩЕСТВУЕТ: $sourceFolder" -Color "Red"
                    Write-Log "         Возможно, уже перенесена" -Color "Yellow"
                    $errorCount++
                    continue
                }
                
                $folderName = Split-Path -Path $sourceFolder -Leaf
                Write-Log "      📛 Имя папки: $folderName" -Color "Gray"
                
                $destFolder = Join-Path -Path $TargetPath -ChildPath $folderName
                Write-Log "      🎯 Целевая папка: $destFolder" -Color "Gray"
                
                # Проверяем не переносим ли папку саму в себя
                if ($sourceFolder -eq $destFolder) {
                    Write-Log "      ⏭️ Папка уже в целевой директории" -Color "Yellow"
                    $skippedCount++
                    continue
                }
                
                # Проверяем существует ли уже в целевом месте
                if (Test-Path -LiteralPath $destFolder) {
                    Write-Log "      ⏭️ Папка уже существует в целевом месте" -Color "Yellow"
                    $skippedCount++
                    continue
                }
                
                # ПЕРЕНЕСЁМ!
                Write-Log "      🚀 ПЕРЕНОС: '$sourceFolder' --> '$destFolder'" -Color "Magenta"
                
                # Показываем содержимое папки перед переносом
                $items = Get-ChildItem -LiteralPath $sourceFolder
                if ($items.Count -gt 0) {
                    Write-Log "        Содержимое ($($items.Count) элементов):" -Color "DarkGray"
                    $items | Select-Object -First 3 | ForEach-Object {
                        Write-Log "          - $($_.Name)" -Color "DarkGray"
                    }
                    if ($items.Count -gt 3) {
                        Write-Log "          ... и ещё $($items.Count - 3) элементов" -Color "DarkGray"
                    }
                } else {
                    Write-Log "        ⚠️ Папка пуста" -Color "Yellow"
                }
                
                try {
                    Move-Item -LiteralPath $sourceFolder -Destination $TargetPath -Force -ErrorAction Stop
                    Write-Log "      ✅ ПЕРЕНОС УСПЕШЕН!" -Color "Green"
                    $movedCount++
                } catch {
                    Write-Log "      ❌ ОШИБКА ПЕРЕНОСА: $_" -Color "Red"
                    $errorCount++
                }
                
            } catch {
                Write-Log "      ❌ ОШИБКА: $_" -Color "Red"
                $errorCount++
            }
        }
    }
    
    # ИТОГИ ПО ЗАДАЧЕ
    Write-Log ""
    Write-Log "  === РЕЗУЛЬТАТ ПО ЗАДАЧЕ '$TaskName' ===" -Color "Cyan"
    Write-Log "  ✅ Перенесено папок: $movedCount" -Color "Green"
    Write-Log "  ⏭️ Пропущено: $skippedCount" -Color "Yellow"
    Write-Log "  ❌ Ошибок: $errorCount" -Color "Red"
    Write-Log ""
}

# Очищаем экран
Clear-Host

# Заголовок
Write-Log "========================================" -Color "Cyan"
Write-Log "=== ПЕРЕНОС ПАПОК ИЗ ПЛЕЙЛИСТОВ MUSICBEE ===" -Color "Cyan"
Write-Log "========================================" -Color "Cyan"
Write-Log "Папка скрипта: $scriptDir" -Color "DarkGray"
Write-Log "Лог файл: $logFile" -Color "DarkGray"
Write-Log ""

# === ЗАКРЫВАЕМ MUSICBEE ЕСЛИ ЗАПУЩЕНА ===
Stop-MusicBee

# === ОБРАБАТЫВАЕМ ВСЕ ЗАДАЧИ ===
$completedTasks = 0
foreach ($task in $tasks) {
    Process-Task -TaskName $task.Name -PlaylistPath $task.PlaylistPath -TargetPath $task.TargetPath
    $completedTasks++
    Write-Log "--- Задача $completedTasks из $($tasks.Count) обработана ---" -Color "DarkGray"
    Write-Log ""
}

# === ОБЩИЙ ИТОГ ===
Write-Log "========================================" -Color "Cyan"
Write-Log "=== ВСЕ ЗАДАЧИ ВЫПОЛНЕНЫ ===" -Color "Cyan"
Write-Log "========================================" -Color "Cyan"
Write-Log "📄 Полный лог сохранён: $logFile" -Color "DarkGray"
Write-Log ""

Write-Host "Нажмите любую клавишу для выхода..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")