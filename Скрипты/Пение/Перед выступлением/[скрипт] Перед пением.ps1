# ============================================
# Мессенджеры и коммуникация
# ============================================
Get-Process "WhatsApp" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process "WhatsApp.Root" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process "Telegram" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process "max" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process "max-service" -ErrorAction SilentlyContinue | Stop-Process -Force

# ============================================
# Офис и продуктивность
# ============================================
Get-Process "Notion" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process "TickTick" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process "DeepL" -ErrorAction SilentlyContinue | Stop-Process -Force

# ============================================
# Синхронизация и загрузки
# ============================================
Get-Process "YandexDisk2" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process "qbittorrent" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process "fdm" -ErrorAction SilentlyContinue | Stop-Process -Force

# ============================================
# Работа
# ============================================
Get-Process "figma_agent" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process "Bitrix24" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process "vkworkspace" -ErrorAction SilentlyContinue | Stop-Process -Force

# ============================================
# VPN и сетевые сервисы
# ============================================
Get-Process "agent_ovpnconnect" -ErrorAction SilentlyContinue | Stop-Process -Force

# ============================================
# Системные службы и утилиты
# ============================================
Get-Process "RuntimeBroker" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process "backgroundTaskHost" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process "helperservice" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process "PureText" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process "LogiTune" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process "ScreenshotReader" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process "PAD.Console.Host" -ErrorAction SilentlyContinue | Stop-Process -Force

# ============================================
# AI и вспомогательные
# ============================================
Get-Process "ChatGPT" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process "BreakTimer" -ErrorAction SilentlyContinue | Stop-Process -Force

# ============================================
# Запуск приложений
# ============================================
Start-Process "ms-settings:easeofaccess-audio"
Start-Process "C:\Program Files (x86)\MusicBee\MusicBee.exe"
# Wait until MusicBee has a visible main window (up to 15 seconds).
# Get-Process is used instead of -Wait because MusicBee stays open.
$musicBeeWindowReady = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    $musicBeeWindowReady = [bool](Get-Process -Name "MusicBee" -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1)
    if ($musicBeeWindowReady) { break }
    Start-Sleep -Milliseconds 500
}
# Let the window finish positioning before restoring the magnified region.
Start-Sleep -Seconds 2
$magnifier = 'C:\Users\Andrey\AppData\Local\OnTopReplicaPlus\OnTopReplicaPlus.exe'
if (Test-Path -LiteralPath $magnifier -PathType Leaf) {
    Start-Process -FilePath $magnifier
} else {
    Write-Warning "OnTopReplicaPlus не найден: $magnifier"
}
Start-Process "C:\Program Files\TightVNC\tvnserver.exe"
Start-Process -FilePath (Join-Path $PSScriptRoot "Связанные скрипты\Панель громкости.ahk")
$ipv4Bat = Join-Path $PSScriptRoot 'Связанные скрипты\Показать IPv4.bat'
if (Test-Path -LiteralPath $ipv4Bat) {
    Start-Process -FilePath $env:ComSpec -ArgumentList ('/d /c ""{0}""' -f $ipv4Bat)
}
Start-Process "anytype://object?objectId=bafyreiek44nqfypu3es7uydlr7bpc7aitm3welxl3u3ia7tl6rsxyffgk4&spaceId=bafyreiao7lfc742foxkwd65zkudl7blk7s7s4mvsq6trwtihyyxgkktury.3vagjf2fgfoqc"