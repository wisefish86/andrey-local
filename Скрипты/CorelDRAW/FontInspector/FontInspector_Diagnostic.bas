Attribute VB_Name = "FontInspector_Diagnostic"
Option Explicit

' Fast inspection without UserForm or FRX. Read-only.
Public Sub Main_FontInspector_Diagnostic()
    Dim choose As VbMsgBoxResult
    Dim fonts As Object, sh As Shape, pg As Page, key As Variant
    Dim message As String
    On Error GoTo Failed
    choose = MsgBox("Font Inspector started." & vbCrLf & _
        "YES: selected objects; NO: all pages; CANCEL: quit.", _
        vbYesNoCancel + vbQuestion, "Font Inspector")
    If choose = vbCancel Then Exit Sub
    If Documents.Count = 0 Then MsgBox "Open a document.": Exit Sub
    Set fonts = CreateObject("Scripting.Dictionary")
    fonts.CompareMode = vbTextCompare
    If choose = vbYes Then
        For Each sh In ActiveSelectionRange
            CheckShape sh, fonts, 0
        Next sh
    Else
        For Each pg In ActiveDocument.Pages
            For Each sh In pg.Shapes
                CheckShape sh, fonts, 0
            Next sh
        Next pg
    End If
    message = "Fonts found: " & fonts.Count & vbCrLf & vbCrLf
    For Each key In fonts.Keys
        message = message & CStr(key) & vbCrLf
        If Len(message) > 1300 Then Exit For
    Next key
    MsgBox message, vbInformation, "Font Inspector"
    Exit Sub
Failed:
    MsgBox "Error " & Err.Number & ": " & Err.Description, vbExclamation
End Sub

Private Sub CheckShape(ByVal sh As Shape, ByVal fonts As Object, ByVal depth As Long)
    Dim child As Shape, pc As PowerClip, f As String
    If depth > 60 Then Exit Sub
    On Error GoTo Skip
    If sh.Type = cdrTextShape Then
        f = Trim$(sh.Text.Story.Font)
        If Len(f) = 0 Then f = "[mixed / unknown]"
        If Not fonts.Exists(f) Then fonts.Add f, True
    End If
    If sh.Type = cdrGroupShape Then
        For Each child In sh.Shapes
            CheckShape child, fonts, depth + 1
        Next child
    End If
    Set pc = Nothing
    On Error Resume Next
    Set pc = sh.PowerClip
    On Error GoTo Skip
    If Not pc Is Nothing Then
        For Each child In pc.Shapes
            CheckShape child, fonts, depth + 1
        Next child
    End If
Skip:
End Sub
