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
    Me.Width = 440
    Me.Height = 340
    AddLabel "lblIntro", "Select a group containing text shapes named @Number, @Text ...", 12, 12, 410, 18
    AddLabel "lblFile", "CSV file:", 12, 40, 400, 18
    Set txtCSV = AddText("txtCSV", 12, 60, 305, 21, "")
    Set cmdBrowse = AddButton("cmdBrowse", "Browse...", 326, 60, 94, 23)
    Set cmdTemplate = AddButton("cmdTemplate", "Create CSV template from group", 12, 100, 408, 28)
    AddLabel "lblCols", "Columns", 12, 145, 100, 18
    AddLabel "lblX", "Spacing X (mm)", 151, 145, 120, 18
    AddLabel "lblY", "Spacing Y (mm)", 290, 145, 120, 18
    Set txtCols = AddText("txtCols", 12, 166, 100, 21, "4")
    Set txtX = AddText("txtX", 151, 166, 100, 21, "10")
    Set txtY = AddText("txtY", 290, 166, 100, 21, "10")
    AddLabel "lblHint", "CSV headers without @. The selected group is the first object.", 12, 208, 408, 32
    Set cmdRun = AddButton("cmdRun", "Create objects", 12, 267, 254, 30)
    Set cmdClose = AddButton("cmdClose", "Close", 278, 267, 142, 30)
    Exit Sub
InitError:
    MsgBox "Form initialization failed: " & Err.Description, vbExclamation
End Sub

Private Sub AddLabel(ByVal n As String, ByVal t As String, ByVal x As Single, ByVal y As Single, ByVal w As Single, ByVal h As Single)
    Dim c As MSForms.Label
    Set c = Me.Controls.Add("Forms.Label.1", n, True)
    c.Caption = t
    c.Left = x: c.Top = y: c.Width = w: c.Height = h
End Sub

Private Function AddText(ByVal n As String, ByVal x As Single, ByVal y As Single, ByVal w As Single, ByVal h As Single, ByVal v As String) As MSForms.TextBox
    Dim c As MSForms.TextBox
    Set c = Me.Controls.Add("Forms.TextBox.1", n, True)
    c.Left = x: c.Top = y: c.Width = w: c.Height = h
    c.Text = v
    Set AddText = c
End Function

Private Function AddButton(ByVal n As String, ByVal t As String, ByVal x As Single, ByVal y As Single, ByVal w As Single, ByVal h As Single) As MSForms.CommandButton
    Dim c As MSForms.CommandButton
    Set c = Me.Controls.Add("Forms.CommandButton.1", n, True)
    c.Caption = t
    c.Left = x: c.Top = y: c.Width = w: c.Height = h
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
