VERSION 5.00
Begin VB.UserForm frmCreateFromCSV
   Caption         =   "Create objects from CSV"
   ClientHeight    =   4950
   ClientLeft      =   120
   ClientTop       =   465
   ClientWidth     =   6300
   StartUpPosition =   1
   Begin MSForms.Label lblGroup
      Caption         =   "Select one group with @Text, @Number ..."
      Height          =   270
      Left            =   270
      Top             =   240
      Width           =   5670
   End
   Begin MSForms.Label lblCSV
      Caption         =   "CSV file:"
      Height          =   270
      Left            =   270
      Top             =   690
      Width           =   2175
   End
   Begin MSForms.TextBox txtCSV
      Height          =   315
      Left            =   270
      Top             =   990
      Width           =   4410
   End
   Begin MSForms.CommandButton cmdBrowse
      Caption         =   "Browse..."
      Height          =   345
      Left            =   4800
      Top             =   975
      Width           =   1170
   End
   Begin MSForms.CommandButton cmdTemplate
      Caption         =   "Create CSV from group"
      Height          =   420
      Left            =   270
      Top             =   1560
      Width           =   5700
   End
   Begin MSForms.Label lblCols
      Caption         =   "Columns"
      Height          =   270
      Left            =   270
      Top             =   2265
      Width           =   1650
   End
   Begin MSForms.Label lblX
      Caption         =   "Spacing X (mm)"
      Height          =   270
      Left            =   2265
      Top             =   2265
      Width           =   1740
   End
   Begin MSForms.Label lblY
      Caption         =   "Spacing Y (mm)"
      Height          =   270
      Left            =   4260
      Top             =   2265
      Width           =   1710
   End
   Begin MSForms.TextBox txtCols
      Height          =   315
      Left            =   270
      Top             =   2580
      Width           =   1575
   End
   Begin MSForms.TextBox txtX
      Height          =   315
      Left            =   2265
      Top             =   2580
      Width           =   1575
   End
   Begin MSForms.TextBox txtY
      Height          =   315
      Left            =   4260
      Top             =   2580
      Width           =   1575
   End
   Begin MSForms.Label lblHint
      Caption         =   "CSV headers without @. The selected group is the first object."
      Height          =   480
      Left            =   270
      Top             =   3165
      Width           =   5670
   End
   Begin MSForms.CommandButton cmdRun
      Caption         =   "Create objects"
      Height          =   450
      Left            =   270
      Top             =   3900
      Width           =   3600
   End
   Begin MSForms.CommandButton cmdCancel
      Caption         =   "Close"
      Height          =   450
      Left            =   4080
      Top             =   3900
      Width           =   1890
   End
End
Attribute VB_Name = "frmCreateFromCSV"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Option Explicit
Private Sub UserForm_Initialize()
    Me.Controls("txtCSV").Text = CSVDefaultPath()
    Me.Controls("txtCols").Text = "4"
    Me.Controls("txtX").Text = "10"
    Me.Controls("txtY").Text = "10"
End Sub
Private Sub cmdBrowse_Click()
    Dim p As String
    If Documents.Count = 0 Then Exit Sub
    p = ChooseCSV(ActiveDocument)
    If Len(p) > 0 Then Me.Controls("txtCSV").Text = p
End Sub
Private Sub cmdTemplate_Click()
    Dim p As String
    p = CreateCSVTemplate()
    If Len(p) > 0 Then
        Me.Controls("txtCSV").Text = p
        MsgBox "CSV template created: " & p, vbInformation
    End If
End Sub
Private Sub cmdRun_Click()
    Dim n As Long, x As Double, y As Double
    If Not IsNumeric(Me.Controls("txtCols").Text) Then
        MsgBox "Enter a numeric column count.", vbExclamation
        Exit Sub
    End If
    n = CLng(Me.Controls("txtCols").Text)
    If n < 1 Then
        MsgBox "Column count must be positive.", vbExclamation
        Exit Sub
    End If
    If Not IsNumeric(Me.Controls("txtX").Text) Or Not IsNumeric(Me.Controls("txtY").Text) Then
        MsgBox "Spacing must be numeric.", vbExclamation
        Exit Sub
    End If
    x = CDbl(Me.Controls("txtX").Text)
    y = CDbl(Me.Controls("txtY").Text)
    RunCreateFromCSV CStr(Me.Controls("txtCSV").Text), n, x, y
End Sub
Private Sub cmdCancel_Click()
    Unload Me
End Sub
