#Requires AutoHotkey v2.0

SwitchToRussian() {
    ; Русская раскладка 0419
    hkl := DllCall("LoadKeyboardLayout", "Str", "00000419", "UInt", 1, "Ptr")
    PostMessage(0x50, 0, hkl, , "A")
}

#HotIf WinActive("ahk_exe Flow.Launcher.exe")

:O:b::
{
    SwitchToRussian()
    SendText("и ")
}

#HotIf