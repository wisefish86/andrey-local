#Requires AutoHotkey v2.0
#SingleInstance Force
SetTitleMatchMode 3
CoordMode "Mouse", "Client"

bupShortcut := "D:\YandexDisk\Проекты\Работа в Компас\- Задачи (рабочие)\- Избранные задачи\- BUP.lnk"
windowTitle := "BUP"
surname := "Шевцов"

if !FileExist(bupShortcut) {
    MsgBox "Не найден ярлык BUP:`n" bupShortcut, "Отчёт в BUP", "Iconx"
    ExitApp
}

try {
    Run '"' bupShortcut '"'
    hwnd := WinWait(windowTitle, , 15)
    if !hwnd
        throw Error("Окно BUP не появилось за 15 секунд.")
    WinActivate "ahk_id " hwnd
    if !WinWaitActive("ahk_id " hwnd, , 5)
        throw Error("Не удалось активировать окно BUP.")

    ; Координаты относительно клиентской области окна (по скриншоту формы 310x104, без заголовка).
    ; Не используем Tab, буфер обмена и ControlSetText.
    WinGetClientPos(, , &width, &height, "ahk_id " hwnd)
    if width < 280 || height < 65
        throw Error("Размер окна отличается от ожидаемого. Ввод остановлен.")

    Click 135, 22
    Sleep 200
    SendText surname
    Sleep 200

    Click 100, 50
    Sleep 200
    SendText surname
    Sleep 250

    ; Enter отправляется только в активное окно BUP.
    if !WinActive("ahk_id " hwnd)
        throw Error("Окно BUP потеряло фокус. Enter не отправлен.")
    Send "{Enter}"
} catch as err {
    MsgBox "Не удалось выполнить первый этап:`n" err.Message, "Отчёт в BUP", "Iconx"
}
