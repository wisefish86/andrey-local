VERSION 5.00
Begin {C62A69F0-16DC-11CE-9E98-00AA00574A4F} frmCreateFromCSV
   Caption         =   "CSV | CorelDRAW"
   ClientHeight    =   4800
   ClientLeft      =   120
   ClientTop       =   465
   ClientWidth     =   6600
   OleObjectBlob   =   "frmCreateFromCSV.frx":0000
   StartUpPosition =   1  'CenterOwner
End
Attribute VB_Name = "frmCreateFromCSV"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Option Explicit
Private WithEvents cmdBrowse As MSForms.CommandButton
Private WithEvents cmdTemplate As MSForms.CommandButton
Private WithEvents cmdRun As MSForms.CommandButton
Private WithEvents cmdClose As MSForms.CommandButton
Private txtCSV As MSForms.TextBox
Private txtCols As MSForms.TextBox
Private txtX As MSForms.TextBox
Private txtY As MSForms.TextBox

Private Sub UserForm_Initialize()
    On Error GoTo InitError
    Me.Caption = "CSV Layout  |  CorelDRAW"
    Me.BackColor = RGB(247, 249, 252)

    AddLabel "lblTitle", RuText("1057,1086,1079,1076,1072,1085,1080,1077,32,1086,1073,1098,1077,1082,1090,1086,1074,32,1080,1079,32,67,83,86"), 16, 10, 366, 25, 13, True, RGB(27, 40, 58)
    AddLabel "lblSubtitle", RuText("1047,1072,1087,1086,1083,1085,1077,1085,1080,1077,32,1090,1077,1082,1089,1090,1086,1074,1099,1093,32,1087,1086,1083,1077,1081,32,1075,1088,1091,1087,1087,1099"), 16, 36, 366, 17, 9, False, RGB(101, 113, 131)

    AddLabel "lblSectionCSV", RuText("48,49,32,32,1044,1040,1053,1053,1067,1045"), 16, 60, 360, 18, 9, True, RGB(53, 91, 153)
    AddLabel "lblFile", RuText("1060,1072,1081,1083,32,67,83,86"), 16, 80, 360, 18, 9, False, RGB(58, 69, 86)
    Set txtCSV = AddText("txtCSV", 16, 101, 273, 23, "")
    Set cmdBrowse = AddButton("cmdBrowse", RuText("1054,1073,1079,1086,1088,46,46,46"), 297, 101, 89, 23, False)
    Set cmdTemplate = AddButton("cmdTemplate", RuText("1057,1086,1079,1076,1072,1090,1100,32,67,83,86,32,1087,1086,32,1074,1099,1073,1088,1072,1085,1085,1086,1081,32,1075,1088,1091,1087,1087,1077"), 16, 133, 370, 26, False)

    AddLabel "lblSectionLayout", RuText("48,50,32,32,1056,1040,1047,1052,1045,1065,1045,1053,1048,1045"), 16, 172, 360, 18, 9, True, RGB(53, 91, 153)
    AddLabel "lblCols", RuText("1050,1086,1083,1086,1085,1082,1080"), 16, 192, 105, 18, 9, False, RGB(58, 69, 86)
    AddLabel "lblX", RuText("1054,1090,1089,1090,1091,1087,32,88,44,32,1084,1084"), 143, 192, 105, 18, 9, False, RGB(58, 69, 86)
    AddLabel "lblY", RuText("1054,1090,1089,1090,1091,1087,32,89,44,32,1084,1084"), 270, 192, 115, 18, 9, False, RGB(58, 69, 86)
    Set txtCols = AddText("txtCols", 16, 211, 105, 23, "4")
    Set txtX = AddText("txtX", 143, 211, 105, 23, "10")
    Set txtY = AddText("txtY", 270, 211, 116, 23, "10")

    Set cmdRun = AddButton("cmdRun", RuText("1057,1086,1079,1076,1072,1090,1100,32,1086,1073,1098,1077,1082,1090,1099"), 16, 247, 239, 28, True)
    Set cmdClose = AddButton("cmdClose", RuText("1047,1072,1082,1088,1099,1090,1100"), 267, 247, 119, 28, False)

    FitFormToControls 12, 12
    Exit Sub
InitError:
    MsgBox "Form initialization failed: " & Err.Description, vbExclamation
End Sub

Private Sub FitFormToControls(ByVal padX As Single, ByVal padY As Single)
    Dim c As MSForms.Control
    Dim maxRight As Single, maxBottom As Single
    Dim borderW As Single, borderH As Single
    borderW = Me.Width - Me.InsideWidth
    borderH = Me.Height - Me.InsideHeight
    For Each c In Me.Controls
        If c.Left + c.Width > maxRight Then maxRight = c.Left + c.Width
        If c.Top + c.Height > maxBottom Then maxBottom = c.Top + c.Height
    Next c
    Me.Width = maxRight + padX + borderW
    Me.Height = maxBottom + padY + borderH
End Sub

Private Sub AddLabel(ByVal n As String, ByVal t As String, ByVal x As Single, ByVal y As Single, ByVal w As Single, ByVal h As Single, ByVal fontSize As Single, ByVal emphasized As Boolean, ByVal textColor As Long)
    Dim c As MSForms.Label
    Set c = Me.Controls.Add("Forms.Label.1", n, True)
    c.Caption = t
    c.Left = x: c.Top = y: c.Width = w: c.Height = h
    c.BackStyle = fmBackStyleTransparent
    c.ForeColor = textColor
    c.Font.Name = "Segoe UI"
    c.Font.Size = fontSize
    c.Font.Bold = emphasized
End Sub

Private Function AddText(ByVal n As String, ByVal x As Single, ByVal y As Single, ByVal w As Single, ByVal h As Single, ByVal v As String) As MSForms.TextBox
    Dim c As MSForms.TextBox
    Set c = Me.Controls.Add("Forms.TextBox.1", n, True)
    c.Left = x: c.Top = y: c.Width = w: c.Height = h
    c.Text = v
    c.TextAlign = fmTextAlignCenter
    c.Font.Name = "Segoe UI"
    c.Font.Size = 10
    c.BackColor = RGB(255, 255, 255)
    c.ForeColor = RGB(27, 40, 58)
    c.BorderStyle = fmBorderStyleSingle
    c.BorderColor = RGB(205, 215, 229)
    Set AddText = c
End Function

Private Function AddButton(ByVal n As String, ByVal t As String, ByVal x As Single, ByVal y As Single, ByVal w As Single, ByVal h As Single, ByVal primary As Boolean) As MSForms.CommandButton
    Dim c As MSForms.CommandButton
    Set c = Me.Controls.Add("Forms.CommandButton.1", n, True)
    c.Caption = t
    c.Left = x: c.Top = y: c.Width = w: c.Height = h
    c.Font.Name = "Segoe UI"
    c.Font.Size = 10
    c.Font.Bold = primary
    If primary Then
        c.BackColor = RGB(37, 99, 235)
        c.ForeColor = RGB(255, 255, 255)
    Else
        c.BackColor = RGB(234, 239, 247)
        c.ForeColor = RGB(38, 57, 85)
    End If
    Set AddButton = c
End Function

Private Sub cmdBrowse_Click()
    Dim p As String
    p = ChooseCSV(ActiveDocument)
    If Len(p) > 0 Then txtCSV.Text = p
End Sub

Private Sub cmdTemplate_Click()
    Dim p As String
    p = CreateCSVTemplate()
    If Len(p) > 0 Then txtCSV.Text = p
End Sub

Private Sub cmdRun_Click()
    If Len(Trim$(txtCSV.Text)) = 0 Then
        MsgBox "Select a CSV file first.", vbExclamation
        Exit Sub
    End If
    If Not IsNumeric(txtCols.Text) Or Not IsNumeric(txtX.Text) Or Not IsNumeric(txtY.Text) Then
        MsgBox "Columns and spacing must be numeric.", vbExclamation
        Exit Sub
    End If
    If CLng(txtCols.Text) < 1 Then
        MsgBox "Columns must be at least 1.", vbExclamation
        Exit Sub
    End If
    RunCreateFromCSV txtCSV.Text, CLng(txtCols.Text), CDbl(txtX.Text), CDbl(txtY.Text)
End Sub

Private Sub cmdClose_Click()
    Unload Me
End Sub

Private Function RuText(ByVal codes As String) As String
    Dim a() As String, i As Long
    a = Split(codes, ",")
    For i = LBound(a) To UBound(a)
        RuText = RuText & ChrW$(CLng(a(i)))
    Next i
End Function
