#Requires AutoHotkey v2.0
#SingleInstance Force
SetTitleMatchMode 3

; Этап 1: открыть BUP и заполнить два поля фамилией.
bupShortcut := "D:\YandexDisk\Проекты\Работа в Компас\- Задачи (рабочие)\- Избранные задачи\- BUP.lnk"
windowTitle := "BUP"
surname := "Шевцов"

if !FileExist(bupShortcut) {
    MsgBox "Не найден ярлык BUP:`n" bupShortcut, "Отчёт в BUP", "Iconx"
    ExitApp
}

try {
    Run '"' bupShortcut '"'
    if !WinWait(windowTitle, , 15) {
        throw Error("Окно BUP не появилось за 15 секунд.")
    }

    WinActivate windowTitle
    if !WinWaitActive(windowTitle, , 5) {
        throw Error("Не удалось активировать окно BUP.")
    }

    ; Работаем только с полями ввода окна BUP, без кликов по координатам.
    firstEdit := ControlGetHwnd("Edit1", windowTitle)
    secondEdit := ControlGetHwnd("Edit2", windowTitle)
    if (!firstEdit || !secondEdit) {
        throw Error("Не найдены оба стандартных поля Edit1 и Edit2.")
    }

    ControlSetText surname, "Edit1", windowTitle
    ControlSetText surname, "Edit2", windowTitle

    ; Защита от подтверждения неверно заполненной формы.
    if (ControlGetText("Edit1", windowTitle) != surname
        || ControlGetText("Edit2", windowTitle) != surname) {
        throw Error("Значение одного из полей отличается от ожидаемого.")
    }

    ControlFocus "Edit2", windowTitle
    Send "{Enter}"
} catch as err {
    MsgBox "Не удалось выполнить первый этап:`n" err.Message
        . "`n`nНичего дополнительно не нажимай в BUP до проверки.", "Отчёт в BUP", "Iconx"
}
