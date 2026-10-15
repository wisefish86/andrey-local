# Unattended sync for PUBLIC andrey-local. Never auto-publish outside inbox/.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-Location -LiteralPath $PSScriptRoot
$log = Join-Path $PSScriptRoot '.auto-sync.log'
$lock = New-Object System.Threading.Mutex($false, 'Local\\AndreyLocalAutoGitSync')
if (-not $lock.WaitOne(0)) { exit 0 }
try {
  $git = (Get-Command git -ErrorAction SilentlyContinue).Source
  if (-not $git) {
    $root = Join-Path $env:LOCALAPPDATA 'GitHubDesktop'
    $git = Get-ChildItem $root -Directory -Filter 'app-*' -ErrorAction SilentlyContinue |
      Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName 'resources\app\git\cmd\git.exe' } |
      Where-Object { Test-Path $_ } | Select-Object -First 1
  }
  if (-not $git) { throw 'Git is unavailable' }
  function Git { & $script:git @args; if ($LASTEXITCODE -ne 0) { throw "git $($args -join ' ') failed ($LASTEXITCODE)" } }
  $remote = (& $git remote get-url origin).Trim()
  if ($remote -notmatch '(^|[/:])wisefish86/andrey-local(\.git)?$') { throw "Unexpected origin: $remote" }
  if ((& $git branch --show-current).Trim() -ne 'main') { throw 'Not on main branch' }
  Git fetch origin main
  $status = @(& $git -c core.quotepath=false status --porcelain --untracked-files=all)
  if ($LASTEXITCODE -ne 0) { throw 'Cannot check status' }
  $outside = @($status | Where-Object { $_.Length -lt 4 -or $_.Substring(3).Trim('"') -notmatch '^inbox/' })
  if ($outside.Count) { throw "Local edits outside inbox: $($outside -join '; ')" }
  $incoming = @($status | Where-Object { $_.Length -ge 4 -and $_.Substring(3).Trim('"') -match '^inbox/' })
  foreach ($line in $incoming) {
    $path = $line.Substring(3).Trim('"')
    if ($line.Substring(0,2) -match 'D') { throw "Automated deletion blocked: $path" }
    if ($path -match '(?i)(^|/)(\.env[^/]*|id_rsa|id_ed25519|.*\.(key|pem|pfx|p12|kdbx|bak|exe|dll|ps1|bat|cmd|sh|sqlite|db))$') { throw "Sensitive/executable file blocked: $path" }
    if ($path -notmatch '(?i)\.(css|js|json|html|txt|md|png|jpg|jpeg|gif|webp|svg|pdf|zip|htz)$') { throw "Unknown file extension blocked: $path" }
    $full = Join-Path $PSScriptRoot ($path.Replace('/', [IO.Path]::DirectorySeparatorChar))
    if ((Test-Path -LiteralPath $full -PathType Leaf) -and (Get-Item -LiteralPath $full).Length -gt 10MB) { throw "File exceeds 10 MB: $path" }
  }
  if ($incoming.Count) {
    Git add -- inbox/
    & $git diff --cached --quiet
    if ($LASTEXITCODE -eq 1) { Git commit -m 'Auto-import inbox files' }
    elseif ($LASTEXITCODE -ne 0) { throw 'Cannot inspect staged changes' }
    Git pull --rebase origin main
    Git push origin main
  } else { Git pull --ff-only origin main }
  Add-Content -LiteralPath $log -Value "[$(Get-Date -Format s)] OK"
} catch {
  Add-Content -LiteralPath $log -Value "[$(Get-Date -Format s)] ERROR $($_.Exception.Message)"
  Write-Error $_
  exit 1
} finally { $lock.ReleaseMutex(); $lock.Dispose() }
