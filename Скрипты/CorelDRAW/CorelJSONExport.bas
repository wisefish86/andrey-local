Attribute VB_Name = "CorelJSONExport"
' Название: Экспорт структуры CorelDRAW в JSON
' Модуль: CorelJSONExport
' Запуск: Main_ExportCorelJSON
' Назначение: Выгружает страницы, слои, объекты, текст и стили в UTF-8 JSON.
' Использование:
'   1. Откройте исходный CDR (предпочтительно копию).
'   2. Запустите Main_ExportCorelJSON через диспетчер макросов.
'   3. Укажите путь к JSON и передайте результат для анализа.
' Условия: документ НЕ изменяется. Требуется установленный ADODB.Stream (Windows).
' Внимание: сложные эффекты/спецобъекты могут экспортироваться не полностью.
' Тест: статическая проверка, реальный запуск в CorelDRAW пока не выполнен.
Option Explicit

Private mDoc As Object
Private mShapes As Long
Private mTexts As Long
Private mWarnings As String
Private mWarningCount As Long
Private mMissing As Object

Public Sub Main_ExportCorelJSON()
    Dim doc As Object, pg As Object, ly As Object
    Dim target As String, result As String, pageItems As String, layerItems As String
    Dim commaPage As String, commaLayer As String, stylesJson As String
    On Error GoTo Fatal

    If Application.Documents.Count = 0 Then
        MsgBox "Откройте документ CorelDRAW.", vbExclamation
        Exit Sub
    End If
    Set doc = ActiveDocument
    Set mDoc = doc
    mShapes = 0: mTexts = 0: mWarnings = "": mWarningCount = 0
    Set mMissing = CreateObject("Scripting.Dictionary")

    target = InputBox("Путь для JSON (UTF-8):", "Экспорт CorelDRAW", _
                     Environ$("USERPROFILE") & "\Documents\CorelDRAW_export.json")
    If Len(Trim$(target)) = 0 Then Exit Sub
    If LCase$(Right$(target, 5)) <> ".json" Then target = target & ".json"
    If Len(Dir$(target)) > 0 Then
        If MsgBox("Файл уже существует. Перезаписать?" & vbCrLf & target, _
                  vbQuestion + vbYesNo + vbDefaultButton2) <> vbYes Then Exit Sub
    End If

    pageItems = "": commaPage = ""
    For Each pg In doc.Pages
        layerItems = "": commaLayer = ""
        For Each ly In pg.Layers
            layerItems = layerItems & commaLayer & "{" & _
                """name"":" & JProp(ly, "Name") & "," & _
                """visible"":" & JProp(ly, "Visible") & "," & _
                """printable"":" & JProp(ly, "Printable") & "," & _
                """editable"":" & JProp(ly, "Editable") & "," & _
                """shapes"":" & JShapes(Obj(ly, "Shapes"), 0) & "}"
            commaLayer = ","
        Next ly
        pageItems = pageItems & commaPage & "{" & _
            """index"":" & JProp(pg, "Index") & "," & _
            """name"":" & JProp(pg, "Name") & "," & _
            """sizeMm"":{""width"":" & MM(pg, "SizeWidth") & _
              ",""height"":" & MM(pg, "SizeHeight") & "}," & _
            """layers"": [" & layerItems & "]}"
        commaPage = ","
    Next pg

    stylesJson = JStyleSheet(Obj(doc, "StyleSheet"))

    result = "{" & _
        """schema"":""coreldraw-json-export/v1""," & _
        """exportedAt"":" & Q(Format$(Now, "yyyy-mm-dd\Thh:nn:ss")) & "," & _
        """readOnly"":true," & _
        """document"":{""name"":" & JProp(doc, "Name") & _
            ",""fileName"":" & JProp(doc, "FileName") & _
            ",""unitsEnum"":" & JProp(doc, "Unit") & _
            ",""pagesCount"":" & JProp(doc.Pages, "Count") & "}," & _
        """pages"": [" & pageItems & "]," & _
        """masterLayers"":" & JMasterLayers(doc) & "," & _
        """styleSheet"":" & stylesJson & "," & _
        """missingProperties"":" & JMissing() & "," & _
        """summary"":{""shapes"":" & CStr(mShapes) & ",""textShapes"":" & CStr(mTexts) & _
           ",""warningCount"":" & CStr(mWarningCount) & "}," & _
        """warnings"": [" & mWarnings & "]}"

    SaveUTF8 target, result
    MsgBox "JSON создан: " & target & vbCrLf & _
           "Объектов: " & mShapes & "; текстовых: " & mTexts & _
           "; замечаний: " & mWarningCount & vbCrLf & _
           "Исходный CDR не изменён.", vbInformation
    Exit Sub
Fatal:
    MsgBox "Экспорт не завершён: " & Err.Description & vbCrLf & _
           "Строка/элемент см. через отладчик VBA. CDR не изменён.", vbCritical
End Sub

Private Function JShapes(ByVal shapes As Object, ByVal depth As Long) As String
    Dim sh As Object, s As String, sep As String
    s = "[": sep = ""
    If shapes Is Nothing Then JShapes = "[]": Exit Function
    If depth > 60 Then
        Warn "Превышена глубина вложенности объектов (60)."
        JShapes = "[]": Exit Function
    End If
    On Error GoTo Failed
    For Each sh In shapes
        s = s & sep & JShape(sh, depth)
        sep = ","
    Next sh
    JShapes = s & "]"
    Exit Function
Failed:
    Warn "Не удалось обойти некоторые объекты: " & Err.Description
    JShapes = s & "]"
End Function

Private Function JMasterLayers(ByVal d As Object) As String
    Dim master As Object, layers As Object, layer As Object
    Dim s As String, sep As String
    Set master = Obj(d, "MasterPage")
    If master Is Nothing Then JMasterLayers = "[]": Exit Function
    Set layers = Obj(master, "Layers")
    If layers Is Nothing Then JMasterLayers = "[]": Exit Function
    On Error GoTo Failed
    s = "[": sep = ""
    For Each layer In layers
        s = s & sep & "{" & _
            """name"":" & JProp(layer, "Name") & "," & _
            """visible"":" & JProp(layer, "Visible") & "," & _
            """printable"":" & JProp(layer, "Printable") & "," & _
            """shapes"":" & JShapes(Obj(layer, "Shapes"), 0) & "}"
        sep = ","
    Next layer
    JMasterLayers = s & "]"
    Exit Function
Failed:
    Warn "Не удалось экспортировать мастер-слои: " & Err.Description
    JMasterLayers = s & "]"
End Function

Private Function JEffects(ByVal effects As Object) As String
    Dim eff As Object, s As String, sep As String
    If effects Is Nothing Then JEffects = "[]": Exit Function
    On Error GoTo Failed
    s = "[": sep = ""
    For Each eff In effects
        s = s & sep & "{""typeEnum"":" & JProp(eff, "Type") & "}"
        sep = ","
    Next eff
    JEffects = s & "]"
    Exit Function
Failed:
    Warn "Не все эффекты доступны: " & Err.Description
    JEffects = s & "]"
End Function

Private Function JShape(ByVal sh As Object, ByVal depth As Long) As String
    Dim st As Object, txt As Object, pow As Object
    Dim members As Object, ownLayer As Object, tmp As String
    On Error GoTo Failed
    mShapes = mShapes + 1
    Set st = Obj(sh, "Style")
    Set ownLayer = Obj(sh, "Layer")

    tmp = "{" & _
      """staticId"":" & JProp(sh, "StaticID") & "," & _
      """name"":" & JProp(sh, "Name") & "," & _
      """typeEnum"":" & JProp(sh, "Type") & "," & _
      """layer"":" & JProp(ownLayer, "Name") & "," & _
      """zOrder"":" & JProp(sh, "ZOrder") & "," & _
      """visible"":" & JProp(sh, "Visible") & "," & _
      """locked"":" & JProp(sh, "Locked") & "," & _
      """boundsMm"":{""x"":" & MM(sh, "PositionX") & _
          ",""y"":" & MM(sh, "PositionY") & _
          ",""width"":" & MM(sh, "SizeWidth") & _
          ",""height"":" & MM(sh, "SizeHeight") & "}," & _
      """transform"":{""rotationDeg"":" & JProp(sh, "RotationAngle") & _
          ",""horizontalScale"":" & JProp(sh, "AbsoluteHScale") & _
          ",""verticalScale"":" & JProp(sh, "AbsoluteVScale") & _
          ",""skewDeg"":" & JProp(sh, "AbsoluteSkew") & "}," & _
      """style"":" & JStyleRef(st) & "," & _
      """effects"":" & JEffects(Obj(sh, "Effects")) & "," & _
      """fill"":" & JFill(Obj(sh, "Fill")) & "," & _
      """outline"":" & JOutline(Obj(sh, "Outline")) & "," & _
      """transparency"":{""typeEnum"":" & JProp(Obj(sh, "Transparency"), "Type") & _
          ",""uniform"":" & JProp(Obj(sh, "Transparency"), "Uniform") & "}"

    Set txt = Obj(sh, "Text")
    If Not txt Is Nothing Then
        If Not Obj(txt, "Story") Is Nothing Then
            mTexts = mTexts + 1
            tmp = tmp & ",""text"":" & JText(txt)
        End If
    End If

    Set members = Obj(sh, "Shapes")
    If Not members Is Nothing Then
        If ValProp(members, "Count") > 0 Then
            tmp = tmp & ",""children"":" & JShapes(members, depth + 1)
        End If
    End If
    Set pow = Obj(sh, "PowerClip")
    If Not pow Is Nothing Then
        Set members = Obj(pow, "Shapes")
        If Not members Is Nothing Then
            If ValProp(members, "Count") > 0 Then
                tmp = tmp & ",""powerClipChildren"":" & JShapes(members, depth + 1)
            End If
        End If
    End If
    JShape = tmp & "}"
    Exit Function
Failed:
    Warn "Ошибка объекта: " & Err.Description
    JShape = "{""staticId"":" & JProp(sh, "StaticID") & _
             ",""error"":" & Q(Err.Description) & "}"
End Function

Private Function JText(ByVal t As Object) As String
    Dim story As Object
    Set story = Obj(t, "Story")
    JText = "{" & _
       """isArtistic"":" & JProp(t, "IsArtisticText") & "," & _
       """typeEnum"":" & JProp(t, "Type") & "," & _
       """overflow"":" & JProp(t, "Overflow") & "," & _
       """framesInLink"":" & JProp(t, "FramesInLink") & "," & _
       """content"":" & JProp(story, "Text") & "," & _
       """runs"":" & JRuns(story) & "," & _
       """paragraphs"":" & JParagraphs(story) & "}"
End Function

' Create continuous runs of characters with identical formatting.
' The text at story level remains authoritative; runs are diagnostic.
Private Function JRuns(ByVal story As Object) As String
    Dim chars As Object, ch As Object
    Dim s As String, delim As String, frag As String, current As String
    Dim fmt As String, lastFmt As String, startAt As Long, count As Long
    On Error GoTo Failed
    Set chars = Obj(story, "Characters")
    If chars Is Nothing Then JRuns = "[]": Exit Function
    s = "[": delim = "": current = "": lastFmt = "": startAt = 1: count = 0
    For Each ch In chars
        frag = StrProp(ch, "Text")
        fmt = JCharFormat(ch)
        If count = 0 Then
            lastFmt = fmt: current = frag: startAt = 1
        ElseIf fmt = lastFmt Then
            current = current & frag
        Else
            s = s & delim & "{""start1"":" & CStr(startAt) & _
                      ",""length"":" & CStr(count - startAt + 1) & _
                      ",""text"":" & Q(current) & ",""format"":" & lastFmt & "}"
            delim = ",": current = frag: lastFmt = fmt: startAt = count + 1
        End If
        count = count + 1
    Next ch
    If count > 0 Then
        s = s & delim & "{""start1"":" & CStr(startAt) & _
                  ",""length"":" & CStr(count - startAt + 1) & _
                  ",""text"":" & Q(current) & ",""format"":" & lastFmt & "}"
    End If
    JRuns = s & "]"
    Exit Function
Failed:
    Warn "Посимвольный экспорт не удался: " & Err.Description
    JRuns = "[]"
End Function

Private Function JCharFormat(ByVal r As Object) As String
    JCharFormat = "{" & _
      """font"":" & JProp(r, "Font") & "," & _
      """sizePt"":" & JProp(r, "Size") & "," & _
      """bold"":" & JProp(r, "Bold") & "," & _
      """italic"":" & JProp(r, "Italic") & "," & _
      """fontStyleEnum"":" & JProp(r, "Style") & "," & _
      """underlineEnum"":" & JProp(r, "Underline") & "," & _
      """strikethroughEnum"":" & JProp(r, "Strikethru") & "," & _
      """overscoreEnum"":" & JProp(r, "Overscore") & "," & _
      """positionEnum"":" & JProp(r, "Position") & "," & _
      """charSpacing"":" & JProp(r, "CharSpacing") & "," & _
      """horizontalShift"":" & JProp(r, "HorizShift") & "," & _
      """characterAngle"":" & JProp(r, "CharAngle") & "," & _
      """rangeKerning"":" & JProp(r, "RangeKerning") & "," & _
      """languageEnum"":" & JProp(r, "LanguageID") & "," & _
      """objectStyle"":" & JStyleRef(Obj(r, "ObjectStyle")) & "," & _
      """fill"":" & JFill(Obj(r, "Fill")) & "}"
End Function

Private Function JParagraphs(ByVal story As Object) As String
    Dim ps As Object, p As Object, s As String, sep As String
    On Error GoTo Failed
    Set ps = Obj(story, "Paragraphs")
    If ps Is Nothing Then JParagraphs = "[]": Exit Function
    s = "[": sep = ""
    For Each p In ps
        s = s & sep & "{" & _
           """start1"":" & JProp(p, "Start") & "," & _
           """end1"":" & JProp(p, "End") & "," & _
           """text"":" & JProp(p, "Text") & "," & _
           """alignmentEnum"":" & JProp(p, "Alignment") & "," & _
           """lineSpacing"":" & JProp(p, "LineSpacing") & "," & _
           """lineSpacingTypeEnum"":" & JProp(p, "LineSpacingType") & "," & _
           """before"":" & JProp(p, "ParaSpacingBefore") & "," & _
           """after"":" & JProp(p, "ParaSpacingAfter") & "," & _
           """firstLineIndent"":" & JProp(p, "FirstLineIndent") & "," & _
           """leftIndent"":" & JProp(p, "LeftIndent") & "," & _
           """rightIndent"":" & JProp(p, "RightIndent") & "," & _
           """style"":" & JStyleRef(Obj(p, "ObjectStyle")) & "}"
        sep = ","
    Next p
    JParagraphs = s & "]"
    Exit Function
Failed:
    Warn "Не удалось выгрузить абзацы: " & Err.Description
    JParagraphs = "[]"
End Function

Private Function JStyleRef(ByVal st As Object) As String
    If st Is Nothing Then JStyleRef = "null": Exit Function
    JStyleRef = "{""name"":" & JProp(st, "Name") & _
                ",""category"":" & JProp(st, "CategoryName") & _
                ",""basedOn"":" & JProp(Obj(st, "BasedOn"), "Name") & "}"
End Function

Private Function JStyleSheet(ByVal sheet As Object) As String
    If sheet Is Nothing Then
        Warn "StyleSheet не доступен."
        JStyleSheet = "null": Exit Function
    End If
    JStyleSheet = "{""styles"":" & JStyles(Obj(sheet, "AllStyles")) & _
                  ",""styleSets"":" & JStyles(Obj(sheet, "AllStyleSets")) & _
                  ",""colorStyles"":" & JColorStyles(Obj(sheet, "AllColorStyles")) & "}"
End Function

Private Function JStyles(ByVal collection As Object) As String
    Dim st As Object, s As String, sep As String, raw As String
    On Error GoTo Failed
    If collection Is Nothing Then JStyles = "[]": Exit Function
    s = "[": sep = ""
    For Each st In collection
        raw = MethodText(st, "ToString")
        s = s & sep & "{" & _
           """name"":" & JProp(st, "Name") & "," & _
           """displayName"":" & JProp(st, "DisplayName") & "," & _
           """category"":" & JProp(st, "CategoryName") & "," & _
           """basedOn"":" & JProp(Obj(st, "BasedOn"), "Name") & "," & _
           """rawProperties"":" & Q(raw) & "}"
        sep = ","
    Next st
    JStyles = s & "]"
    Exit Function
Failed:
    Warn "Неполный экспорт каталога стилей: " & Err.Description
    JStyles = s & "]"
End Function

Private Function JColorStyles(ByVal collection As Object) As String
    Dim st As Object, s As String, sep As String
    On Error GoTo Failed
    If collection Is Nothing Then JColorStyles = "[]": Exit Function
    s = "[": sep = ""
    For Each st In collection
        s = s & sep & "{""name"":" & JProp(st, "Name") & _
          ",""color"":" & JColor(Obj(st, "Color")) & "}"
        sep = ","
    Next st
    JColorStyles = s & "]"
    Exit Function
Failed:
    Warn "Неполный экспорт цветовых стилей: " & Err.Description
    JColorStyles = s & "]"
End Function

Private Function JFill(ByVal f As Object) As String
    If f Is Nothing Then JFill = "null": Exit Function
    JFill = "{""typeEnum"":" & JProp(f, "Type") & _
            ",""uniformColor"":" & JColor(Obj(f, "UniformColor")) & "}"
End Function

Private Function JOutline(ByVal o As Object) As String
    If o Is Nothing Then JOutline = "null": Exit Function
    JOutline = "{""typeEnum"":" & JProp(o, "Type") & _
        ",""width"":" & JProp(o, "Width") & _
        ",""color"":" & JColor(Obj(o, "Color")) & "}"
End Function

Private Function JColor(ByVal c As Object) As String
    If c Is Nothing Then JColor = "null": Exit Function
    JColor = "{""typeEnum"":" & JProp(c, "Type") & _
            ",""modelEnum"":" & JProp(c, "Model") & _
            ",""name"":" & JProp(c, "Name") & _
            ",""rgb"":{""r"":" & JProp(c, "RGBRed") & _
            ",""g"":" & JProp(c, "RGBGreen") & _
            ",""b"":" & JProp(c, "RGBBlue") & "}," & _
            """cmyk"":{""c"":" & JProp(c, "CMYKCyan") & _
            ",""m"":" & JProp(c, "CMYKMagenta") & _
            ",""y"":" & JProp(c, "CMYKYellow") & _
            ",""k"":" & JProp(c, "CMYKBlack") & "}}"
End Function

Private Function Obj(ByVal source As Object, ByVal member As String) As Object
    On Error Resume Next
    If source Is Nothing Then Exit Function
    Set Obj = CallByName(source, member, VbGet)
    Err.Clear
End Function

Private Function ValProp(ByVal source As Object, ByVal member As String) As Double
    Dim v As Variant
    On Error Resume Next
    If source Is Nothing Then Exit Function
    v = CallByName(source, member, VbGet)
    If Err.Number = 0 And IsNumeric(v) Then ValProp = CDbl(v)
    Err.Clear
End Function

Private Function StrProp(ByVal source As Object, ByVal member As String) As String
    Dim v As Variant
    On Error Resume Next
    If source Is Nothing Then Exit Function
    v = CallByName(source, member, VbGet)
    If Err.Number = 0 Then
        If Not IsNull(v) Then StrProp = CStr(v)
    End If
    Err.Clear
End Function

Private Function MethodText(ByVal source As Object, ByVal member As String) As String
    Dim v As Variant
    On Error Resume Next
    v = CallByName(source, member, VbMethod)
    If Err.Number = 0 Then
        If Not IsNull(v) Then MethodText = CStr(v)
    End If
    Err.Clear
End Function

Private Function JProp(ByVal source As Object, ByVal member As String) As String
    Dim v As Variant
    On Error GoTo Missing
    If source Is Nothing Then GoTo Missing
    v = CallByName(source, member, VbGet)
    If IsNull(v) Or IsEmpty(v) Then GoTo Missing
    Select Case VarType(v)
       Case vbBoolean
           If v Then JProp = "true" Else JProp = "false"
       Case vbByte, vbInteger, vbLong, vbSingle, vbDouble, vbCurrency, vbDecimal
           JProp = N(CDbl(v))
       Case vbString
           JProp = Q(CStr(v))
       Case Else
           JProp = Q(CStr(v))
    End Select
    Exit Function
Missing:
    If Err.Number <> 0 Then RecordMissing source, member
    JProp = "null"
End Function

Private Sub RecordMissing(ByVal source As Object, ByVal member As String)
    Dim key As String
    On Error Resume Next
    If source Is Nothing Or mMissing Is Nothing Then Exit Sub
    key = TypeName(source) & "." & member
    If mMissing.Exists(key) Then
        mMissing(key) = CLng(mMissing(key)) + 1
    Else
        mMissing.Add key, 1
    End If
End Sub

Private Function JMissing() As String
    Dim key As Variant, s As String, delim As String
    s = "{": delim = ""
    If Not mMissing Is Nothing Then
        For Each key In mMissing.Keys
            s = s & delim & Q(CStr(key)) & ":" & CStr(mMissing(key))
            delim = ","
        Next key
    End If
    JMissing = s & "}"
End Function

Private Function MM(ByVal obj As Object, ByVal prop As String) As String
    Dim v As Variant
    On Error GoTo Missing
    v = CallByName(obj, prop, VbGet)
    If Not IsNumeric(v) Then GoTo Missing
    MM = N(CDbl(mDoc.FromUnits(CDbl(v), cdrMillimeter)))
    Exit Function
Missing:
    MM = "null"
End Function

Private Function N(ByVal value As Double) As String
    ' JSON uses '.' regardless of system locale.
    N = Replace$(Format$(value, "0.############"), ",", ".")
End Function

Private Function Q(ByVal value As String) As String
    Dim i As Long, u As Long, ch As String, out As String
    out = """"
    For i = 1 To Len(value)
        ch = Mid$(value, i, 1)
        u = AscW(ch): If u < 0 Then u = u + 65536
        Select Case u
           Case 34: out = out & "\"""
           Case 92: out = out & "\\"
           Case 8:  out = out & "\b"
           Case 9:  out = out & "\t"
           Case 10: out = out & "\n"
           Case 12: out = out & "\f"
           Case 13: out = out & "\r"
           Case 0 To 31: out = out & "\u" & Right$("0000" & Hex$(u), 4)
           Case Else: out = out & ch
        End Select
    Next i
    Q = out & """"
End Function

Private Sub Warn(ByVal msg As String)
    If mWarningCount < 500 Then
        If Len(mWarnings) <> 0 Then mWarnings = mWarnings & ","
        mWarnings = mWarnings & Q(msg)
    End If
    mWarningCount = mWarningCount + 1
End Sub

Private Sub SaveUTF8(ByVal path As String, ByVal data As String)
    Dim stream As Object
    Set stream = CreateObject("ADODB.Stream")
    stream.Type = 2               ' adTypeText
    stream.Charset = "utf-8"
    stream.Open
    stream.WriteText data
    stream.SaveToFile path, 2     ' adSaveCreateOverWrite
    stream.Close
End Sub
