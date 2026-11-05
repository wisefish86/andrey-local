VERSION 5.00
Begin {C62A69F0-16DC-11CE-9E98-00AA00574A4F} frmFontInspector
   Caption         =   "Font Inspector | CorelDRAW"
   ClientHeight    =   6480
   ClientLeft      =   120
   ClientTop      =   465
   ClientWidth     =   8280
   OleObjectBlob   =   "frmFontInspector.frx":0000
   StartUpPosition =   1
End
Attribute VB_Name = "frmFontInspector"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Option Explicit

Private WithEvents btnRefresh As MSForms.CommandButton
Private WithEvents btnCapture As MSForms.CommandButton
Private WithEvents btnStop As MSForms.CommandButton
Private WithEvents optDocument As MSForms.OptionButton
Private WithEvents optSelection As MSForms.OptionButton
Private WithEvents btnJump As MSForms.CommandButton
Private WithEvents btnClose As MSForms.CommandButton
Private WithEvents lstFonts As MSForms.ListBox
Private WithEvents lstMatches As MSForms.ListBox
Private lblInfo As MSForms.Label
Private lblItem As MSForms.Label
Private ready As Boolean
Private didAutoScan As Boolean
Private busy As Boolean

Private Sub UserForm_Initialize()
    Me.Caption = "Инспектор шрифтов | CorelDRAW"
    Me.BackColor = RGB(247, 249, 252)
    Me.Width = 565: Me.Height = 492
    LabelAt "title", "Инспектор шрифтов", 16, 12, 425, 23, 14, True
    LabelAt "hint", "Проверка шрифтов в документе или выделенном стенде", 16, 38, 525, 19, 9, False
    Set btnRefresh = ButtonAt("btnRefresh", "Проверить", 449, 12, 96, 26)
    Set optDocument = OptionAt("optDocument", "Весь документ", 16, 65, 150, 19)
    Set optSelection = OptionAt("optSelection", "Только выделенное", 172, 65, 172, 19)
    Set btnCapture = ButtonAt("btnCapture", "Взять выделение", 347, 62, 198, 25)
    optSelection.Value = InspectorSelectionMode
    optDocument.Value = Not InspectorSelectionMode
    LabelAt "fonts", "Шрифты документа", 16, 97, 240, 18, 10, True
    LabelAt "objects", "Найденные фрагменты", 274, 97, 260, 18, 10, True
    Set lstFonts = Me.Controls.Add("Forms.ListBox.1", "lstFonts", True)
    lstFonts.Left = 16: lstFonts.Top = 119: lstFonts.Width = 243: lstFonts.Height = 253
    lstFonts.Font.Name = "Segoe UI": lstFonts.Font.Size = 9: lstFonts.IntegralHeight = False
    Set lstMatches = Me.Controls.Add("Forms.ListBox.1", "lstMatches", True)
    lstMatches.Left = 274: lstMatches.Top = 119: lstMatches.Width = 271: lstMatches.Height = 253
    lstMatches.Font.Name = "Segoe UI": lstMatches.Font.Size = 9: lstMatches.IntegralHeight = False
    lstMatches.ColumnCount = 2: lstMatches.ColumnWidths = "245 pt;0 pt"
    Set lblInfo = LabelAt("lblInfo", "Готов к проверке.", 16, 378, 529, 20, 9, False)
    Set lblItem = LabelAt("lblItem", "", 16, 403, 349, 18, 9, False)
    Set btnJump = ButtonAt("btnJump", "Перейти к объекту", 376, 402, 169, 27)
    btnJump.Enabled = False
    Set btnStop = ButtonAt("btnStop", "Остановить", 124, 435, 110, 25)
    btnStop.Enabled = False
    Set btnClose = ButtonAt("btnClose", "Закрыть", 16, 435, 98, 25)
    ready = True
End Sub

' Never run a potentially long scan in Initialize or Activate:
' modeless Show must return before the user starts analysis explicitly.
Private Sub UserForm_Activate()
    If didAutoScan Or Not ready Then Exit Sub
    didAutoScan = True
    lblInfo.Caption = "Окно готово. Нажмите «Проверить», чтобы начать поиск."
End Sub

Private Function LabelAt(ByVal key As String, ByVal s As String, ByVal x As Single, _
                         ByVal y As Single, ByVal w As Single, ByVal h As Single, _
                         ByVal sz As Single, ByVal strong As Boolean) As MSForms.Label
    Dim v As MSForms.Label
    Set v = Me.Controls.Add("Forms.Label.1", key, True)
    v.Caption = s: v.Left = x: v.Top = y: v.Width = w: v.Height = h
    v.Font.Name = "Segoe UI": v.Font.Size = sz: v.Font.Bold = strong
    v.BackStyle = fmBackStyleTransparent
    v.ForeColor = RGB(37, 49, 69)
    Set LabelAt = v
End Function

Private Function ButtonAt(ByVal key As String, ByVal s As String, ByVal x As Single, _
                           ByVal y As Single, ByVal w As Single, ByVal h As Single) As MSForms.CommandButton
    Dim v As MSForms.CommandButton
    Set v = Me.Controls.Add("Forms.CommandButton.1", key, True)
    v.Caption = s: v.Left = x: v.Top = y: v.Width = w: v.Height = h
    v.Font.Name = "Segoe UI": v.Font.Size = 9
    v.BackColor = RGB(229, 235, 245): v.ForeColor = RGB(33, 53, 86)
    Set ButtonAt = v
End Function

Private Function OptionAt(ByVal key As String, ByVal s As String, ByVal x As Single, _
                           ByVal y As Single, ByVal w As Single, ByVal h As Single) As MSForms.OptionButton
    Dim v As MSForms.OptionButton
    Set v = Me.Controls.Add("Forms.OptionButton.1", key, True)
    v.Caption = s: v.Left = x: v.Top = y: v.Width = w: v.Height = h
    v.Font.Name = "Segoe UI": v.Font.Size = 9
    v.BackStyle = fmBackStyleTransparent
    Set OptionAt = v
End Function

Private Sub RefreshResults()
    Dim more As Boolean, steps As Long
    If busy Or Not ready Then Exit Sub
    If Documents.Count = 0 Then lblInfo.Caption = "Нет открытого документа.": Exit Sub
    On Error GoTo ScanError
    busy = True
    InspectorRunning = True
    btnStop.Enabled = True: btnRefresh.Enabled = False: btnCapture.Enabled = False
    optDocument.Enabled = False: optSelection.Enabled = False
    btnJump.Enabled = False
    lstFonts.Clear: lstMatches.Clear
    lblInfo.Caption = "Составляю список объектов..."
    Me.Repaint: DoEvents
    InspectorPrepareScan
    If InspectorCancelled Then GoTo Finished
    lblInfo.Caption = "Найдено текстовых объектов: " & InspectorTotalObjects()
    Me.Repaint: DoEvents
    Do
        more = InspectorScanStep(250)
        steps = steps + 1
        If (steps Mod 4) = 0 Or Not more Then
            lblInfo.Caption = "Проверено " & InspectorScannedObjects() & " из " & InspectorTotalObjects() & _
                              " объектов; найдено " & InspectorItems.Count & " фрагментов."
            Me.Repaint
        End If
        DoEvents
        If InspectorCancelled Then Exit Do
    Loop While more
Finished:
    InspectorRunning = False
    busy = False
    btnStop.Enabled = False: btnRefresh.Enabled = True: btnCapture.Enabled = True
    optDocument.Enabled = True: optSelection.Enabled = True
    PopulateResults
    If InspectorCancelled Then
        lblInfo.Caption = "Остановлено: " & InspectorScannedObjects() & " / " & InspectorTotalObjects() & " объектов; результат неполный."
    Else
        lblInfo.Caption = "Проверено " & InspectorScannedObjects() & " / " & InspectorTotalObjects() & _
                          " объектов; предупреждений: " & InspectorWarnings
    End If
    Exit Sub
ScanError:
    InspectorCancelled = True
    InspectorRunning = False: busy = False
    btnStop.Enabled = False: btnRefresh.Enabled = True: btnCapture.Enabled = True
    optDocument.Enabled = True: optSelection.Enabled = True
    lblInfo.Caption = "Ошибка поиска: " & Err.Description
End Sub

Private Sub PopulateResults()
    Dim counts As Object, row As Object, keys As Variant
    Dim i As Long, j As Long, swap As Variant, f As String
    Set counts = CreateObject("Scripting.Dictionary")
    counts.CompareMode = vbTextCompare
    For Each row In InspectorItems
        f = CStr(row.Item("font"))
        If counts.Exists(f) Then
            counts(f) = counts(f) + 1
        Else
            counts.Add f, 1
        End If
    Next row
    lstFonts.Clear: lstMatches.Clear
    btnJump.Enabled = False
    lblItem.Caption = counts.Count & " шрифтов / " & InspectorItems.Count & " фрагментов"
    If counts.Count = 0 Then Exit Sub
    keys = counts.Keys
    If counts.Count > 1 Then
        For i = 0 To UBound(keys) - 1
            For j = i + 1 To UBound(keys)
                If StrComp(CStr(keys(i)), CStr(keys(j)), vbTextCompare) > 0 Then
                    swap = keys(i): keys(i) = keys(j): keys(j) = swap
                End If
            Next j
        Next i
    End If
    For i = 0 To UBound(keys)
        lstFonts.AddItem CStr(keys(i)) & "  (" & counts(keys(i)) & ")"
    Next i
    lstFonts.ListIndex = 0
End Sub

Private Sub lstFonts_Change()
    Dim i As Long, row As Object, s As String, p As Long
    If busy Or lstFonts.ListIndex < 0 Then Exit Sub
    s = lstFonts.List(lstFonts.ListIndex, 0)
    p = InStrRev(s, "  (")
    If p > 0 Then s = Left$(s, p - 1)
    lstMatches.Clear
    For i = 1 To InspectorItems.Count
        Set row = InspectorItems(i)
        If StrComp(CStr(row.Item("font")), s, vbTextCompare) = 0 Then
            lstMatches.AddItem "стр." & row.Item("page") & "  " & row.Item("preview")
            lstMatches.List(lstMatches.ListCount - 1, 1) = CStr(i)
        End If
    Next i
    btnJump.Enabled = False
    lblItem.Caption = "Фрагментов: " & lstMatches.ListCount
End Sub

Private Sub lstMatches_Change()
    btnJump.Enabled = (Not busy And lstMatches.ListIndex >= 0)
End Sub

Private Sub lstMatches_DblClick(ByVal Cancel As MSForms.ReturnBoolean)
    JumpToSelected
End Sub

Private Sub JumpToSelected()
    If busy Or lstMatches.ListIndex < 0 Then Exit Sub
    If InspectorGoTo(CLng(lstMatches.List(lstMatches.ListIndex, 1))) Then
        lblItem.Caption = "Объект выделен. Исправьте шрифт и нажмите «Проверить»."
    End If
End Sub

Private Sub btnJump_Click()
    JumpToSelected
End Sub

Private Sub btnRefresh_Click()
    RefreshResults
End Sub

Private Sub btnStop_Click()
    InspectorCancelled = True
    lblInfo.Caption = "Останавливаю..."
End Sub

Private Sub btnCapture_Click()
    If busy Then Exit Sub
    If Not InspectorCaptureSelection() Then
        lblInfo.Caption = "Выделите стенд в CorelDRAW и повторите."
        Exit Sub
    End If
    InspectorSelectionMode = True
    optSelection.Value = True
    lblInfo.Caption = "Выделение сохранено. Нажмите «Проверить»."
End Sub

Private Sub optDocument_Click()
    If Not ready Or busy Then Exit Sub
    InspectorSelectionMode = False
    lblInfo.Caption = "Режим: весь документ. Нажмите «Проверить»."
End Sub

Private Sub optSelection_Click()
    If Not ready Or busy Then Exit Sub
    InspectorSelectionMode = True
    lblInfo.Caption = "Режим: выделенный стенд. Нажмите «Взять выделение» или «Проверить»."
End Sub

Private Sub btnClose_Click()
    If busy Then
        InspectorCancelled = True
        lblInfo.Caption = "Останавливаю; закройте форму после остановки."
    Else
        Unload Me
    End If
End Sub

Private Sub UserForm_QueryClose(Cancel As Integer, CloseMode As Integer)
    If busy Then
        Cancel = True
        InspectorCancelled = True
    End If
End Sub
