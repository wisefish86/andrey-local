$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location -LiteralPath $repoRoot

$cmd = Get-Command git -ErrorAction SilentlyContinue
if ($cmd) {
    $git = $cmd.Source
} else {
    $root = Join-Path $env:LOCALAPPDATA 'GitHubDesktop'
    $git = Get-ChildItem $root -Directory -Filter 'app-*' -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending |
        ForEach-Object { Join-Path $_.FullName 'resources\app\git\cmd\git.exe' } |
        Where-Object { Test-Path $_ } |
        Select-Object -First 1
}
if (-not $git) { throw 'Git not found. Start GitHub Desktop first.' }

function Invoke-Git {
    & $script:git @args
    if ($LASTEXITCODE -ne 0) { throw "Git exited with code $LASTEXITCODE" }
}

Write-Host '=== andrey-local ===' -ForegroundColor Cyan
$origin = (& $git remote get-url origin).Trim()
if ($LASTEXITCODE -ne 0 -or $origin -notmatch 'wisefish86/andrey-local(\.git)?$') {
    throw "Unexpected repository: $origin"
}
$branch = (& $git branch --show-current).Trim()
if ($branch -ne 'main') { throw "Expected branch main, found: $branch" }
Invoke-Git config --local core.quotepath false
Invoke-Git fetch origin main

$changes = @(& $git status --porcelain --untracked-files=all)
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect local changes' }

if (-not $changes.Count) {
    # Update ignore rules first, then recheck: new files may become visible.
    $aheadBehind = (& $git rev-list --left-right --count HEAD...origin/main).Trim() -split '\s+'
    if ($LASTEXITCODE -ne 0 -or $aheadBehind.Count -ne 2) { throw 'Cannot inspect branch divergence' }
    if ([int]$aheadBehind[0] -gt 0) {
        Write-Host 'Local commits exist; rebasing on origin/main without pushing.' -ForegroundColor Yellow
        Invoke-Git rebase origin/main
    } else {
        Invoke-Git merge --ff-only origin/main
    }
    $changes = @(& $git status --porcelain --untracked-files=all)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect local changes after pull' }
}

if ($changes.Count) {
    Write-Host 'Local changes to review before publishing:' -ForegroundColor Yellow
    $changes | ForEach-Object { Write-Host $_ }
    Write-Host 'WARNING: this repository is PUBLIC.' -ForegroundColor Yellow
    $answer = Read-Host 'Confirm public upload (1 / U / YES / DA)'
    if ($answer.Trim().ToLowerInvariant() -notin @('1', 'u', 'г', 'yes', 'y', 'да', 'д')) {
        Write-Host 'Nothing published; remote changes not applied.'
        return
    }
    $paths = @(& $git ls-files --others --exclude-standard)
    $risky = @($paths | Where-Object { $_ -match '(?i)(^|/)(\.env.*|id_rsa|id_ed25519|.*\.(key|pem|pfx|p12|kdbx)|.*\.bak)$' })
    if ($risky.Count) {
        $risky | ForEach-Object { Write-Host "Private-looking file: $_" -ForegroundColor Red }
        throw 'Remove sensitive files before publishing.'
    }
    Invoke-Git add -A
    # A trailing blank line is harmless; do not block file synchronization on whitespace lint.
    & $git --no-pager diff --cached --quiet
    if ($LASTEXITCODE -eq 1) {
        Invoke-Git commit -m 'Sync local files'
    } elseif ($LASTEXITCODE -ne 0) {
        throw 'Cannot check staged changes'
    }
    Invoke-Git pull --rebase origin main
    Invoke-Git push origin main
} else {
    Invoke-Git merge --ff-only origin/main
}
# Restore Windows Explorer metadata after Git updates. Git does not track Hidden/System attributes.
try {
    $count = 0
    Get-ChildItem -LiteralPath $repoRoot -Filter 'desktop.ini' -File -Force -Recurse -ErrorAction Stop |
        ForEach-Object {
            $wanted = $_.Attributes -bor [System.IO.FileAttributes]::Hidden -bor [System.IO.FileAttributes]::System
            if ($_.Attributes -ne $wanted) { $_.Attributes = $wanted }
            $count++
        }
    Write-Host ("desktop.ini attributes restored: " + $count) -ForegroundColor Cyan
} catch {
    Write-Warning ("desktop.ini attribute restoration failed: " + $_.Exception.Message)
}

# Refresh local shortcut catalog after repository sync. Shortcuts stay beside BAT launchers.
$catalog = Join-Path $repoRoot 'Скрипты\Личные\Система ярлыков\Обновить-ярлыки.ps1'
if (Test-Path -LiteralPath $catalog -PathType Leaf) {
    Write-Host 'Updating Windows shortcuts...' -ForegroundColor Cyan
    & $catalog
} else {
    Write-Warning "Shortcut generator not found: $catalog"
}
Write-Host 'Synchronization complete.' -ForegroundColor Green
