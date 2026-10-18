#Requires AutoHotkey v2.0
#SingleInstance Force
; Anytype → Notion: preliminary safe UI exporter.
; Does not read or expose the API key; property update will be added after
; reliable mapping of the active Anytype object to its API object ID.
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
        throw Error("Не настроена точка " name ". Используй Ctrl+Shift+1/2/3.")
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
        WinActivate "ahk_id " picker
        if !WinWaitActive("ahk_id " picker, , 3)
            throw Error("Не удалось активировать выбор папки.")
        Send "{Enter}"
        if !WinWaitClose("ahk_id " picker, , 10)
            throw Error("Выбор папки не закрылся. Проверь диалог вручную.")
        ; Explorer might not open at all; this is normal for some Anytype versions.
        ; Close only a newly opened Explorer window, if any.
        Loop 10 {
            Sleep 350
            for id in WinGetList("ahk_class CabinetWClass") {
                if !before.Has(id) {
                    try WinClose "ahk_id " id
                    break
                }
            }
        }
        if WinExist("ahk_id " hwnd)
            WinActivate "ahk_id " hwnd
        ; Closing the picker is not proof that the ZIP is complete.
        ; Never mark the object as imported without a verified export.
        ToolTip "Диалог экспорта закрыт. Проверь ZIP. Отметка «В Notion» пока не изменена."
        SetTimer () => ToolTip(), -5000
    } catch as e {
        MsgBox e.Message, "Anytype Export", "Icon!"
    } finally {
        running := false
    }
}
