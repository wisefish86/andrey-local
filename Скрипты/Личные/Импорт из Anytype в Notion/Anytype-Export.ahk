#Requires AutoHotkey v2.0
#SingleInstance Force
; Anytype UI export with configurable completion-toast and checkbox clicks.
; The checkbox is toggled, not set idempotently: start with it unchecked.
SetTitleMatchMode 2
CoordMode "Mouse", "Client"
global config := A_ScriptDir "\\Anytype-Export.local.ini"
global running := false

IsAnytype() {
    return WinActive("ahk_exe Anytype.exe")
}

#HotIf IsAnytype()
^+1::CapturePoint("Menu")
^+2::CapturePoint("ExportMenu")
^+3::CapturePoint("ExportConfirm")
^+5::CapturePoint("NotionCheckbox")
^+6::CapturePoint("ExportToastClose")
^e::ExportCurrent()
#HotIf

CapturePoint(name) {
    global config
    MouseGetPos &x, &y
    IniWrite x, config, "Clicks", name "X"
    IniWrite y, config, "Clicks", name "Y"
    ToolTip name ": " x ", " y
    SetTimer () => ToolTip(), -1500
}

ReadPoint(name) {
    global config
    x := IniRead(config, "Clicks", name "X", "")
    y := IniRead(config, "Clicks", name "Y", "")
    if (x = "" || y = "")
        throw Error("Не настроена точка " name ". Используй Ctrl+Shift+1/2/3/5/6.")
    return [Integer(x), Integer(y)]
}

ExportCurrent() {
    global running
    if running
        return
    running := true
    try {
        hwnd := WinGetID("A")
        p1 := ReadPoint("Menu")
        p2 := ReadPoint("ExportMenu")
        p3 := ReadPoint("ExportConfirm")
        ; Remember existing Explorer windows to avoid closing the user's work.
        before := Map()
        for id in WinGetList("ahk_class CabinetWClass")
            before[id] := true
        Click p1[1], p1[2]
        Sleep 400
        Click p2[1], p2[2]
        Sleep 550
        Click p3[1], p3[2]
        ; Native Windows folder picker: identify by title/class, not coordinates.
        picker := 0
        Loop 30 {
            for id in WinGetList("ahk_class #32770") {
                title := WinGetTitle("ahk_id " id)
                if (title = "Выбор папки" || title = "Select Folder" || title = "Browse For Folder") {
                    picker := id
                    break
                }
            }
            if picker
                break
            Sleep 200
        }
        if !picker
            throw Error("Окно выбора папки не появилось.")
        if !WinExist("ahk_id " picker)
            throw Error("Окно выбора папки закрылось до подтверждения.")
        WinActivate "ahk_id " picker
        if !WinWaitActive("ahk_id " picker, , 3)
            throw Error("Не удалось активировать выбор папки.")
        Send "{Enter}"
        if WinExist("ahk_id " picker) && !WinWaitClose("ahk_id " picker, , 10)
            throw Error("Выбор папки не закрылся. Проверь диалог вручную.")
        ; Anytype can reuse an existing Explorer window. Never close user's
        ; pre-existing windows: minimize a reused foreground window instead.
        Loop 30 {
            Sleep 250
            active := WinGetID("A")
            if (active && WinExist("ahk_id " active) && WinGetClass("ahk_id " active) = "CabinetWClass") {
                if before.Has(active)
                    WinMinimize "ahk_id " active
                else
                    WinClose "ahk_id " active
                break
            }
            ; A newly created Explorer window may open without focus.
            newExplorer := 0
            for id in WinGetList("ahk_class CabinetWClass") {
                if !before.Has(id) {
                    newExplorer := id
                    break
                }
            }
            if newExplorer {
                try WinClose "ahk_id " newExplorer
                break
            }
        }
        if WinExist("ahk_id " hwnd) {
            WinActivate "ahk_id " hwnd
            try WinWaitActive "ahk_id " hwnd, , 3
        }
        ; Close the export-completed toast before toggling the checkbox.
        ; Toast coordinates are relative to the Anytype client window.
        pToast := ReadPoint("ExportToastClose")
        if !WinActive("ahk_id " hwnd)
            throw Error("Anytype не активно; уведомление не закрыто.")
        Sleep 400
        Click pToast[1], pToast[2]
        Sleep 250
        ; Coordinate-based toggle: only use when the checkbox is initially OFF.
        ; This UI method cannot reliably read its current checked state.
        pCheck := ReadPoint("NotionCheckbox")
        if !WinActive("ahk_id " hwnd)
            throw Error("Anytype не активно; галочка не изменена.")
        Click pCheck[1], pCheck[2]
        ToolTip "В Notion: переключено (проверь состояние галочки)"
        SetTimer () => ToolTip(), -4000
    } catch as e {
        MsgBox e.Message " (строка " e.Line ")", "Anytype Export", "Icon!"
    } finally {
        running := false
    }
}
