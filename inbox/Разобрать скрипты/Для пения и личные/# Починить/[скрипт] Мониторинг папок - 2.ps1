$linksFolder = "D:\YandexDisk\Ресурсы\Автоматизация\Папки для мониторинга"
$reportFile = Join-Path $PSScriptRoot "FolderReport.html"
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
        Log ("ERROR reading shortcut: " + $lnkPath + " | " + $_.Exception.Message)
        return $null
    }
}

function Get-FolderStats {
    param([string]$folderPath)

    if (-not (Test-Path $folderPath -PathType Container)) {
        return @{
            Count = 0
            Size = 0
            Error = "Folder not found"
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
            Size = [int64]$size
            Error = $null
        }
    }
    catch {
        return @{
            Count = 0
            Size = 0
            Error = $_.Exception.Message
        }
    }
}

function Convert-SizeToHuman {
    param([Int64]$Size)

    if ($Size -ge 1TB) { return "{0:N2} TB" -f ($Size / 1TB) }
    elseif ($Size -ge 1GB) { return "{0:N2} GB" -f ($Size / 1GB) }
    elseif ($Size -ge 1MB) { return "{0:N2} MB" -f ($Size / 1MB) }
    elseif ($Size -ge 1KB) { return "{0:N2} KB" -f ($Size / 1KB) }
    else { return "$Size B" }
}

function HtmlEncode {
    param([string]$Text)
    if ($null -eq $Text) { return "" }
    return [System.Net.WebUtility]::HtmlEncode($Text)
}

Log "START"
Log ("linksFolder = " + $linksFolder)
Log ("reportFile = " + $reportFile)
Log ("debugFile = " + $debugFile)

if (-not (Test-Path $linksFolder -PathType Container)) {
    Log "ERROR: links folder not found"
    exit
}

Log "Links folder exists"

try {
    $lnkFiles = Get-ChildItem -Path $linksFolder -Filter *.lnk -File -ErrorAction Stop
    Log ("Shortcut count = " + $lnkFiles.Count)
}
catch {
    Log ("ERROR listing shortcuts: " + $_.Exception.Message)
    exit
}

if (-not $lnkFiles -or $lnkFiles.Count -eq 0) {
    Log "No shortcut files found"
    exit
}

$data = @()

foreach ($lnk in $lnkFiles) {
    Log ("Processing shortcut: " + $lnk.FullName)

    $target = Get-LnkTarget -lnkPath $lnk.FullName

    if ([string]::IsNullOrWhiteSpace($target)) {
        Log "TargetPath is empty"

        $data += [PSCustomObject]@{
            Name = $lnk.BaseName
            Target = ""
            FileCount = 0
            SizeBytes = 0
            SizeHuman = "0 B"
            Error = "Shortcut target is empty"
        }

        continue
    }

    Log ("TargetPath = " + $target)

    $stats = Get-FolderStats -folderPath $target
    $sizeHuman = Convert-SizeToHuman -Size $stats.Size

    Log ("Files = " + $stats.Count + "; Size = " + $sizeHuman)

    if ($stats.Error) {
        Log ("Folder error = " + $stats.Error)
    }

    $data += [PSCustomObject]@{
        Name = $lnk.BaseName
        Target = $target
        FileCount = $stats.Count
        SizeBytes = [int64]$stats.Size
        SizeHuman = $sizeHuman
        Error = $stats.Error
    }
}

$totalFiles = ($data | Where-Object { -not $_.Error } | Measure-Object -Property FileCount -Sum).Sum
$totalSize = ($data | Where-Object { -not $_.Error } | Measure-Object -Property SizeBytes -Sum).Sum

if ($null -eq $totalFiles) { $totalFiles = 0 }
if ($null -eq $totalSize) { $totalSize = 0 }

$totalSizeHuman = Convert-SizeToHuman -Size ([int64]$totalSize)

Log ("Total files = " + $totalFiles)
Log ("Total size = " + $totalSizeHuman)

$html = @()
$html += '<!DOCTYPE html>'
$html += '<html>'
$html += '<head>'
$html += '<meta charset="utf-8">'
$html += '<title>Folder Report</title>'
$html += '<style>'
$html += 'body { font-family: Segoe UI, Arial, sans-serif; margin: 20px; background: #fff; color: #222; }'
$html += 'h1 { margin-bottom: 10px; }'
$html += 'table { border-collapse: collapse; width: 100%; }'
$html += 'th, td { border: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: middle; }'
$html += 'th { background: #f2f2f2; }'
$html += 'tr:nth-child(even) { background: #f9f9f9; }'
$html += 'tr:hover { background: #f3f7fb; }'
$html += '.err { color: #b00020; font-weight: bold; }'
$html += '.btn { display: inline-block; padding: 6px 10px; background: #1e88e5; color: #ffffff !important; text-decoration: none; border-radius: 4px; font-size: 13px; }'
$html += '.btn:hover { background: #1565c0; }'
$html += '.path { color: #666; font-size: 12px; margin-top: 3px; word-break: break-all; }'
$html += '</style>'
$html += '</head>'
$html += '<body>'
$html += '<h1>Folder Report</h1>'
$html += '<p>Date: ' + (Get-Date -Format "dd.MM.yyyy HH:mm") + '</p>'
$html += '<table>'
$html += '<tr><th>Name</th><th>Files</th><th>Size</th><th>Open</th></tr>'

foreach ($item in $data) {
    $name = HtmlEncode $item.Name

    if ($item.Error) {
        $err = HtmlEncode $item.Error
        $html += '<tr><td class="err">' + $name + '</td><td>-</td><td class="err">' + $err + '</td><td>-</td></tr>'
    }
    else {
        try {
            $targetUri = [System.Uri]::new($item.Target).AbsoluteUri
            $targetUri = HtmlEncode $targetUri
            $sizeHuman = HtmlEncode $item.SizeHuman
            $fileCount = "{0:N0}" -f $item.FileCount
            $safePath = HtmlEncode $item.Target

            $nameCell = '<div>' + $name + '</div><div class="path">' + $safePath + '</div>'
            $openBtn = '<a class="btn" href="' + $targetUri + '">Open folder</a>'

            $row = '<tr><td>' + $nameCell + '</td><td>' + $fileCount + '</td><td>' + $sizeHuman + '</td><td>' + $openBtn + '</td></tr>'
            $html += $row
        }
        catch {
            Log ("ERROR creating URI for: " + $item.Target + " | " + $_.Exception.Message)
            $html += '<tr><td class="err">' + $name + '</td><td>-</td><td class="err">URI error</td><td>-</td></tr>'
        }
    }
}

$html += '</table>'
$html += '<p><b>Total:</b> ' + $totalFiles + ' files, ' + $totalSizeHuman + '</p>'
$html += '</body>'
$html += '</html>'

try {
    $html -join "`r`n" | Out-File -FilePath $reportFile -Encoding utf8 -Force
    Log ("HTML saved: " + $reportFile)
}
catch {
    Log ("ERROR saving HTML: " + $_.Exception.Message)
    exit
}

try {
    Start-Process $reportFile
    Log "HTML opened"
}
catch {
    Log ("ERROR opening HTML: " + $_.Exception.Message)
}

Log "FINISH"