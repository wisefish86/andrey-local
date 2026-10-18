# Compatibility launcher: keep the root BAT working.
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'Скрипты\Система GitHub\Синхронизация.ps1') @args
if (-not $?) { exit 1 }
