' Название: Импорт текстовых блоков плаката из JSON
' Модуль: CorelParagraphOCRImport
' Запуск: Main_ImportPosterOCR
' Назначение: создание ОДНОЙ страницы CorelDRAW с редактируемыми
' абзацными рамками, соответствующими координатам полного изображения.
' Использование:
'  1. Запустите Main_ImportPosterOCR.
'  2. Выберите JSON. В диалог выбора файла можно вставить полный путь.
'  3. При отсутствии мм и DPI применяется 300 dpi по умолчанию.
'  4. Проверьте макет, предупреждения и сохраните как CDR.
' Условия: импорт создает новый документ и не меняет уже открытые макеты.
' JSON: UTF-8; модуль .bas для русской VBA-системы: Windows-1251.
' Проверка в CorelDRAW 2026 на реальном компьютере еще не проведена.
Option Explicit

Private Const JSON_VERSION As String = "corel-paragraph-ocr/v2"
Private Const MAX_BLOCKS As Long = 2500
Private Const DEFAULT_DPI As Double = 300#
Private Const DEFAULT_FONT_TITLE As String = "PF Din Text Cond Pro Medium"
Private Const DEFAULT_FONT_BOLD As String = "PF Din Text Cond Pro Bold"
Private Const DEFAULT_FONT_BODY As String = "PF Din Text Cond Pro Light"

' Одно действие через штатный графический выбор JSON.
Public Sub Main_ImportPosterOCR()
    Dim selectedFile As String
    selectedFile = CorelScriptTools.GetFileBox( _
        "Файлы JSON (*.json)|*.json|Все файлы (*.*)|*.*", _
        "Импорт текстовых блоков в CorelDRAW", 0)
    If Len(selectedFile) = 0 Then Exit Sub
    Main_ImportPosterOCRFromPath selectedFile
End Sub

' Дополнительный вход для последующего подключения внешнего drag-and-drop
' лаунчера: все операции выполняет тот же единственный модуль VBA.
Public Sub Main_ImportPosterOCRFromPath(ByVal jsonPath As String)
    Dim sourceJson As String, blocks As Collection, block As Variant
    Dim canvasWpx As Double, canvasHpx As Double
    Dim canvasWmm As Double, canvasHmm As Double, dpiX As Double, dpiY As Double
    Dim x As Double, y As Double, w As Double, h As Double
    Dim leftMm As Double, topMm As Double, rightMm As Double, bottomMm As Double
    Dim fontName As String, fontTitle As String, fontBold As String, fontBody As String
    Dim fontPx As Double, pt As Single, initialPt As Single, minPt As Single
    Dim role As String, itemID As String, content As String
    Dim itemCount As Long, overflowCount As Long, shrunkCount As Long
    Dim needsReviewCount As Long, tinyCount As Long
    Dim summary As String
    Dim sh As Shape, d As Document
    Dim isCreated As Boolean, isBad As Boolean
    Dim i As Long

    On Error GoTo ImportError
    If Len(Dir$(jsonPath)) = 0 Then Err.Raise vbObjectError + 810, , "Файл JSON не найден."
    sourceJson = ReadUtf8(jsonPath)
    If FieldValue(sourceJson, "schema") <> JSON_VERSION Then
        Err.Raise vbObjectError + 811, , "Неподдерживаемый формат JSON: нужна схема v2."
    End If

    canvasWpx = NumberValue(FieldValue(sourceJson, "canvas_width_px"))
    canvasHpx = NumberValue(FieldValue(sourceJson, "canvas_height_px"))
    If canvasWpx <= 0 Or canvasHpx <= 0 Then
        Err.Raise vbObjectError + 812, , "Некорректный размер исходного изображения в пикселях."
    End If

    ' У размеров в мм приоритет над DPI; наличие только пикселей не дает мм.
    canvasWmm = NumberValue(FieldValue(sourceJson, "canvas_width_mm"))
    canvasHmm = NumberValue(FieldValue(sourceJson, "canvas_height_mm"))
    dpiX = NumberValue(FieldValue(sourceJson, "dpi_x"))
    dpiY = NumberValue(FieldValue(sourceJson, "dpi_y"))
    If canvasWmm > 0 Then
        If canvasHmm <= 0 Then canvasHmm = canvasWmm * canvasHpx / canvasWpx
    ElseIf dpiX > 0 Then
        canvasWmm = 25.4 * canvasWpx / dpiX
        If dpiY > 0 Then
            canvasHmm = 25.4 * canvasHpx / dpiY
        Else
            canvasHmm = canvasWmm * canvasHpx / canvasWpx
        End If
    Else
        ' При отсутствии явного размера/метаданных DPI — стабильный дефолт.
        canvasWmm = 25.4 * canvasWpx / DEFAULT_DPI
        canvasHmm = 25.4 * canvasHpx / DEFAULT_DPI
    End If
    If canvasWmm < 10 Or canvasHmm < 10 Or _
       canvasWmm > 15000 Or canvasHmm > 15000 Then
        Err.Raise vbObjectError + 813, , "Проверьте размер страницы: недопустимые миллиметры."
    End If
    If Abs(canvasWmm / canvasHmm - canvasWpx / canvasHpx) > 0.004 * canvasWpx / canvasHpx Then
        Err.Raise vbObjectError + 814, , "Размеры в мм и пропорции изображения не совпадают."
    End If

    fontTitle = FieldValue(sourceJson, "font_title")
    fontBold = FieldValue(sourceJson, "font_bold")
    fontBody = FieldValue(sourceJson, "font_body")
    If Len(fontTitle) = 0 Then fontTitle = DEFAULT_FONT_TITLE
    If Len(fontBold) = 0 Then fontBold = DEFAULT_FONT_BOLD
    If Len(fontBody) = 0 Then fontBody = DEFAULT_FONT_BODY

    Set blocks = ReadArrayOfObjects(sourceJson, "blocks")
    If blocks.Count = 0 Or blocks.Count > MAX_BLOCKS Then
        Err.Raise vbObjectError + 815, , "Число текстовых блоков вне допустимого диапазона."
    End If

    ' Проверяем весь JSON до создания документа.
    For Each block In blocks
        itemID = FieldValue(CStr(block), "id")
        content = FieldValue(CStr(block), "text")
        x = NumberValue(FieldValue(CStr(block), "x_px"))
        y = NumberValue(FieldValue(CStr(block), "y_px"))
        w = NumberValue(FieldValue(CStr(block), "width_px"))
        h = NumberValue(FieldValue(CStr(block), "height_px"))
        fontPx = NumberValue(FieldValue(CStr(block), "font_px"))
        If Len(itemID) = 0 Or Len(content) = 0 Or _
           x < 0 Or y < 0 Or w <= 0 Or h <= 0 Or fontPx <= 0 Or _
           x + w > canvasWpx + 2 Or y + h > canvasHpx + 2 Then
            Err.Raise vbObjectError + 816, , "Проблема данных OCR: " & itemID
        End If
    Next block

    Set d = Application.CreateDocument
    isCreated = True
    d.Unit = cdrMillimeter
    d.Pages(1).SetSize canvasWmm, canvasHmm
    d.Pages(1).Activate

    For Each block In blocks
        itemID = FieldValue(CStr(block), "id")
        content = FieldValue(CStr(block), "text")
        role = LCase$(FieldValue(CStr(block), "role"))
        x = NumberValue(FieldValue(CStr(block), "x_px"))
        y = NumberValue(FieldValue(CStr(block), "y_px"))
        w = NumberValue(FieldValue(CStr(block), "width_px"))
        h = NumberValue(FieldValue(CStr(block), "height_px"))
        fontPx = NumberValue(FieldValue(CStr(block), "font_px"))

        leftMm = x / canvasWpx * canvasWmm
        rightMm = (x + w) / canvasWpx * canvasWmm
        topMm = (canvasHpx - y) / canvasHpx * canvasHmm
        bottomMm = (canvasHpx - y - h) / canvasHpx * canvasHmm
        pt = CSng(fontPx * canvasWmm / canvasWpx * 72 / 25.4)
        If pt < 2 Then pt = 2
        If pt > 200 Then pt = 200
        initialPt = pt
        ' Используем реальные начертания PF Din, без синтетического Bold.
        Select Case role
            Case "title", "heading", "subheading"
                fontName = fontTitle
            Case "emphasis", "bold", "highlight"
                fontName = fontBold
            Case Else
                fontName = fontBody
        End Select

        ' Unicode-вариант Corel API: кириллица не превращается в вопросительные знаки.
        Set sh = d.ActiveLayer.CreateParagraphTextWide( _
            leftMm, topMm, rightMm, bottomMm, content, , , _
            fontName, pt)
        sh.Name = "OCR_" & itemID
        itemCount = itemCount + 1

        ' Только уменьшение при переполнении. Ширина/высота рамки не меняются.
        ' Сначала мягкая коррекция до 65% исходного размера.
        minPt = CSng(pt * 0.65)
        If minPt < 2 Then minPt = 2
        i = 0
        Do While sh.Text.Overflow And pt > minPt And i < 125
            pt = CSng(pt - 0.2)
            If pt < minPt Then pt = minPt
            sh.Text.Story.Size = pt
            i = i + 1
        Loop
        If pt + 0.1 < initialPt Then shrunkCount = shrunkCount + 1

        ' Если всё ещё переполнение — штатный Corel Fit Text to Frame,
        ' затем показываем предупреждения по слишком мелкому кеглю.
        If sh.Text.Overflow Then sh.Text.FitTextToFrame
        If sh.Text.Overflow Then overflowCount = overflowCount + 1
        If sh.Text.Story.Size < initialPt * 0.65 Then tinyCount = tinyCount + 1
        If FieldValue(CStr(block), "needs_review") = "true" Then _
            needsReviewCount = needsReviewCount + 1
        If itemCount Mod 10 = 0 Then DoEvents
    Next block

    d.Pages(1).Activate
    summary = "Создана ОДНА страница: " & _
        Format$(canvasWmm, "0.0") & " x " & Format$(canvasHmm, "0.0") & " мм." & vbCrLf & _
        "Редактируемых абзацных рамок: " & CStr(itemCount) & vbCrLf & _
        "Кегль уменьшен: " & CStr(shrunkCount) & vbCrLf & _
        "Слишком сильно уменьшен: " & CStr(tinyCount) & vbCrLf & _
        "Переполнение осталось: " & CStr(overflowCount) & vbCrLf & _
        "OCR-фрагменты для сверки: " & CStr(needsReviewCount) & vbCrLf & vbCrLf & _
        "Проверьте макет и сохраните его в CDR."
    MsgBox summary, vbInformation, "Импорт OCR в CorelDRAW"
    Exit Sub

ImportError:
    summary = "Ошибка импорта: " & Err.Description & vbCrLf & _
        "Объектов успели создать: " & CStr(itemCount) & "."
    If isCreated Then summary = summary & vbCrLf & _
        "Новый документ может быть неполным. Закройте его без сохранения."
    MsgBox summary, vbExclamation, "Импорт OCR"
End Sub

Private Function ReadUtf8(ByVal filePath As String) As String
    Dim inputStream As Object, result As String
    Set inputStream = CreateObject("ADODB.Stream")
    inputStream.Type = 2
    inputStream.Charset = "utf-8"
    inputStream.Open
    inputStream.LoadFromFile filePath
    result = inputStream.ReadText(-1)
    inputStream.Close
    If Len(result) > 0 Then
        If Left$(result, 1) = ChrW$(65279) Then result = Mid$(result, 2)
    End If
    ReadUtf8 = result
End Function

' Небольшой парсер только для текущего OCR-формата:
' верхнеуровневые поля и массив простых объектов, без вложенных блоков.
Private Function ReadArrayOfObjects(ByVal raw As String, ByVal arrayName As String) As Collection
    Dim found As New Collection, pos As Long, i As Long, startPos As Long
    Dim depth As Long, ch As String, escaped As Boolean, quoted As Boolean
    pos = InStr(1, raw, """" & arrayName & """", vbBinaryCompare)
    If pos = 0 Then Err.Raise vbObjectError + 820, , "Не найден массив JSON: " & arrayName
    pos = InStr(pos, raw, "[")
    If pos = 0 Then Err.Raise vbObjectError + 821, , "Нет открывающей скобки массива JSON"
    For i = pos + 1 To Len(raw)
        ch = Mid$(raw, i, 1)
        If quoted Then
            If escaped Then
                escaped = False
            ElseIf ch = "\" Then
                escaped = True
            ElseIf ch = """" Then
                quoted = False
            End If
        Else
            Select Case ch
                Case """"
                    quoted = True
                Case "{"
                    If depth = 0 Then startPos = i
                    depth = depth + 1
                Case "}"
                    depth = depth - 1
                    If depth < 0 Then Err.Raise vbObjectError + 822, , "Неверная вложенность JSON"
                    If depth = 0 Then found.Add Mid$(raw, startPos, i - startPos + 1)
                Case "]"
                    If depth = 0 Then Exit For
            End Select
        End If
    Next i
    If quoted Or depth <> 0 Then Err.Raise vbObjectError + 823, , "Незавершённый массив JSON"
    Set ReadArrayOfObjects = found
End Function

Private Function FieldValue(ByVal src As String, ByVal key As String) As String
    Dim p As Long, q As Long, symbol As String, esc As String
    Dim result As String, unicodeHex As String
    p = InStr(1, src, """" & key & """", vbBinaryCompare)
    If p = 0 Then Err.Raise vbObjectError + 830, , "Не найдено поле JSON: " & key
    p = InStr(p + Len(key) + 2, src, ":")
    If p = 0 Then Err.Raise vbObjectError + 831, , "Нет двоеточия у JSON-поля: " & key
    p = p + 1
    Do While p <= Len(src)
        symbol = Mid$(src, p, 1)
        If symbol <> " " And symbol <> vbTab And symbol <> vbCr And symbol <> vbLf Then Exit Do
        p = p + 1
    Loop
    If Mid$(src, p, 1) <> """" Then
        q = p
        Do While q <= Len(src)
            symbol = Mid$(src, q, 1)
            If symbol = "," Or symbol = "}" Or symbol = vbCr Or symbol = vbLf Then Exit Do
            q = q + 1
        Loop
        FieldValue = Trim$(Mid$(src, p, q - p))
        Exit Function
    End If

    p = p + 1
    Do While p <= Len(src)
        symbol = Mid$(src, p, 1)
        If symbol = """" Then Exit Do
        If symbol = "\" Then
            p = p + 1
            If p > Len(src) Then Err.Raise vbObjectError + 832, , "Ошибка escape в JSON"
            esc = Mid$(src, p, 1)
            Select Case esc
                Case "n": result = result & vbCrLf
                Case "r": result = result & vbCr
                Case "t": result = result & vbTab
                Case """": result = result & """"
                Case "\": result = result & "\"
                Case "/": result = result & "/"
                Case "u"
                    unicodeHex = Mid$(src, p + 1, 4)
                    If Len(unicodeHex) <> 4 Then Err.Raise vbObjectError + 833, , "Unicode escape оборван"
                    result = result & ChrW$(CLng("&H" & unicodeHex))
                    p = p + 4
                Case Else
                    Err.Raise vbObjectError + 834, , "Неизвестная escape-последовательность: " & esc
            End Select
        Else
            result = result & symbol
        End If
        p = p + 1
    Loop
    FieldValue = result
End Function

Private Function NumberValue(ByVal raw As String) As Double
    If LCase$(Trim$(raw)) = "null" Then
        NumberValue = 0
    Else
        NumberValue = Val(Replace$(Trim$(raw), ",", "."))
    End If
End Function
