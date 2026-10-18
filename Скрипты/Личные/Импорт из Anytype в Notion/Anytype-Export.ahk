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
        ; Export may take time. New Explorer is a hint, not proof of ZIP validity.
        found := false
        Loop 30 {
            Sleep 500
            for id in WinGetList("ahk_class CabinetWClass") {
                if !before.Has(id) {
                    ; Close only the newly opened window.
                    try WinClose("ahk_id " id)
                    found := true
                    break
                }
            }
            if found
                break
        }
        if WinExist("ahk_id " hwnd)
            WinActivate "ahk_id " hwnd
        if found
            MsgBox "Проводник закрыт. Проверь ZIP экспорта. Свойство «В Notion» пока не менялось.", "Anytype Export", "Iconi"
        else
            MsgBox "Не обнаружено новое окно Проводника. Проверь результат экспорта вручную. Свойство не менялось.", "Anytype Export", "Icon!"
    } catch as e {
        MsgBox e.Message, "Anytype Export", "Icon!"
    } finally {
        running := false
    }
}
