# Compatibility launcher: existing Windows scheduled task points here.
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'Скрипты\Система GitHub\Автосинхронизация.ps1') @args
if (-not $?) { exit 1 }
