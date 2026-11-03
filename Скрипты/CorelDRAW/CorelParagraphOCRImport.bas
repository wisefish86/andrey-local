' Название: Импорт OCR-плакатов в абзацные блоки
' Модуль: CorelParagraphOCRImport
' Запуск: Main_ImportPosterOCR
' Назначение: Создает НОВЫЙ документ CorelDRAW с двумя страницами
' и редактируемыми абзацными текстовыми рамками по координатам JSON.
' Использование:
'   1. Запустите Main_ImportPosterOCR из редактора макросов CorelDRAW.
'   2. Выберите файл posters_ocr_corel.json.
'   3. Проверьте текст, переносы, переполнение и сохраните CDR.
' Условия: исходные документы не меняются; картинки в CDR не импортируются.
' JSON: UTF-8, схема corel-paragraph-ocr/v1. Макрос не исправляет исходный текст.
' Важно: выполнение и компиляция в CorelDRAW 2026 не проверены.
Option Explicit

Public Sub Main_ImportPosterOCR()
    Dim jsonPath As String, raw As String
    Dim pages As Collection, items As Collection
    Dim pageInfo As Variant, entry As Variant
    Dim pageWidth(1 To 2) As Double, pageHeight(1 To 2) As Double
    Dim sourceWidth(1 To 2) As Double, sourceHeight(1 To 2) As Double
    Dim doc As Document, sh As Shape
    Dim p As Long, count As Long, reviewCount As Long
    Dim x As Double, y As Double, w As Double, h As Double
    Dim leftEdge As Double, rightEdge As Double
    Dim topEdge As Double, bottomEdge As Double
    Dim fontSize As Single, boldState As cdrTriState
    Dim itemId As String, itemText As String, itemRole As String
    Dim created As Boolean, msg As String

    On Error GoTo ImportFailed
    jsonPath = CorelScriptTools.GetFileBox( _
        "OCR JSON (*.json)|*.json|All files (*.*)|*.*", _
        "Выберите распознанный плакат JSON", 0)
    If Len(jsonPath) = 0 Then Exit Sub
    raw = LoadUtf8Text(jsonPath)
    If InStr(1, raw, "corel-paragraph-ocr/v1", vbBinaryCompare) = 0 Then
        Err.Raise vbObjectError + 920, , "Неподдерживаемая схема JSON"
    End If

    Set pages = JsonObjects(raw, "pages")
    Set items = JsonObjects(raw, "blocks")
    If pages.Count <> 2 Then Err.Raise vbObjectError + 921, , "В JSON ожидается ровно 2 страницы"
    If items.Count = 0 Then Err.Raise vbObjectError + 922, , "В JSON нет текстовых блоков"

    ' Сначала проверяем размеры и структуру, чтобы не создавать ошибочный документ.
    For Each pageInfo In pages
        p = CLng(Val(JsonValue(CStr(pageInfo), "page")))
        If p < 1 Or p > 2 Then Err.Raise vbObjectError + 923, , "Номер страницы вне диапазона"
        pageWidth(p) = Val(JsonValue(CStr(pageInfo), "width_mm"))
        pageHeight(p) = Val(JsonValue(CStr(pageInfo), "height_mm"))
        sourceWidth(p) = Val(JsonValue(CStr(pageInfo), "source_width_px"))
        sourceHeight(p) = Val(JsonValue(CStr(pageInfo), "source_height_px"))
    Next pageInfo
    For p = 1 To 2
        If pageWidth(p) <= 0 Or pageHeight(p) <= 0 Or _
           sourceWidth(p) <= 0 Or sourceHeight(p) <= 0 Then
            Err.Raise vbObjectError + 924, , "Неверные размеры страницы " & CStr(p)
        End If
    Next p
    For Each entry In items
        p = CLng(Val(JsonValue(CStr(entry), "page")))
        If p < 1 Or p > 2 Then Err.Raise vbObjectError + 925, , "Некорректная страница блока"
        x = Val(JsonValue(CStr(entry), "x_px"))
        y = Val(JsonValue(CStr(entry), "y_px"))
        w = Val(JsonValue(CStr(entry), "width_px"))
        h = Val(JsonValue(CStr(entry), "height_px"))
        If x < 0 Or y < 0 Or w <= 0 Or h <= 0 Or _
           x + w > sourceWidth(p) + 1 Or y + h > sourceHeight(p) + 1 Then
            Err.Raise vbObjectError + 926, , "Неверная геометрия: " & JsonValue(CStr(entry), "id")
        End If
    Next entry

    ' Создаём отдельный документ, никак не изменяя уже открытые макеты.
    Set doc = Application.CreateDocument
    created = True
    doc.Unit = cdrMillimeter
    doc.Pages(1).SetSize pageWidth(1), pageHeight(1)
    doc.AddPages 1
    doc.Pages(2).SetSize pageWidth(2), pageHeight(2)

    For Each entry In items
        itemId = JsonValue(CStr(entry), "id")
        itemText = JsonValue(CStr(entry), "text")
        itemRole = JsonValue(CStr(entry), "role")
        p = CLng(Val(JsonValue(CStr(entry), "page")))
        x = Val(JsonValue(CStr(entry), "x_px"))
        y = Val(JsonValue(CStr(entry), "y_px"))
        w = Val(JsonValue(CStr(entry), "width_px"))
        h = Val(JsonValue(CStr(entry), "height_px"))
        fontSize = CSng(Val(JsonValue(CStr(entry), "font_pt")))
        If fontSize < 4 Or fontSize > 64 Then fontSize = 8
        boldState = cdrFalse
        If itemRole = "title" Or itemRole = "heading" Then boldState = cdrTrue

        leftEdge = pageWidth(p) * x / sourceWidth(p)
        rightEdge = pageWidth(p) * (x + w) / sourceWidth(p)
        topEdge = pageHeight(p) * (sourceHeight(p) - y) / sourceHeight(p)
        bottomEdge = pageHeight(p) * (sourceHeight(p) - y - h) / sourceHeight(p)
        Set sh = doc.Pages(p).ActiveLayer.CreateParagraphText( _
            leftEdge, topEdge, rightEdge, bottomEdge, itemText, , , _
            "Arial", fontSize, boldState)
        sh.Name = itemId & "_" & itemRole
        count = count + 1
        If JsonValue(CStr(entry), "needs_review") = "true" Then reviewCount = reviewCount + 1
        If count Mod 10 = 0 Then DoEvents
    Next entry

    doc.Pages(1).Activate
    MsgBox "Создан НОВЫЙ документ: " & CStr(count) & " абзацных рамок." & vbCrLf & _
           "Отмечено для проверки: " & CStr(reviewCount) & vbCrLf & _
           "Проверьте переполнение, переносы строк и сам текст." & vbCrLf & _
           "Исходные документы не изменялись.", vbInformation, "Импорт OCR"
    Exit Sub

ImportFailed:
    msg = "Импорт прерван: " & Err.Description & vbCrLf & _
          "Создано текстовых рамок: " & CStr(count) & "."
    If created Then msg = msg & vbCrLf & _
        "Новый документ может быть неполным. Закройте его без сохранения."
    MsgBox msg, vbExclamation, "Импорт OCR"
End Sub

Private Function LoadUtf8Text(ByVal path As String) As String
    Dim stream As Object
    Set stream = CreateObject("ADODB.Stream")
    stream.Type = 2               ' adTypeText
    stream.Charset = "utf-8"
    stream.Open
    stream.LoadFromFile path
    LoadUtf8Text = stream.ReadText(-1)
    stream.Close
    If Left$(LoadUtf8Text, 1) = ChrW$(65279) Then
        LoadUtf8Text = Mid$(LoadUtf8Text, 2)
    End If
End Function

' Извлекает плоские объекты массива pages или blocks без внешних библиотек.
' Учитывает кавычки и escapes, чтобы скобки внутри текста не рвали запись.
Private Function JsonObjects(ByVal raw As String, ByVal arrayName As String) As Collection
    Dim out As New Collection
    Dim startField As Long, i As Long, depth As Long, first As Long
    Dim insideString As Boolean, escaped As Boolean
    Dim ch As String
    startField = InStr(1, raw, """" & arrayName & """", vbBinaryCompare)
    If startField = 0 Then Err.Raise vbObjectError + 930, , "Не найден массив: " & arrayName
    startField = InStr(startField, raw, "[")
    If startField = 0 Then Err.Raise vbObjectError + 931, , "Не найдено начало массива"
    For i = startField + 1 To Len(raw)
        ch = Mid$(raw, i, 1)
        If insideString Then
            If escaped Then
                escaped = False
            ElseIf ch = "\" Then
                escaped = True
            ElseIf ch = """" Then
                insideString = False
            End If
        Else
            Select Case ch
                Case """"
                    insideString = True
                Case "{"
                    If depth = 0 Then first = i
                    depth = depth + 1
                Case "}"
                    depth = depth - 1
                    If depth < 0 Then Err.Raise vbObjectError + 932, , "Нарушенные скобки JSON"
                    If depth = 0 Then out.Add Mid$(raw, first, i - first + 1)
                Case "]"
                    If depth = 0 Then Exit For
            End Select
        End If
    Next i
    Set JsonObjects = out
End Function

Private Function JsonValue(ByVal obj As String, ByVal key As String) As String
    Dim pos As Long, i As Long, ch As String, esc As String
    Dim code As String, result As String
    pos = InStr(1, obj, """" & key & """", vbBinaryCompare)
    If pos = 0 Then Err.Raise vbObjectError + 933, , "Отсутствует поле JSON: " & key
    pos = InStr(pos + Len(key) + 2, obj, ":") + 1
    If pos <= 1 Then Err.Raise vbObjectError + 934, , "Нет разделителя JSON: " & key
    Do While pos <= Len(obj)
        ch = Mid$(obj, pos, 1)
        If ch <> " " And ch <> vbCr And ch <> vbLf And ch <> vbTab Then Exit Do
        pos = pos + 1
    Loop
    If Mid$(obj, pos, 1) <> """" Then
        i = pos
        Do While i <= Len(obj)
            ch = Mid$(obj, i, 1)
            If ch = "," Or ch = "}" Or ch = vbCr Or ch = vbLf Then Exit Do
            i = i + 1
        Loop
        JsonValue = Trim$(Mid$(obj, pos, i - pos))
        Exit Function
    End If

    pos = pos + 1
    Do While pos <= Len(obj)
        ch = Mid$(obj, pos, 1)
        If ch = """" Then Exit Do
        If ch = "\" Then
            pos = pos + 1
            If pos > Len(obj) Then Err.Raise vbObjectError + 935, , "Незавершённая escape-последовательность"
            esc = Mid$(obj, pos, 1)
            Select Case esc
                Case "n": result = result & vbCrLf
                Case "r": result = result & vbCrLf
                Case "t": result = result & vbTab
                Case """": result = result & """"
                Case "\": result = result & "\"
                Case "/": result = result & "/"
                Case "u"
                    code = Mid$(obj, pos + 1, 4)
                    If Len(code) <> 4 Then Err.Raise vbObjectError + 936, , "Неполная Unicode escape"
                    result = result & ChrW$(CLng("&H" & code))
                    pos = pos + 4
                Case Else
                    Err.Raise vbObjectError + 937, , "Неизвестная JSON escape: " & esc
            End Select
        Else
            result = result & ch
        End If
        pos = pos + 1
    Loop
    JsonValue = result
End Function
