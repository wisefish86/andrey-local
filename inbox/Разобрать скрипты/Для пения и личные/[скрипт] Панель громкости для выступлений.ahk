#Requires AutoHotkey v2.0

; ----- НАСТРОЙКИ ДИЗАЙНА -----
BG_COLOR := 0x2F2F2F              ; графитовый фон окна
BTN_COLOR := "Silver"             ; светлый фон кнопок (серебристый)
FONT_SIZE := 20                    ; размер символов +/-
FONT_NAME := "Segoe UI"
STEP := 2                          ; шаг громкости 2%

; ----- СОЗДАНИЕ ОКНА -----
MyGui := Gui("+AlwaysOnTop -Caption +Border +ToolWindow +E0x08000000", "Volume Control")
MyGui.BackColor := BG_COLOR
MyGui.SetFont("s" FONT_SIZE " bold cWhite", FONT_NAME)  ; белый текст по умолчанию

; ----- КНОПКИ С ФОНОМ И РАМКОЙ -----
btnMinus := MyGui.Add("Text", "x5 y5 w45 h45 Center +Border 0x200", "-")
btnMinus.BackColor := BTN_COLOR

btnPlus := MyGui.Add("Text", "x150 y5 w45 h45 Center +Border 0x200", "+")
btnPlus.BackColor := BTN_COLOR

; Индикатор громкости (без рамки, фон как у окна, текст белый)
txtVolume := MyGui.Add("Text", "x55 y5 w90 h45 Center 0x200", "50%")
txtVolume.SetFont("s12 bold cWhite", FONT_NAME)
txtVolume.BackColor := BG_COLOR

; ----- ОБРАБОТЧИКИ КЛИКОВ -----
btnMinus.OnEvent("Click", (*) => ChangeVolume(-STEP))
btnPlus.OnEvent("Click",  (*) => ChangeVolume(STEP))

ChangeVolume(delta) {
    current := SoundGetVolume()
    newVol  := Min(100, Max(0, current + delta))
    SoundSetVolume(newVol)
}

; ----- ТАЙМЕР СИНХРОНИЗАЦИИ -----
UpdateVolumeDisplay() {
    try {
        current := SoundGetVolume()
        txtVolume.Text := Round(current) "%"
    } catch {
        txtVolume.Text := "N/A"
    }
}
SetTimer(UpdateVolumeDisplay, 100)

; ----- ПЕРЕТАСКИВАНИЕ ОКНА -----
WM_NCLBUTTONDOWN := 0xA1
HTCAPTION := 2
OnMessage(0x201, (wParam, lParam, msg, hwnd) => DllCall("PostMessage", "Ptr", hwnd, "UInt", WM_NCLBUTTONDOWN, "Ptr", HTCAPTION, "Ptr", 0))

; ----- КОНТЕКСТНОЕ МЕНЮ -----
ctxMenu := Menu()
ctxMenu.Add("Закрыть", (*) => ExitApp())

ShowContextMenu(wParam, lParam, msg, hwnd) {
    if (hwnd != MyGui.Hwnd)
        return
    x := lParam & 0xFFFF
    y := lParam >> 16
    ctxMenu.Show(x, y)
}
OnMessage(0x7B, ShowContextMenu)

; ----- ПОКАЗАТЬ ОКНО -----
MyGui.Show("w200 h55")
UpdateVolumeDisplay()