$gh = "C:\Program Files\GitHub CLI\gh.exe"
$repo = "wisefish86/singer-andreway"
$workflow = "import-anytype-v2.yml"

$script:openedPage = $false

function Finish {
    if ($script:openedPage) { return }
    Write-Host ""
    Read-Host "Нажмите Enter, чтобы закрыть окно"
}

function Open-NotionPage([string]$url) {
    # Launch through Windows Explorer so Notion desktop logs do not flood this console.
    Start-Process -FilePath "explorer.exe" -ArgumentList @($url) -ErrorAction Stop
    $script:openedPage = $true
}

Write-Host "====================================" -ForegroundColor Cyan
Write-Host "      ИМПОРТ ANYTYPE В NOTION" -ForegroundColor Cyan
Write-Host "===================================="
Write-Host ""

try {
    if (-not (Test-Path $gh)) {
        throw "GitHub CLI не найден."
    }

    Write-Host "Проверяю подключение к GitHub..."
    & $gh auth status 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Нет авторизации GitHub. Выполните gh auth login."
    }

    $old = & $gh run list --repo $repo --workflow $workflow `
        --event workflow_dispatch --limit 1 --json databaseId |
        ConvertFrom-Json

    $oldId = if ($old) { $old[0].databaseId } else { 0 }

    Write-Host "Запускаю импорт..." -ForegroundColor Yellow
    $output = & $gh workflow run $workflow --repo $repo 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось запустить GitHub Actions: $output"
    }

    $runId = $null
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 2
        $runs = & $gh run list --repo $repo --workflow $workflow `
            --event workflow_dispatch --limit 5 --json databaseId |
            ConvertFrom-Json

        $newRun = $runs | Where-Object {
            $_.databaseId -gt $oldId
        } | Sort-Object databaseId -Descending | Select-Object -First 1

        if ($newRun) {
            $runId = $newRun.databaseId
            break
        }
    }

    if (-not $runId) {
        throw "Запуск отправлен, но номер выполнения пока не найден. Проверьте GitHub Actions."
    }

    Write-Host "Импорт запущен. Номер: $runId" -ForegroundColor Green
    Write-Host "Ожидаю завершения..."
    Write-Host ""

    & $gh run watch $runId --repo $repo --exit-status --interval 5
    $watchCode = $LASTEXITCODE

    Write-Host ""
    Write-Host "========== РЕЗУЛЬТАТ ==========" -ForegroundColor Cyan

    $logs = & $gh run view $runId --repo $repo --log 2>&1
    $summary = $logs | Where-Object {
        $_ -match "ZIP archives found:|VERIFIED and archived:|FAILED, ZIP retained:|RESULT "
    }

    if ($summary) {
        $summary | ForEach-Object {
            ($_ -split "`t")[-1]
        }
    }

    if ($watchCode -eq 0 -and $summary -match 'ZIP archives found: 0') {
        Write-Host ""
        Write-Host "Папка 01_Inbox пуста. Импортировать нечего." -ForegroundColor Yellow
    } elseif ($watchCode -eq 0) {
        Write-Host ""
        Write-Host "УСПЕШНО: обработка завершена!" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "ОШИБКА: не всё удалось импортировать." -ForegroundColor Red
        if (-not $summary) {
            & $gh run view $runId --repo $repo --log-failed
        }
    }

    # Extract successful page URLs from the current importer's RESULT PAGE lines.
    $pages = @()
    foreach ($line in $logs) {
        if ($line -match 'RESULT PAGE:\s*(.*?)\s*\| blocks:.*?\| Notion:\s*(https://app\.notion\.com/p/[0-9a-fA-F]{32})') {
            $pages += [PSCustomObject]@{
                Title = $Matches[1].Trim()
                Url = $Matches[2]
            }
        }
    }
    if ($pages.Count -gt 0) {
        Write-Host ""
        Write-Host "СТРАНИЦЫ NOTION:" -ForegroundColor Cyan
        for ($j = 0; $j -lt $pages.Count; $j++) {
            Write-Host ("{0}. {1}" -f ($j + 1), $pages[$j].Title) -ForegroundColor Green
            Write-Host ("   {0}" -f $pages[$j].Url)
        }
        Write-Host ""
        $selection = (Read-Host "Открыть в браузере: номер, ВСЕ или Enter для пропуска").Trim()
        if ($selection -match '^\d+$') {
            $number = [int]$selection
            if ($number -ge 1 -and $number -le $pages.Count) {
                Open-NotionPage $pages[$number - 1].Url
            } else {
                Write-Host "Такого номера нет." -ForegroundColor Yellow
            }
        } elseif ($selection -match '^(?i:все|all)$') {
            foreach ($page in $pages) { Open-NotionPage $page.Url }
        }
    }
    Write-Host "Подробности:"
    Write-Host "https://github.com/$repo/actions/runs/$runId"
}
catch {
    Write-Host ""
    Write-Host "ОШИБКА: $($_.Exception.Message)" -ForegroundColor Red
}

Finish


