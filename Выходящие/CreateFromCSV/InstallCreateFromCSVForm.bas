Attribute VB_Name = "InstallCreateFromCSVForm"
Option Explicit
' One-time installer. Requires "Trust access to the VBA project object model".
Public Sub Install_CreateFromCSV_UserForm()
    Dim prj As Object, comp As Object, des As Object, ctl As Object
    Dim oldComp As Object
    On Error GoTo Failed
    Set prj = Application.VBE.ActiveVBProject
    On Error Resume Next
    Set oldComp = prj.VBComponents("frmCreateFromCSV")
    On Error GoTo Failed
    If Not oldComp Is Nothing Then
        MsgBox "frmCreateFromCSV already exists. Remove the incorrect module/form first and run the installer again.", vbExclamation
        Exit Sub
    End If
    Set comp = prj.VBComponents.Add(3) ' vbext_ct_MSForm
    comp.Name = "frmCreateFromCSV"
    Set des = comp.Designer
    des.Caption = "Create objects from CSV"
    des.Width = 420
    des.Height = 330
    AddUI des, "Forms.Label.1", "lblGroup", "Select one group with @Text, @Number ...", 18, 16, 378, 18
    AddUI des, "Forms.Label.1", "lblCSV", "CSV file:", 18, 46, 145, 18
    AddUI des, "Forms.TextBox.1", "txtCSV", "", 18, 66, 294, 21
    AddUI des, "Forms.CommandButton.1", "cmdBrowse", "Browse...", 320, 65, 78, 23
    AddUI des, "Forms.CommandButton.1", "cmdTemplate", "Create CSV from group", 18, 104, 380, 28
    AddUI des, "Forms.Label.1", "lblCols", "Columns", 18, 151, 110, 18
    AddUI des, "Forms.Label.1", "lblX", "Spacing X (mm)", 151, 151, 116, 18
    AddUI des, "Forms.Label.1", "lblY", "Spacing Y (mm)", 284, 151, 114, 18
    AddUI des, "Forms.TextBox.1", "txtCols", "", 18, 172, 105, 21
    AddUI des, "Forms.TextBox.1", "txtX", "", 151, 172, 105, 21
    AddUI des, "Forms.TextBox.1", "txtY", "", 284, 172, 105, 21
    AddUI des, "Forms.Label.1", "lblHint", "CSV headers without @. The selected group is the first object.", 18, 211, 378, 32
    AddUI des, "Forms.CommandButton.1", "cmdRun", "Create objects", 18, 260, 240, 30
    AddUI des, "Forms.CommandButton.1", "cmdCancel", "Close", 272, 260, 126, 30
    comp.CodeModule.AddFromString FormSource()
    MsgBox "UserForm created in the Forms section. Save the GMS project.", vbInformation
    Exit Sub
Failed:
    MsgBox "Could not install UserForm: " & Err.Description & vbCrLf & _
           "Enable Trust access to the VBA project object model, select the correct GMS project in VBE and retry.", vbCritical
End Sub
Private Sub AddUI(ByVal designer As Object, ByVal className As String, ByVal controlName As String, _
                  ByVal caption As String, ByVal x As Single, ByVal y As Single, _
                  ByVal w As Single, ByVal h As Single)
    Dim c As Object
    Set c = designer.Controls.Add(className, controlName, True)
    c.Left = x
    c.Top = y
    c.Width = w
    c.Height = h
    If className <> "Forms.TextBox.1" Then c.Caption = caption
End Sub
Private Function FormSource() As String
    FormSource = "Option Explicit
"
    FormSource = FormSource & "Private Sub UserForm_Initialize()
"
    FormSource = FormSource & "    Me.Controls(""txtCSV"").Text = CSVDefaultPath()
"
    FormSource = FormSource & "    Me.Controls(""txtCols"").Text = ""4""
"
    FormSource = FormSource & "    Me.Controls(""txtX"").Text = ""10""
"
    FormSource = FormSource & "    Me.Controls(""txtY"").Text = ""10""
"
    FormSource = FormSource & "End Sub
"
    FormSource = FormSource & "Private Sub cmdBrowse_Click()
"
    FormSource = FormSource & "    Dim p As String
"
    FormSource = FormSource & "    If Documents.Count = 0 Then Exit Sub
"
    FormSource = FormSource & "    p = ChooseCSV(ActiveDocument)
"
    FormSource = FormSource & "    If Len(p) > 0 Then Me.Controls(""txtCSV"").Text = p
"
    FormSource = FormSource & "End Sub
"
    FormSource = FormSource & "Private Sub cmdTemplate_Click()
"
    FormSource = FormSource & "    Dim p As String
"
    FormSource = FormSource & "    p = CreateCSVTemplate()
"
    FormSource = FormSource & "    If Len(p) > 0 Then
"
    FormSource = FormSource & "        Me.Controls(""txtCSV"").Text = p
"
    FormSource = FormSource & "        MsgBox ""CSV template created: "" & p, vbInformation
"
    FormSource = FormSource & "    End If
"
    FormSource = FormSource & "End Sub
"
    FormSource = FormSource & "Private Sub cmdRun_Click()
"
    FormSource = FormSource & "    Dim n As Long, x As Double, y As Double
"
    FormSource = FormSource & "    If Not IsNumeric(Me.Controls(""txtCols"").Text) Then
"
    FormSource = FormSource & "        MsgBox ""Enter a numeric column count."", vbExclamation
"
    FormSource = FormSource & "        Exit Sub
"
    FormSource = FormSource & "    End If
"
    FormSource = FormSource & "    n = CLng(Me.Controls(""txtCols"").Text)
"
    FormSource = FormSource & "    If n < 1 Then
"
    FormSource = FormSource & "        MsgBox ""Column count must be positive."", vbExclamation
"
    FormSource = FormSource & "        Exit Sub
"
    FormSource = FormSource & "    End If
"
    FormSource = FormSource & "    If Not IsNumeric(Me.Controls(""txtX"").Text) Or Not IsNumeric(Me.Controls(""txtY"").Text) Then
"
    FormSource = FormSource & "        MsgBox ""Spacing must be numeric."", vbExclamation
"
    FormSource = FormSource & "        Exit Sub
"
    FormSource = FormSource & "    End If
"
    FormSource = FormSource & "    x = CDbl(Me.Controls(""txtX"").Text)
"
    FormSource = FormSource & "    y = CDbl(Me.Controls(""txtY"").Text)
"
    FormSource = FormSource & "    RunCreateFromCSV CStr(Me.Controls(""txtCSV"").Text), n, x, y
"
    FormSource = FormSource & "End Sub
"
    FormSource = FormSource & "Private Sub cmdCancel_Click()
"
    FormSource = FormSource & "    Unload Me
"
    FormSource = FormSource & "End Sub"
End Function
