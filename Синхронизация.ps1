$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Set-Location -LiteralPath $PSScriptRoot

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
Invoke-Git -c core.quotepath=false fetch origin main

$changes = @(& $git -c core.quotepath=false status --porcelain --untracked-files=all)
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect local changes' }

if ($changes.Count) {
    Write-Host 'Local changes to review before publishing:' -ForegroundColor Yellow
    $changes | ForEach-Object { Write-Host $_ }
    Write-Host 'WARNING: this repository is PUBLIC.' -ForegroundColor Yellow
    $answer = Read-Host 'Type YES to publish these changes'
    if ($answer -cne 'YES') {
        Write-Host 'Nothing published; remote changes not applied.'
        return
    }
    $paths = @(& $git -c core.quotepath=false ls-files --others --exclude-standard)
    $risky = @($paths | Where-Object { $_ -match '(?i)(^|/)(\.env.*|id_rsa|id_ed25519|.*\.(key|pem|pfx|p12|kdbx)|.*\.bak)$' })
    if ($risky.Count) {
        $risky | ForEach-Object { Write-Host "Private-looking file: $_" -ForegroundColor Red }
        throw 'Remove sensitive files before publishing.'
    }
    Invoke-Git add -A
    Invoke-Git diff --cached --check
    & $git diff --cached --quiet
    if ($LASTEXITCODE -eq 1) {
        Invoke-Git commit -m 'Sync local files'
    } elseif ($LASTEXITCODE -ne 0) {
        throw 'Cannot check staged changes'
    }
    Invoke-Git pull --rebase origin main
    Invoke-Git push origin main
} else {
    Invoke-Git pull --ff-only origin main
}
Write-Host 'Synchronization complete.' -ForegroundColor Green
