VERSION 5.00
Begin {C62A69F0-16DC-11CE-9E98-00AA00574A4F} frmCreateFromCSV
   Caption         =   "Create objects from CSV"
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
    Me.Width = 492
    Me.Height = 374
    Me.BackColor = RGB(247, 249, 252)

    AddLabel "lblTitle", "Create objects from CSV", 20, 16, 446, 27, 15, True, RGB(27, 40, 58)
    AddLabel "lblSubtitle", "Duplicate a selected group and fill named text fields.", 20, 47, 446, 20, 9, False, RGB(101, 113, 131)

    AddLabel "lblSectionCSV", "01  DATA SOURCE", 20, 86, 440, 18, 9, True, RGB(53, 91, 153)
    AddLabel "lblFile", "CSV file", 20, 111, 440, 18, 9, False, RGB(58, 69, 86)
    Set txtCSV = AddText("txtCSV", 20, 134, 329, 26, "")
    Set cmdBrowse = AddButton("cmdBrowse", "Browse...", 359, 134, 107, 26, False)
    Set cmdTemplate = AddButton("cmdTemplate", "Generate CSV template from selected group", 20, 170, 446, 28, False)

    AddLabel "lblSectionLayout", "02  LAYOUT", 20, 217, 440, 18, 9, True, RGB(53, 91, 153)
    AddLabel "lblCols", "Columns", 20, 241, 130, 18, 9, False, RGB(58, 69, 86)
    AddLabel "lblX", "Horizontal gap (mm)", 173, 241, 130, 18, 9, False, RGB(58, 69, 86)
    AddLabel "lblY", "Vertical gap (mm)", 326, 241, 140, 18, 9, False, RGB(58, 69, 86)
    Set txtCols = AddText("txtCols", 20, 262, 128, 25, "4")
    Set txtX = AddText("txtX", 173, 262, 128, 25, "10")
    Set txtY = AddText("txtY", 326, 262, 140, 25, "10")

    Set cmdRun = AddButton("cmdRun", "Create objects", 20, 310, 293, 32, True)
    Set cmdClose = AddButton("cmdClose", "Close", 326, 310, 140, 32, False)
    Exit Sub
InitError:
    MsgBox "Form initialization failed: " & Err.Description, vbExclamation
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
