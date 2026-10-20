Attribute VB_Name = "SVGTextToParagraph"
' Название: Преобразовать текст SVG в абзацный
' Модуль: SVGTextToParagraph
' Запуск: Main_SVGTextToParagraph
' Назначение: Преобразует весь импортированный фигурный текст активной страницы
'   в абзацный текст CorelDRAW с возможностью редактирования текста в рамках.
' Использование:
'   1. Откройте SVG в CorelDRAW и сохраните копию как CDR.
'   2. Запустите Main_SVGTextToParagraph.
'   3. Проверьте переносы и переполнение рамок перед печатью.
' Условия: используется активная страница; выполняется преобразование всех текстовых
'   фигурных объектов. Из-за различий импорта SVG размещение текста может измениться.
'   Операция группируется для отмены одним действием; на оригинале не запускать.
Option Explicit

Public Sub Main_SVGTextToParagraph()
    Dim doc As Document
    Dim allTexts As ShapeRange
    Dim item As Shape
    Dim changed As Long
    Dim failures As Long
    Dim errMessage As String
    Dim inGroup As Boolean

    If Application.Documents.Count = 0 Then
        MsgBox "Сначала откройте SVG в CorelDRAW.", vbInformation
        Exit Sub
    End If

    Set doc = ActiveDocument
    Set allTexts = doc.ActivePage.FindShapes(Type:=cdrTextShape, Recursive:=True)
    If allTexts.Count = 0 Then
        MsgBox "Текстовые объекты не найдены.", vbInformation
        Exit Sub
    End If

    On Error GoTo FatalError
    doc.BeginCommandGroup "Преобразовать текст SVG в абзацный"
    inGroup = True

    For Each item In allTexts
        On Error Resume Next
        Err.Clear
        If item.Text.IsArtisticText Then
            item.Text.ConvertToParagraph
            If Err.Number = 0 Then
                changed = changed + 1
            Else
                failures = failures + 1
                Err.Clear
            End If
        End If
        On Error GoTo FatalError
    Next item

Finish:
    If inGroup Then
        doc.EndCommandGroup
        inGroup = False
    End If
    If Len(errMessage) > 0 Then
        MsgBox "Преобразование прервано: " & errMessage & vbCrLf & _
               "Успешно: " & changed & "; ошибок: " & failures, vbExclamation
    Else
        MsgBox "Готово. Преобразовано: " & changed & "; не удалось: " & failures & "." & vbCrLf & _
               "Проверьте переполнение текста и сохраните CDR.", vbInformation
    End If
    Exit Sub

FatalError:
    errMessage = Err.Description
    Resume Finish
End Sub
