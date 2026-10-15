# Automatic repository sync. Public repo: do not add confidential files.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-Location -LiteralPath $PSScriptRoot
$log = Join-Path $PSScriptRoot '.auto-sync.log'
$lock = New-Object System.Threading.Mutex($false, 'Local\AndreyLocalAutoGitSync')
if (-not $lock.WaitOne(0)) { exit 0 }
function Write-SyncLog([string]$entry) {
  $previous = @()
  if (Test-Path -LiteralPath $log) {
    $previous = @(Get-Content -LiteralPath $log -Tail 9 -ErrorAction SilentlyContinue)
  }
  @($previous) + @($entry) | Set-Content -LiteralPath $log -Encoding UTF8
}
try {
  $command = Get-Command git -ErrorAction SilentlyContinue
  $git = if ($command) { $command.Source } else { $null }
  if (-not $git) {
    $root = Join-Path $env:LOCALAPPDATA 'GitHubDesktop'
    $git = Get-ChildItem $root -Directory -Filter 'app-*' -ErrorAction SilentlyContinue |
      Sort-Object Name -Descending |
      ForEach-Object { Join-Path $_.FullName 'resources\app\git\cmd\git.exe' } |
      Where-Object { Test-Path $_ } | Select-Object -First 1
  }
  if (-not $git) { throw 'Git not found' }
  function Invoke-Git {
    & $script:git @args
    if ($LASTEXITCODE -ne 0) { throw "Git exited with $LASTEXITCODE" }
  }
  $remote = (& $git remote get-url origin).Trim()
  if ($LASTEXITCODE -ne 0 -or $remote -notmatch '(^|[/:])wisefish86/andrey-local(\.git)?$') {
    throw "Unexpected repository: $remote"
  }
  if ((& $git branch --show-current).Trim() -ne 'main') { throw 'Expected branch main' }
  Invoke-Git fetch origin main
  $status = @(& $git -c core.quotepath=false status --porcelain --untracked-files=all)
  if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect changes' }
  foreach ($line in $status) {
    if ($line.Length -lt 4) { continue }
    $file = $line.Substring(3).Trim('"')
    if ($file -match '(?i)(^|/)(\.env[^/]*|id_rsa|id_ed25519|.*\.(key|pem|pfx|p12|kdbx))$') {
      throw "Sensitive filename blocked: $file"
    }
    $full = Join-Path $PSScriptRoot ($file.Replace('/', [IO.Path]::DirectorySeparatorChar))
    if ((Test-Path -LiteralPath $full -PathType Leaf) -and (Get-Item -LiteralPath $full).Length -gt 10MB) {
      throw "File larger than 10 MB: $file"
    }
  }
  if ($status.Count) {
    Invoke-Git add -A
    & $git diff --cached --quiet
    if ($LASTEXITCODE -eq 1) { Invoke-Git commit -m 'Auto-sync local repository' }
    elseif ($LASTEXITCODE -ne 0) { throw 'Cannot inspect staged changes' }
    Invoke-Git pull --rebase origin main
    Invoke-Git push origin main
  } else {
    Invoke-Git pull --ff-only origin main
  }
  # Update local launch shortcuts after Git sync. Never execute discovered scripts.
  $catalog = Join-Path $PSScriptRoot 'Скрипты\Система ярлыков\Обновить-ярлыки.ps1'
  if (Test-Path -LiteralPath $catalog -PathType Leaf) {
    try {
      & $catalog | Out-Null
    } catch {
      Write-SyncLog "[$(Get-Date -Format s)] SHORTCUT ERROR $($_.Exception.Message)"
    }
  }
  Write-SyncLog "[$(Get-Date -Format s)] OK"
} catch {
  Write-SyncLog "[$(Get-Date -Format s)] ERROR $($_.Exception.Message)"
  Write-Error $_
  exit 1
} finally {
  $lock.ReleaseMutex()
  $lock.Dispose()
}
