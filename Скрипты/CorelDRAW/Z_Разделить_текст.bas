Attribute VB_Name = "Z_Разделить_текст"

Option Explicit

' Название: Разделить текст и создать заглушки
' Модуль: SplitTextAndCreateRect
' Запуск: Разделить_текст_и_создать_заглушки
'
' Назначение:
'   Разделяет текст по пустым строкам на отдельные объекты.
'   Сохраняет локальное форматирование символов.
'   Создаёт серые заглушки по размерам из текста.
'
' Использование:
'   1. Выделите один текстовый объект в CorelDRAW.
'   2. Разделите записи пустыми строками.
'   3. Запустите макрос.
'
' Условия:
'   Поддерживает фигурный и абзацный текст.
'   Исходный объект удаляется после успешного разделения.
'   Все изменения объединяются в одну операцию отмены.
'   Перед первым запуском проверьте макрос на копии документа.

Public Sub Разделить_текст_и_создать_заглушки()

    Dim doc As Document
    Dim Исходный_текст As Shape
    Dim Новый_текст As Shape
    Dim Заглушка As Shape

    Dim Весь_текст As String
    Dim Текст_части As String

    Dim Начало_части As Long
    Dim Конец_части As Long
    Dim Позиция_разделителя As Long
    Dim Длина_текста As Long

    Dim Создано_текстов As Long
    Dim Создано_заглушек As Long

    Dim Позиция_X As Double
    Dim Позиция_Y As Double

    Dim Отступ_от_текста As Double
    Dim Отступ_между_блоками As Double

    Dim Ширина_мм As Double
    Dim Высота_мм As Double
    Dim Размеры_найдены As Boolean

    Dim Ширина_заглушки As Double
    Dim Высота_заглушки As Double
    Dim Высота_блока As Double

    Dim Команда_начата As Boolean
    Dim Номер_ошибки As Long
    Dim Текст_ошибки As String

    If Documents.count = 0 Then
        MsgBox "Нет открытого документа.", vbExclamation
        Exit Sub
    End If

    Set doc = ActiveDocument

    If ActiveSelectionRange.count <> 1 Then
        MsgBox "Выделите один текстовый объект.", vbExclamation
        Exit Sub
    End If

    Set Исходный_текст = ActiveSelectionRange(1)

    If Исходный_текст.Type <> cdrTextShape Then
        MsgBox "Выделенный объект не является текстом.", vbExclamation
        Exit Sub
    End If

    Select Case Исходный_текст.Text.Type

        Case cdrParagraphText
            ' Абзацный текст.

        Case cdrArtisticText
            ' Фигурный текст.

        Case Else
            MsgBox "Неподдерживаемый тип текста.", vbExclamation
            Exit Sub

    End Select

    Весь_текст = Исходный_текст.Text.story.Text

    If Len(Trim$(Весь_текст)) = 0 Then
        MsgBox "Текстовый объект пуст.", vbExclamation
        Exit Sub
    End If

    ' Важно: исходную строку не нормализуем,
    ' чтобы индексы символов совпадали с CorelDRAW.

    Длина_текста = Len(Весь_текст)

    Отступ_от_текста = doc.ToUnits(10, cdrMillimeter)
    Отступ_между_блоками = doc.ToUnits(15, cdrMillimeter)

    Позиция_X = Исходный_текст.PositionX
    Позиция_Y = Исходный_текст.PositionY

    On Error GoTo Обработчик_ошибки

    doc.BeginCommandGroup _
        "Разделить текст и создать заглушки"

    Команда_начата = True

    Начало_части = 1

    Do While Начало_части <= Длина_текста

        ' Ищем двойной перевод строки.
        Позиция_разделителя = InStr( _
            Начало_части, _
            Весь_текст, _
            vbCr & vbCr)

        If Позиция_разделителя > 0 Then
            Конец_части = Позиция_разделителя - 1
        Else
            Конец_части = Длина_текста
        End If

        If Конец_части >= Начало_части Then

            Текст_части = Mid$( _
                Весь_текст, _
                Начало_части, _
                Конец_части - Начало_части + 1)

            If Len(Trim$(Текст_части)) > 0 Then

                ' Создаём копию со всем форматированием.
                Set Новый_текст = _
                    Исходный_текст.Duplicate(0, 0)

                ' Удаляем ненужный текст справа.
                ' Удаление выполняем первым, чтобы
                ' не сместить индексы левой границы.

                If Конец_части < Длина_текста Then

                    Новый_текст.Text.story.Characters( _
                        Конец_части + 1, _
                        Длина_текста - Конец_части _
                    ).Delete

                End If

                ' Удаляем ненужный текст слева.
                If Начало_части > 1 Then

                    Новый_текст.Text.story.Characters( _
                        1, _
                        Начало_части - 1 _
                    ).Delete

                End If

                ' Не присваиваем Story.Text:
                ' это уничтожило бы форматирование.

                Новый_текст.SetPosition _
                    Позиция_X, Позиция_Y

                Новый_текст.Name = "@пункт"

                Создано_текстов = Создано_текстов + 1

                ' Определяем размеры по тексту блока.
                Ширина_мм = 0
                Высота_мм = 0
                Размеры_найдены = False

                Получить_размеры_из_текста _
                    Текст_части, _
                    Ширина_мм, _
                    Высота_мм, _
                    Размеры_найдены

                Высота_блока = Новый_текст.SizeHeight

                If Размеры_найдены Then

                    Ширина_заглушки = _
                        doc.ToUnits(Ширина_мм, cdrMillimeter)

                    Высота_заглушки = _
                        doc.ToUnits(Высота_мм, cdrMillimeter)

                    Set Заглушка = _
                        Новый_текст.layer.CreateRectangle2( _
                            Позиция_X, _
                            Позиция_Y - _
                            Новый_текст.SizeHeight - _
                            Отступ_от_текста - _
                            Высота_заглушки, _
                            Ширина_заглушки, _
                            Высота_заглушки)

                    Заглушка.Fill.UniformColor.RGBAssign _
                        220, 220, 220

                    Заглушка.Outline.SetNoOutline
                    Заглушка.Name = "@заглушка"

                    Создано_заглушек = _
                        Создано_заглушек + 1

                    Высота_блока = _
                        Высота_блока + _
                        Отступ_от_текста + _
                        Высота_заглушки

                End If

                Позиция_Y = _
                    Позиция_Y - _
                    Высота_блока - _
                    Отступ_между_блоками

            End If

        End If

        If Позиция_разделителя = 0 Then
            Exit Do
        End If

        Начало_части = Позиция_разделителя + 2

        ' Пропускаем дополнительные пустые строки.
        Do While Начало_части <= Длина_текста

            If Mid$(Весь_текст, Начало_части, 1) <> vbCr Then
                Exit Do
            End If

            Начало_части = Начало_части + 1

        Loop

    Loop

    If Создано_текстов = 0 Then
        Err.Raise vbObjectError + 1000, , _
            "Не удалось создать ни одного текстового блока."
    End If

    ' Удаляем исходник только после создания блоков.
    Исходный_текст.Delete

    doc.EndCommandGroup
    Команда_начата = False

    ActiveWindow.Refresh

    MsgBox _
        "Готово." & vbCrLf & vbCrLf & _
        "Создано текстовых блоков: " & _
        Создано_текстов & vbCrLf & _
        "Создано серых заглушек: " & _
        Создано_заглушек, _
        vbInformation

    Exit Sub

Обработчик_ошибки:

    Номер_ошибки = Err.Number
    Текст_ошибки = Err.Description

    On Error Resume Next

    If Команда_начата Then
        doc.EndCommandGroup
        doc.Undo
    End If

    ActiveWindow.Refresh
    On Error GoTo 0

    MsgBox _
        "Ошибка " & Номер_ошибки & ":" & vbCrLf & _
        Текст_ошибки, _
        vbCritical

End Sub


' ============================================================
' ОПРЕДЕЛЕНИЕ РАЗМЕРОВ ИЗ ТЕКСТА
' ============================================================

Private Sub Получить_размеры_из_текста( _
    ByVal Проверяемый_текст As String, _
    ByRef Ширина As Double, _
    ByRef Высота As Double, _
    ByRef Размеры_найдены As Boolean)

    Dim re As Object
    Dim Совпадения As Object
    Dim Совпадение As Object

    Dim Единица As String
    Dim Число1 As Double
    Dim Число2 As Double

    Размеры_найдены = False
    Ширина = 0
    Высота = 0

    Set re = CreateObject("VBScript.RegExp")

    re.Global = False
    re.IgnoreCase = True

    ' Два размера: ширина x высота.
    re.Pattern = _
        "(\d+([,.]\d+)?)\s*[xх?]\s*" & _
        "(\d+([,.]\d+)?)\s*(мм|cm|см|м)?"

    Set Совпадения = re.Execute(Проверяемый_текст)

    If Совпадения.count > 0 Then

        Set Совпадение = Совпадения(0)

        Число1 = Val(Replace( _
            Совпадение.SubMatches(0), ",", "."))

        Число2 = Val(Replace( _
            Совпадение.SubMatches(2), ",", "."))

        Единица = LCase$(Trim$( _
            Совпадение.SubMatches(4)))

        If Число1 <= 0 Or Число2 <= 0 Then Exit Sub

        Select Case Единица

            Case "м"

                Число1 = Число1 * 1000
                Число2 = Число2 * 1000

            Case "см", "cm"

                Число1 = Число1 * 10
                Число2 = Число2 * 10

            Case "мм"

                ' Размеры уже в миллиметрах.

            Case Else

                ' 2x3 без единиц считаем метрами.
                ' 128x56 без единиц считаем миллиметрами.

                If Число1 <= 5 And Число2 <= 5 Then
                    Число1 = Число1 * 1000
                    Число2 = Число2 * 1000
                End If

        End Select

        Ширина = Число1
        Высота = Число2
        Размеры_найдены = True

        Exit Sub

    End If

    ' Одиночный размер с единицами.
    ' Создаём полосу высотой 5 мм.

    re.Pattern = _
        "(\d+([,.]\d+)?)\s*(мм|cm|см)\b"

    Set Совпадения = re.Execute(Проверяемый_текст)

    If Совпадения.count > 0 Then

        Set Совпадение = Совпадения(0)

        Число1 = Val(Replace( _
            Совпадение.SubMatches(0), ",", "."))

        Единица = LCase$(Совпадение.SubMatches(2))

        If Число1 <= 0 Then Exit Sub

        If Единица = "см" Or Единица = "cm" Then
            Число1 = Число1 * 10
        End If

        Ширина = Число1
        Высота = 5
        Размеры_найдены = True

    End If

End Sub

