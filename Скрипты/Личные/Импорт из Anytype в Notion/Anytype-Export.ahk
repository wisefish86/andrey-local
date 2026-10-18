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
^+4::CapturePoint("CopyLink")
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
        pLink := ReadPoint("CopyLink")
        savedClipboard := ClipboardAll()
        A_Clipboard := ""
        Click p1[1], p1[2]
        Sleep 350
        Click pLink[1], pLink[2]
        if !ClipWait(3) {
            A_Clipboard := savedClipboard
            throw Error("Copy Link did not copy a URL.")
        }
        objectUrl := A_Clipboard
        A_Clipboard := savedClipboard
        if !RegExMatch(objectUrl, "^https://object[.]any[.]coop/[^?]+[?]spaceId=")
            throw Error("Unexpected object link; checkbox unchanged.")
        Sleep 250
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
        helper := A_ScriptDir "\Anytype-MarkNotion.ps1"
        if !FileExist(helper)
            throw Error("Missing Anytype-MarkNotion.ps1")
        command := 'powershell.exe -NoProfile -File "' helper '" -ObjectUrl "' objectUrl '"'
        if RunWait(command, , "Hide") {
            detailFile := A_Temp "\Anytype-Export-error.txt"
            detail := FileExist(detailFile) ? FileRead(detailFile, "UTF-8") : "PowerShell failed without details."
            if FileExist(detailFile)
                FileDelete detailFile
            throw Error("Anytype API: " detail)
        }
        ToolTip "В Notion: отмечено через API"
        SetTimer () => ToolTip(), -4000
    } catch as e {
        MsgBox e.Message " (строка " e.Line ")", "Anytype Export", "Icon!"
    } finally {
        running := false
    }
}
