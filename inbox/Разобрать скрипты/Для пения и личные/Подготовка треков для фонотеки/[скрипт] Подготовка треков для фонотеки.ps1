param(
    [string]$FileListPath,
    [switch]$WhatIfMode
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$baseName = [IO.Path]::GetFileNameWithoutExtension($MyInvocation.MyCommand.Name)

$rulesFile = Join-Path $scriptDir "$baseName.txt"
$logFile = Join-Path $scriptDir "$baseName.log"

function Write-Log {
    param(
        [string]$Text,
        [string]$Color = "Gray"
    )

    $line = "[" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + "] " + $Text
    Write-Host $line -ForegroundColor $Color
    Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
}

function Replace-TextIgnoreCase {
    param(
        [string]$Text,
        [string]$From,
        [string]$To
    )

    if ([string]::IsNullOrEmpty($From)) {
        return $Text
    }

    return [regex]::Replace(
        $Text,
        [regex]::Escape($From),
        [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $To },
        "IgnoreCase"
    )
}

function Load-Rules {
    param([string]$Path)

    $rules = @{
        PREFIX  = @()
        SUFFIX  = @()
        REPLACE = @()
        REGEX   = @()
        ADD     = @()
    }

    if (-not (Test-Path -LiteralPath $Path)) {
        Write-Log "Файл правил не найден: $Path" "Yellow"
        return $rules
    }

    $section = ""

    foreach ($rawLine in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $trimmed = $rawLine.Trim()

        if ($trimmed -eq "" -or $trimmed.StartsWith("#")) {
            continue
        }

        if ($trimmed -match "^\[(.+)\]$") {
            $section = $matches[1].ToUpper()
            continue
        }

        if (-not $rules.ContainsKey($section)) {
            continue
        }

        if ($section -eq "REPLACE" -or $section -eq "REGEX") {
            $pos = $rawLine.IndexOf("|")

            if ($pos -ge 0) {
                $from = $rawLine.Substring(0, $pos)
                $to = $rawLine.Substring($pos + 1)

                $rules[$section] += [PSCustomObject]@{
                    From = $from
                    To   = $to
                }
            }
        }
        else {
            $rules[$section] += $rawLine
        }
    }

    return $rules
}

function Apply-Rules {
    param(
        [string]$OldName,
        $Rules
    )

    $name = [IO.Path]::GetFileNameWithoutExtension($OldName)
    $ext = [IO.Path]::GetExtension($OldName)

    Write-Log "ИМЯ ИСХОДНОЕ = [$name]" "DarkGray"

    # PREFIX
    foreach ($prefix in $Rules.PREFIX) {
        if ([string]::IsNullOrEmpty($prefix)) {
            continue
        }

        while ($name.StartsWith($prefix, [StringComparison]::InvariantCultureIgnoreCase)) {
            $name = $name.Substring($prefix.Length)
        }
    }

    Write-Log "ИМЯ ПОСЛЕ PREFIX = [$name]" "DarkGray"

    # SUFFIX — надежное удаление с учетом пробелов/невидимого хвоста
    foreach ($suffix in $Rules.SUFFIX) {
        if ([string]::IsNullOrWhiteSpace($suffix)) {
            continue
        }

        $suffixClean = $suffix.TrimEnd()
        $escapedSuffix = [regex]::Escape($suffixClean)

        $name = [regex]::Replace(
            $name,
            "(?i)$escapedSuffix[\s\p{Zs}]*$",
            ""
        )
    }

    Write-Log "ИМЯ ПОСЛЕ SUFFIX = [$name]" "DarkGray"

    # REPLACE
    foreach ($rule in $Rules.REPLACE) {
        $name = Replace-TextIgnoreCase -Text $name -From $rule.From -To $rule.To
    }

    Write-Log "ИМЯ ПОСЛЕ REPLACE = [$name]" "DarkGray"

    # REGEX
    foreach ($rule in $Rules.REGEX) {
        if ([string]::IsNullOrEmpty($rule.From)) {
            continue
        }

        $name = [regex]::Replace($name, $rule.From, $rule.To, "IgnoreCase")
    }

    Write-Log "ИМЯ ПОСЛЕ REGEX = [$name]" "DarkGray"

    # Очистка пробелов
    $name = [regex]::Replace($name, "[\s\p{Zs}]+", " ")
    $name = $name.Trim()

    # ADD
    foreach ($add in $Rules.ADD) {
        if ([string]::IsNullOrEmpty($add)) {
            continue
        }

        if (-not $name.EndsWith($add, [StringComparison]::InvariantCultureIgnoreCase)) {
            $name = $name + $add
        }
    }

    # Финальная очистка пробелов
    $name = [regex]::Replace($name, "[\s\p{Zs}]+", " ")
    $name = $name.Trim()

    Write-Log "ИМЯ ФИНАЛЬНОЕ = [$name$ext]" "DarkGray"

    return $name + $ext
}

Clear-Host

if (Test-Path -LiteralPath $logFile) {
    Remove-Item -LiteralPath $logFile -Force
}

Write-Log "PS1 запущен" "Cyan"
Write-Log "Файл правил: $rulesFile" "Gray"
Write-Log "Список файлов: $FileListPath" "Gray"

if ($WhatIfMode) {
    Write-Log "Режим предпросмотра: включен. Файлы не будут переименованы." "Yellow"
}

$rules = Load-Rules -Path $rulesFile

if (-not $FileListPath -or -not (Test-Path -LiteralPath $FileListPath)) {
    Write-Log "Не найден список файлов." "Red"
    pause
    exit 1
}

$files = @(Get-Content -LiteralPath $FileListPath -Encoding UTF8 | Where-Object {
    $_.Trim() -ne ""
})

Write-Log "Получено файлов: $($files.Count)" "White"

$processed = 0
$skipped = 0
$errors = 0

foreach ($file in $files) {
    try {
        if (-not (Test-Path -LiteralPath $file)) {
            Write-Log "Файл не найден: $file" "Red"
            $errors++
            continue
        }

        $item = Get-Item -LiteralPath $file

        if ($item.PSIsContainer) {
            Write-Log "Пропущена папка: $($item.FullName)" "Yellow"
            $skipped++
            continue
        }

        $newName = Apply-Rules -OldName $item.Name -Rules $rules

        if ($newName -eq $item.Name) {
            Write-Log "Без изменений: $($item.Name)" "Gray"
            $skipped++
            continue
        }

        $newPath = Join-Path $item.DirectoryName $newName

        if (Test-Path -LiteralPath $newPath) {
            Write-Log "Уже существует: $newName" "Yellow"
            $skipped++
            continue
        }

        if ($WhatIfMode) {
            Write-Log "[ПРЕДПРОСМОТР] $($item.Name) -> $newName" "Yellow"
            $processed++
            continue
        }

        Rename-Item -LiteralPath $item.FullName -NewName $newName -ErrorAction Stop

        Write-Log "$($item.Name) -> $newName" "Green"
        $processed++
    }
    catch {
        Write-Log "Ошибка: $file | $($_.Exception.Message)" "Red"
        $errors++
    }
}

Write-Log ""
Write-Log "=== РЕЗУЛЬТАТ ===" "Cyan"
Write-Log "Обработано: $processed" "Green"
Write-Log "Пропущено: $skipped" "Yellow"
Write-Log "Ошибок: $errors" "Red"
Write-Log "Лог: $logFile" "Gray"

pause

if ($errors -gt 0) {
    exit 1
}

exit 0