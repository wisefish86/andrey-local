#Requires AutoHotkey v2.0
#SingleInstance Force
SetTitleMatchMode 3
CoordMode "Mouse", "Client"

bupShortcut := "D:\YandexDisk\Ресурсы\Софт\Работа и управление задачами\Компас\BUP.exe"
windowTitle := "BUP"
surname := "Шевцов"

if !FileExist(bupShortcut) {
    MsgBox "Не найден BUP.exe:`n" bupShortcut, "Отчёт в BUP", "Iconx"
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

    ; После входа ждём основное окно BUP (в заголовке появляется имя).
    ; Иконка пользователя находится в клиентской области у левого верхнего края.
    mainWindow := 0
    deadline := A_TickCount + 15000
    while (A_TickCount < deadline) {
        for candidate in WinGetList() {
            if !WinExist("ahk_id " candidate)
                continue
            title := WinGetTitle("ahk_id " candidate)
            if (InStr(title, "BUP - ") = 1) {
                mainWindow := candidate
                break
            }
        }
        if mainWindow
            break
        Sleep 250
    }
    if !mainWindow
        throw Error("Основное окно BUP не найдено после входа. Клик не выполнен.")

    WinActivate "ahk_id " mainWindow
    if !WinWaitActive("ahk_id " mainWindow, , 5)
        throw Error("Не удалось активировать главное окно BUP.")

    ; На предоставленном скриншоте иконка расположена примерно в (8, 17)
    ; относительно клиентской области главного окна.
    Click 9, 17

    ; Ожидаем появления списка «Сотрудники» в основном MDI-окне.
    ; На предоставленном скриншоте единственная строка — ID 11,
    ; Шевцов Андрей Алексеевич (примерно x=110, y=143 от клиентской области).
    Sleep 900
    if !WinActive("ahk_id " mainWindow)
        throw Error("Главное окно BUP потеряло фокус. Сотрудник не выбран.")
    Click 110, 143, 2
    ; Далее пользователь продолжает работу вручную.

} catch as err {
    MsgBox "Не удалось выполнить первый этап:`n" err.Message, "Отчёт в BUP", "Iconx"
}
