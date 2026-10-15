$linksFolder = "D:\YandexDisk\Ресурсы\Автоматизация\Папки для мониторинга"
$reportFile = Join-Path $PSScriptRoot "FolderReport.hta"
$debugFile = Join-Path $PSScriptRoot "FolderReport_Debug.txt"

"" | Out-File -FilePath $debugFile -Encoding utf8 -Force

function Log {
    param([string]$Text)
    $line = "[{0}] {1}" -f (Get-Date -Format "dd.MM.yyyy HH:mm:ss"), $Text
    $line | Out-File -FilePath $debugFile -Encoding utf8 -Append
    Write-Host $line
}

function Get-LnkTarget {
    param([string]$lnkPath)

    try {
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($lnkPath)
        return $shortcut.TargetPath
    }
    catch {
        Log ("Ошибка чтения ярлыка: " + $lnkPath + " | " + $_.Exception.Message)
        return $null
    }
}

function Get-FolderStats {
    param([string]$folderPath)

    if (-not (Test-Path $folderPath -PathType Container)) {
        return @{
            Count = 0
            Size  = 0
            Error = "Папка не найдена"
        }
    }

    try {
        $files = Get-ChildItem -Path $folderPath -File -Recurse -Force -ErrorAction SilentlyContinue
        $count = $files.Count
        $size = ($files | Measure-Object -Property Length -Sum).Sum

        if ($null -eq $size) {
            $size = 0
        }

        return @{
            Count = $count
            Size  = [int64]$size
            Error = $null
        }
    }
    catch {
        return @{
            Count = 0
            Size  = 0
            Error = $_.Exception.Message
        }
    }
}

function Convert-SizeToHuman {
    param([Int64]$Size)

    if ($Size -ge 1TB) { return "{0:N2} ТБ" -f ($Size / 1TB) }
    elseif ($Size -ge 1GB) { return "{0:N2} ГБ" -f ($Size / 1GB) }
    elseif ($Size -ge 1MB) { return "{0:N2} МБ" -f ($Size / 1MB) }
    elseif ($Size -ge 1KB) { return "{0:N2} КБ" -f ($Size / 1KB) }
    else { return "$Size Б" }
}

function HtmlEncode {
    param([string]$Text)
    if ($null -eq $Text) { return "" }
    return [System.Net.WebUtility]::HtmlEncode($Text)
}

function JsEscape {
    param([string]$Text)

    if ($null -eq $Text) { return "" }

    $s = $Text.Replace('\', '\\')
    $s = $s.Replace("'", "\'")
    $s = $s.Replace("`r", "")
    $s = $s.Replace("`n", "\n")
    return $s
}

Log "СТАРТ"
Log ("Папка ярлыков = " + $linksFolder)
Log ("Файл отчета = " + $reportFile)
Log ("Файл лога = " + $debugFile)

if (-not (Test-Path $linksFolder -PathType Container)) {
    Log "ОШИБКА: папка с ярлыками не найдена"
    exit
}

Log "Папка с ярлыками найдена"

try {
    $lnkFiles = Get-ChildItem -Path $linksFolder -Filter *.lnk -File -ErrorAction Stop
    Log ("Количество ярлыков = " + $lnkFiles.Count)
}
catch {
    Log ("ОШИБКА получения списка ярлыков: " + $_.Exception.Message)
    exit
}

if (-not $lnkFiles -or $lnkFiles.Count -eq 0) {
    Log "Ярлыки не найдены"
    exit
}

$data = @()

foreach ($lnk in $lnkFiles) {
    Log ("Обработка ярлыка: " + $lnk.FullName)

    $target = Get-LnkTarget -lnkPath $lnk.FullName

    if ([string]::IsNullOrWhiteSpace($target)) {
        Log "Целевой путь пустой"

        $data += [PSCustomObject]@{
            Name      = $lnk.BaseName
            Target    = ""
            FileCount = 0
            SizeBytes = 0
            SizeHuman = "0 Б"
            Error     = "Не удалось прочитать ярлык"
        }

        continue
    }

    Log ("Целевой путь = " + $target)

    $stats = Get-FolderStats -folderPath $target
    $sizeHuman = Convert-SizeToHuman -Size $stats.Size

    Log ("Файлов = " + $stats.Count + "; Размер = " + $sizeHuman)

    if ($stats.Error) {
        Log ("Ошибка папки = " + $stats.Error)
    }

    $data += [PSCustomObject]@{
        Name      = $lnk.BaseName
        Target    = $target
        FileCount = $stats.Count
        SizeBytes = [int64]$stats.Size
        SizeHuman = $sizeHuman
        Error     = $stats.Error
    }
}

$totalFiles = ($data | Where-Object { -not $_.Error } | Measure-Object -Property FileCount -Sum).Sum
$totalSize  = ($data | Where-Object { -not $_.Error } | Measure-Object -Property SizeBytes -Sum).Sum

if ($null -eq $totalFiles) { $totalFiles = 0 }
if ($null -eq $totalSize)  { $totalSize = 0 }

$totalSizeHuman = Convert-SizeToHuman -Size ([int64]$totalSize)

Log ("Всего файлов = " + $totalFiles)
Log ("Общий размер = " + $totalSizeHuman)

$html = @()
$html += '<html>'
$html += '<head>'
$html += '<meta http-equiv="X-UA-Compatible" content="IE=9" />'
$html += '<meta charset="utf-8">'
$html += '<title>Мониторинг папок</title>'
$html += '<HTA:APPLICATION ID="FolderMonitor" APPLICATIONNAME="Мониторинг папок" BORDER="thin" BORDERSTYLE="normal" CAPTION="yes" SHOWINTASKBAR="yes" SINGLEINSTANCE="yes" SYSMENU="yes" WINDOWSTATE="normal" SCROLL="yes" />'
$html += '<style>'
$html += 'body { font-family: Segoe UI, Arial, sans-serif; margin: 20px; background: #fff; color: #222; }'
$html += 'h1 { margin-bottom: 10px; }'
$html += 'table { border-collapse: collapse; width: 100%; }'
$html += 'th, td { border: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: middle; }'
$html += 'th { background: #f2f2f2; }'
$html += 'tr:nth-child(even) { background: #f9f9f9; }'
$html += 'tr:hover { background: #f3f7fb; }'
$html += '.err { color: #b00020; font-weight: bold; }'
$html += '.btn { display: inline-block; padding: 6px 10px; background: #1e88e5; color: #ffffff; text-decoration: none; border-radius: 4px; font-size: 13px; border: none; cursor: pointer; }'
$html += '.btn:hover { background: #1565c0; }'
$html += '.path { color: #666; font-size: 12px; margin-top: 3px; word-break: break-all; }'
$html += '.topline { margin-bottom: 14px; }'
$html += '</style>'
$html += '<script language="javascript">'
$html += 'function openFolder(path) {'
$html += '    try {'
$html += '        var shell = new ActiveXObject("WScript.Shell");'
$html += '        shell.Run(\'explorer.exe "\' + path + \'"\');'
$html += '    }'
$html += '    catch(e) {'
$html += '        alert("Не удалось открыть папку: " + path + "\n" + e.message);'
$html += '    }'
$html += '}'
$html += '</script>'
$html += '</head>'
$html += '<body>'
$html += '<h1>Мониторинг папок</h1>'
$html += '<div class="topline"><b>Дата:</b> ' + (Get-Date -Format "dd.MM.yyyy HH:mm") + '</div>'
$html += '<table>'
$html += '<tr><th>Название</th><th>Количество файлов</th><th>Размер</th><th>Действие</th></tr>'

foreach ($item in $data) {
    $name = HtmlEncode $item.Name

    if ($item.Error) {
        $err = HtmlEncode $item.Error
        $html += '<tr><td class="err">' + $name + '</td><td>-</td><td class="err">' + $err + '</td><td>-</td></tr>'
    }
    else {
        $sizeHuman = HtmlEncode $item.SizeHuman
        $fileCount = "{0:N0}" -f $item.FileCount
        $safePath = HtmlEncode $item.Target
        $jsPath = JsEscape $item.Target

        $nameCell = '<div>' + $name + '</div><div class="path">' + $safePath + '</div>'
        $openBtn = '<button class="btn" onclick="openFolder(''' + $jsPath + ''')">Открыть папку</button>'

        $row = '<tr><td>' + $nameCell + '</td><td>' + $fileCount + '</td><td>' + $sizeHuman + '</td><td>' + $openBtn + '</td></tr>'
        $html += $row
    }
}

$html += '</table>'
$html += '<p><b>Всего:</b> ' + $totalFiles + ' файлов, ' + $totalSizeHuman + '</p>'
$html += '</body>'
$html += '</html>'

try {
    $html -join "`r`n" | Out-File -FilePath $reportFile -Encoding utf8 -Force
    Log ("Отчет сохранен: " + $reportFile)
}
catch {
    Log ("ОШИБКА сохранения отчета: " + $_.Exception.Message)
    exit
}

try {
    Start-Process mshta.exe $reportFile
    Log "Отчет открыт"
}
catch {
    Log ("ОШИБКА открытия отчета: " + $_.Exception.Message)
}

Log "ФИНИШ"