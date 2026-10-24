$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location -LiteralPath $repoRoot

$cmd = Get-Command git -ErrorAction SilentlyContinue
if ($cmd) {
    $git = $cmd.Source
} else {
    $desktopRoot = Join-Path $env:LOCALAPPDATA 'GitHubDesktop'
    $git = Get-ChildItem $desktopRoot -Directory -Filter 'app-*' -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending |
        ForEach-Object { Join-Path $_.FullName 'resources\app\git\cmd\git.exe' } |
        Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
        Select-Object -First 1
}

if (-not $git) {
    throw 'Git not found. Start GitHub Desktop first.'
}

function Invoke-Git {
    & $script:git @args
    if ($LASTEXITCODE -ne 0) {
        throw "Git exited with code $LASTEXITCODE"
    }
}

Write-Host '=== andrey-local ===' -ForegroundColor Cyan

$origin = (& $git remote get-url origin).Trim()
if ($LASTEXITCODE -ne 0 -or $origin -notmatch 'wisefish86/andrey-local(\.git)?$') {
    throw "Unexpected repository: $origin"
}

$branch = (& $git branch --show-current).Trim()
if ($branch -ne 'main') {
    throw "Expected branch main, found: $branch"
}

Invoke-Git config --local core.quotepath false
Invoke-Git fetch origin main

$changes = @(& $git status --porcelain --untracked-files=all)
if ($LASTEXITCODE -ne 0) {
    throw 'Cannot inspect local changes'
}

# Apply origin/main before deciding which changes are genuinely local.
# Dirty working-tree changes are temporarily stashed and restored afterwards.
$hadTempStash = $false
if ($changes.Count) {
    Write-Host 'Local working-tree changes detected; preserving them while updating origin/main.' -ForegroundColor Cyan
    $stashName = "__andrey_sync_temp__$([DateTime]::Now.ToString('yyyyMMdd_HHmmss'))"
    & $git stash push -u -m $stashName
    if ($LASTEXITCODE -ne 0) {
        throw 'Cannot temporarily stash local changes'
    }
    $hadTempStash = $true
}

$aheadBehind = (& $git rev-list --left-right --count HEAD...origin/main).Trim() -split '\s+'
if ($LASTEXITCODE -ne 0 -or $aheadBehind.Count -ne 2) {
    throw 'Cannot inspect branch divergence'
}

if ([int]$aheadBehind[0] -gt 0) {
    Write-Host 'Local commits exist; rebasing on origin/main without pushing.' -ForegroundColor Yellow
    Invoke-Git rebase origin/main
} else {
    Invoke-Git merge --ff-only origin/main
}

if ($hadTempStash) {
    Write-Host 'Restoring preserved local working-tree changes...' -ForegroundColor Cyan
    & $git stash pop
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Temporary stash was NOT dropped because restore reported a conflict.' -ForegroundColor Red
        Write-Host 'Resolve the conflict before publishing anything.' -ForegroundColor Red
        throw 'Cannot restore local changes cleanly after updating origin/main'
    }
}

$changes = @(& $git status --porcelain --untracked-files=all)
if ($LASTEXITCODE -ne 0) {
    throw 'Cannot inspect local changes after updating origin/main'
}

if ($changes.Count) {
    Write-Host 'Local changes to review before publishing:' -ForegroundColor Yellow
    $changes | ForEach-Object { Write-Host $_ }
    Write-Host 'WARNING: this repository is PUBLIC.' -ForegroundColor Yellow

    $answer = Read-Host 'Confirm public upload (1 / U / YES / DA)'
    $approved = $answer.Trim().ToLowerInvariant() -in @('1', 'u', 'г', 'yes', 'y', 'да', 'д')

    if ($approved) {
        $paths = @(& $git ls-files --others --exclude-standard)
        if ($LASTEXITCODE -ne 0) {
            throw 'Cannot inspect untracked files'
        }

        $risky = @(
            $paths | Where-Object {
                $_ -match '(?i)(^|/)(\.env.*|id_rsa|id_ed25519|.*\.(key|pem|pfx|p12|kdbx)|.*\.bak)$'
            }
        )

        if ($risky.Count) {
            $risky | ForEach-Object {
                Write-Host "Private-looking file: $_" -ForegroundColor Red
            }
            throw 'Remove sensitive files before publishing.'
        }

        Invoke-Git add -A

        & $git --no-pager diff --cached --quiet
        if ($LASTEXITCODE -eq 1) {
            Invoke-Git commit -m 'Sync local files'
        } elseif ($LASTEXITCODE -ne 0) {
            throw 'Cannot check staged changes'
        }

        Invoke-Git pull --rebase origin main
        Invoke-Git push origin main
    } else {
        Write-Host 'Nothing published. Remote changes are already applied locally.' -ForegroundColor Yellow
    }
}

# Git does not preserve Hidden/System attributes of desktop.ini.
try {
    $count = 0
    Get-ChildItem -LiteralPath $repoRoot -Filter 'desktop.ini' -File -Force -Recurse -ErrorAction Stop |
        ForEach-Object {
            $wanted = $_.Attributes -bor [System.IO.FileAttributes]::Hidden -bor [System.IO.FileAttributes]::System
            if ($_.Attributes -ne $wanted) {
                $_.Attributes = $wanted
            }
            $count++
        }
    Write-Host ("desktop.ini attributes restored: " + $count) -ForegroundColor Cyan
} catch {
    Write-Warning ("desktop.ini attribute restoration failed: " + $_.Exception.Message)
}

# Refresh local shortcut catalog after repository sync.
$catalog = Join-Path $repoRoot 'Скрипты\Личные\Система ярлыков в andrey-local\Обновить-ярлыки.ps1'
if (Test-Path -LiteralPath $catalog -PathType Leaf) {
    Write-Host 'Updating Windows shortcuts...' -ForegroundColor Cyan
    & $catalog
} else {
    Write-Warning "Shortcut generator not found: $catalog"
}

Write-Host 'Synchronization complete.' -ForegroundColor Green
