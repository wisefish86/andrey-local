Option Explicit

Private smallestPt As Double
Private foundText As Boolean

Private Sub ScanText(ByVal s As Shape)
    Dim child As Shape
    Dim i As Long
    Dim pt As Double

    If s.Type = cdrGroupShape Then
        For Each child In s.Shapes
            ScanText child
        Next child
        Exit Sub
    End If
    If s.Type <> cdrTextShape Then Exit Sub

    On Error Resume Next
    For i = 1 To s.Text.Story.Characters.Count
        Err.Clear
        pt = CDbl(s.Text.Story.Characters(i).Size)
        If Err.Number = 0 And pt > 0 Then
            foundText = True
            If pt < smallestPt Then smallestPt = pt
        End If
    Next i
    On Error GoTo 0
End Sub

Private Function SafeSuffix(ByVal raw As String) As String
    Dim bad As String
    Dim i As Long
    Dim value As String

    value = Trim$(raw)
    bad = "<>:/" & Chr$(92) & Chr$(34) & "|?*"
    For i = 1 To Len(bad)
        value = Replace$(value, Mid$(bad, i, 1), "_")
    Next i
    For i = 0 To 31
        value = Replace$(value, Chr$(i), "_")
    Next i
    Do While Len(value) > 0
        If Right$(value, 1) <> "." And Right$(value, 1) <> " " Then Exit Do
        value = Left$(value, Len(value) - 1)
    Loop
    If value = "0" Then value = ""
    SafeSuffix = value
End Function

Public Sub ExportSmartPNG()
    On Error GoTo Failed

    Const TARGET_FONT_PX As Double = 13#
    Const MIN_WIDTH_PX As Double = 900#
    Const FALLBACK_WIDTH_PX As Double = 900#
    Const MAX_SIDE_PX As Double = 8000#

    Dim d As Document
    Dim sh As Shape
    Dim f As ExportFilter
    Dim oldUnit As cdrUnit
    Dim unitChanged As Boolean
    Dim x As Double, y As Double, w As Double, h As Double
    Dim pixelW As Double, pixelH As Double, scaleFactor As Double
    Dim suffix As String, baseName As String
    Dim targetPath As String, tempPath As String
    Dim folderPath As String
    Dim dotPos As Long
    Dim n As Long
    Dim savedError As String

    If Application.Documents.Count = 0 Then
        MsgBox "Open a CDR file first.", vbExclamation
        Exit Sub
    End If
    Set d = ActiveDocument
    If Len(d.FilePath) = 0 Then
        MsgBox "Save the CDR file first.", vbExclamation
        Exit Sub
    End If
    If ActiveSelectionRange.Count = 0 Then
        MsgBox "Select objects first.", vbExclamation
        Exit Sub
    End If

    suffix = InputBox("Optional file suffix (empty = none):", "Export PNG", "")
    ' VBA InputBox returns a null BSTR pointer on Cancel, but an empty
    ' non-null string when OK is pressed with the field left blank.
    If StrPtr(suffix) = 0 Then Exit Sub
    suffix = SafeSuffix(suffix)

    baseName = d.Name
    dotPos = InStrRev(baseName, ".")
    If dotPos > 0 Then baseName = Left$(baseName, dotPos - 1)
    If Len(suffix) > 0 Then baseName = baseName & " - " & suffix

    folderPath = d.FilePath
    If Right$(folderPath, 1) <> Chr$(92) Then folderPath = folderPath & Chr$(92)
    targetPath = folderPath & baseName & ".png"

    oldUnit = d.Unit
    d.Unit = cdrMillimeter
    unitChanged = True
    ActiveSelectionRange.GetBoundingBox x, y, w, h, True
    If w <= 0 Or h <= 0 Then Err.Raise 5, , "Invalid selection size."

    smallestPt = 1000000#
    foundText = False
    For Each sh In ActiveSelectionRange
        ScanText sh
    Next sh

    If foundText Then
        pixelW = w * TARGET_FONT_PX / (smallestPt * 25.4 / 72)
    Else
        pixelW = FALLBACK_WIDTH_PX
    End If
    If pixelW < MIN_WIDTH_PX Then pixelW = MIN_WIDTH_PX
    pixelH = pixelW * h / w

    If pixelW > MAX_SIDE_PX Or pixelH > MAX_SIDE_PX Then
        scaleFactor = MAX_SIDE_PX / pixelW
        If pixelH > pixelW Then scaleFactor = MAX_SIDE_PX / pixelH
        pixelW = pixelW * scaleFactor
        pixelH = pixelH * scaleFactor
    End If
    If pixelW < 1 Then pixelW = 1
    If pixelH < 1 Then pixelH = 1

    d.Unit = oldUnit
    unitChanged = False

    ' Export into a unique temporary PNG first.
    ' A failed export must not destroy an existing final PNG.
    n = 1
    Do
        tempPath = folderPath & baseName & ".__smartpng_tmp_" & CStr(n) & ".png"
        n = n + 1
    Loop While Len(Dir$(tempPath)) > 0

    Set f = d.ExportBitmap(tempPath, cdrPNG, cdrSelection, _
        cdrRGBColorImage, CLng(pixelW), CLng(pixelH), 96, 96, _
        cdrNormalAntiAliasing, False, False)
    f.Finish
    Set f = Nothing

    If Len(Dir$(tempPath)) = 0 Then Err.Raise 53, , "PNG file was not created."

    ' Replace silently only after successful export.
    If Len(Dir$(targetPath)) > 0 Then Kill targetPath
    Name tempPath As targetPath

    If MsgBox("File saved as:" & vbCrLf & baseName & ".png" & vbCrLf & _
        "Size: " & CLng(pixelW) & " x " & CLng(pixelH) & " px" & vbCrLf & vbCrLf & _
        "Open saved PNG?", vbYesNo + vbInformation, "Export PNG") = vbYes Then
        CreateObject("Shell.Application").ShellExecute targetPath, "", "", "open", 1
    End If
    Exit Sub

Failed:
    savedError = Err.Description
    On Error Resume Next
    If unitChanged Then d.Unit = oldUnit
    MsgBox "PNG export failed: " & savedError, vbCritical, "Export PNG"
End Sub
