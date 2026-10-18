# Compatibility entrypoint for existing README and shortcuts.
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'Скрипты\Система GitHub\Установить автосинхронизацию.ps1') @args
if (-not $?) { exit 1 }
