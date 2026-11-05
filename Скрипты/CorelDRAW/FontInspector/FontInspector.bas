Attribute VB_Name = "FontInspector"
Option Explicit
' Название: Инспектор шрифтов (CorelDRAW)
' Модуль: FontInspector | Запуск: Main_FontInspector
' Назначение: поиск шрифтов в документе или выделении с переходом к тексту.
' Использование: выделить стенд (необязательно), запустить Main_FontInspector,
' нажать "Проверить", выбрать шрифт и фрагмент, нажать "Перейти".
' Безопасность: только чтение, не меняет текст, стили и объекты.
' Требуется форма frmFontInspector. CorelDRAW 2026 VBA, Windows.
' Проверка: компиляция/работа в самом CorelDRAW пока не подтверждены.
' Важно: у CorelDRAW TextRange.Font тип String, не .Font.Name.

Public InspectorItems As Collection
Public InspectorDocument As Document
Public InspectorSelectionMode As Boolean
Public InspectorScopeShapes As Collection
Public InspectorScopeDocument As Document
Public InspectorWarnings As Long
Public InspectorTextObjects As Long
Public InspectorCharCount As Long
Public InspectorCancelled As Boolean
Public InspectorRunning As Boolean
Private InspectorQueue As Collection
Private InspectorQueueIndex As Long
Private InspectorCurrent As Shape
Private InspectorCurrentPage As Long
Private InspectorRawText As String
Private InspectorTextPosition As Long
Private InspectorRunStart As Long
Private InspectorRunFont As String
Private InspectorLimit As Long
Private Const MAX_CHARS As Long = 600000

Public Sub Main_FontInspector()
    If Documents.Count = 0 Then
        MsgBox "Сначала откройте документ CorelDRAW.", vbExclamation
        Exit Sub
    End If
    On Error GoTo OpenError
    InspectorSelectionMode = (ActiveSelectionRange.Count > 0)
    If InspectorSelectionMode Then InspectorCaptureSelection
    Load frmFontInspector
    frmFontInspector.Show vbModeless
    Exit Sub
OpenError:
    MsgBox "Инспектор не открылся. Ошибка " & Err.Number & ": " & Err.Description & vbCrLf & _
           "Проверьте имя формы frmFontInspector и Debug > Compile VBAProject.", vbExclamation
End Sub

Public Function InspectorCaptureSelection() As Boolean
    Dim sh As Shape
    If Documents.Count = 0 Then Exit Function
    Set InspectorScopeShapes = New Collection
    Set InspectorScopeDocument = ActiveDocument
    For Each sh In ActiveSelectionRange
        InspectorScopeShapes.Add sh
    Next sh
    InspectorCaptureSelection = (InspectorScopeShapes.Count > 0)
End Function

Public Sub InspectorPrepareScan()
    Dim pg As Page, sh As Shape
    If Documents.Count = 0 Then Err.Raise vbObjectError + 711, , "Документ закрыт."
    InspectorCancelled = False
    Set InspectorDocument = ActiveDocument
    Set InspectorItems = New Collection
    Set InspectorQueue = New Collection
    InspectorQueueIndex = 1
    Set InspectorCurrent = Nothing
    InspectorWarnings = 0
    InspectorTextObjects = 0
    InspectorCharCount = 0
    InspectorLimit = 0
    If InspectorSelectionMode Then
        If InspectorScopeShapes Is Nothing Then Err.Raise vbObjectError + 712, , "Выделите стенд и нажмите «Взять выделение»."
        If Not InspectorScopeDocument Is InspectorDocument Then Err.Raise vbObjectError + 713, , "Выделение относится к другому документу."
        If InspectorScopeShapes.Count = 0 Then Err.Raise vbObjectError + 714, , "Нет выделения."
        For Each sh In InspectorScopeShapes
            InspectorCollect sh, 0
        Next sh
    Else
        For Each pg In InspectorDocument.Pages
            For Each sh In pg.Shapes
                InspectorCollect sh, 0
            Next sh
            DoEvents
            If InspectorCancelled Then Exit Sub
        Next pg
    End If
End Sub

Private Sub InspectorCollect(ByVal sh As Shape, ByVal depth As Long)
    Dim child As Shape, item As Object, pc As PowerClip
    If InspectorCancelled Then Exit Sub
    If depth > 80 Then InspectorWarnings = InspectorWarnings + 1: Exit Sub
    On Error GoTo ShapeError
    If sh.Type = cdrTextShape Then
        Set item = CreateObject("Scripting.Dictionary")
        item.Add "page", sh.Layer.Page.Index
        item.Add "shape", Empty
        Set item.Item("shape") = sh
        InspectorQueue.Add item
    End If
    If sh.Type = cdrGroupShape Then
        For Each child In sh.Shapes
            InspectorCollect child, depth + 1
        Next child
    End If
    Set pc = Nothing
    On Error Resume Next
    Err.Clear
    Set pc = sh.PowerClip
    If Err.Number <> 0 Then InspectorWarnings = InspectorWarnings + 1
    Err.Clear
    On Error GoTo ShapeError
    If Not pc Is Nothing Then
        For Each child In pc.Shapes
            InspectorCollect child, depth + 1
        Next child
    End If
    Exit Sub
ShapeError:
    InspectorWarnings = InspectorWarnings + 1
End Sub

Public Function InspectorTotalObjects() As Long
    If Not InspectorQueue Is Nothing Then InspectorTotalObjects = InspectorQueue.Count
End Function

Public Function InspectorScannedObjects() As Long
    InspectorScannedObjects = InspectorTextObjects
End Function

' Small bounded step: the form calls DoEvents between steps, so Stop works.
' Returns False when complete or stopped.
Public Function InspectorScanStep(ByVal charBudget As Long) As Boolean
    Dim n As Long, f As String, completed As Boolean, item As Object
    If InspectorCancelled Then Exit Function
    If InspectorQueue Is Nothing Then Exit Function
    On Error GoTo StepError
    Do While charBudget > 0
        If InspectorCurrent Is Nothing Then
            If InspectorQueueIndex > InspectorQueue.Count Then Exit Function
            Set item = InspectorQueue(InspectorQueueIndex)
            Set InspectorCurrent = item.Item("shape")
            InspectorCurrentPage = CLng(item.Item("page"))
            InspectorRawText = InspectorCurrent.Text.Story.Text
            InspectorTextPosition = 1
            InspectorRunStart = 1
            InspectorRunFont = ""
            If Len(InspectorRawText) > MAX_CHARS - InspectorCharCount Then
                InspectorWarnings = InspectorWarnings + 1
                InspectorRawText = ""
            End If
            InspectorCharCount = InspectorCharCount + Len(InspectorRawText)
        End If
        n = Len(InspectorRawText)
        If InspectorTextPosition > n Then
            If InspectorTextPosition > 1 Then
                InspectorAdd InspectorCurrent, InspectorCurrentPage, InspectorRunFont, _
                             InspectorRawText, InspectorRunStart, n + 1 - InspectorRunStart
            End If
            Set InspectorCurrent = Nothing
            InspectorTextObjects = InspectorTextObjects + 1
            InspectorQueueIndex = InspectorQueueIndex + 1
        Else
            f = InspectorCharFont(InspectorCurrent, InspectorTextPosition)
            If InspectorTextPosition = 1 Then
                InspectorRunFont = f
            ElseIf StrComp(f, InspectorRunFont, vbTextCompare) <> 0 Then
                InspectorAdd InspectorCurrent, InspectorCurrentPage, InspectorRunFont, _
                             InspectorRawText, InspectorRunStart, InspectorTextPosition - InspectorRunStart
                InspectorRunStart = InspectorTextPosition
                InspectorRunFont = f
            End If
            InspectorTextPosition = InspectorTextPosition + 1
            charBudget = charBudget - 1
        End If
        If InspectorCancelled Then Exit Function
    Loop
    InspectorScanStep = (InspectorQueueIndex <= InspectorQueue.Count)
    Exit Function
StepError:
    InspectorWarnings = InspectorWarnings + 1
    Set InspectorCurrent = Nothing
    InspectorQueueIndex = InspectorQueueIndex + 1
    InspectorScanStep = (InspectorQueueIndex <= InspectorQueue.Count)
End Function

Private Function InspectorCharFont(ByVal sh As Shape, ByVal offset As Long) As String
    On Error GoTo FontError
    InspectorCharFont = Trim$(sh.Text.Story.Characters(offset, 1).Font)
    If Len(InspectorCharFont) = 0 Then InspectorCharFont = "[Unknown font]"
    Exit Function
FontError:
    InspectorCharFont = "[Unknown font]"
    InspectorWarnings = InspectorWarnings + 1
End Function

Private Sub InspectorAdd(ByVal sh As Shape, ByVal pageNum As Long, ByVal f As String, _
                         ByVal rawText As String, ByVal startAt As Long, ByVal runLength As Long)
    Dim row As Object, preview As String
    If runLength <= 0 Then Exit Sub
    Set row = CreateObject("Scripting.Dictionary")
    row.Add "font", f
    row.Add "page", pageNum
    row.Add "start", startAt
    row.Add "length", runLength
    preview = Mid$(rawText, startAt, runLength)
    preview = Replace(preview, vbCr, " ")
    preview = Replace(preview, vbLf, " ")
    preview = Replace(preview, vbTab, " ")
    If Len(preview) > 76 Then preview = Left$(preview, 76) & "..."
    row.Add "preview", preview
    row.Add "shape", Empty
    Set row.Item("shape") = sh
    InspectorItems.Add row
End Sub

Public Function InspectorGoTo(ByVal index As Long) As Boolean
    Dim row As Object, sh As Shape
    On Error GoTo NavigationError
    If InspectorRunning Then Exit Function
    If Documents.Count = 0 Then Exit Function
    If Not ActiveDocument Is InspectorDocument Then Exit Function
    If index < 1 Or index > InspectorItems.Count Then Exit Function
    Set row = InspectorItems(index)
    Set sh = row.Item("shape")
    InspectorDocument.Pages(CLng(row.Item("page"))).Activate
    sh.CreateSelection
    On Error Resume Next
    ActiveWindow.ActiveView.ToFitSelection
    On Error GoTo NavigationError
    InspectorGoTo = True
    Exit Function
NavigationError:
    MsgBox "Не удалось выделить объект: " & Err.Description, vbExclamation
End Function
