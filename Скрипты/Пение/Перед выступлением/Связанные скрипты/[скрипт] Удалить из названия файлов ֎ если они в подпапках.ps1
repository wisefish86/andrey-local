$root = "D:\YandexDisk\Проекты\Пение\Минусы\1. Основной репертуар"

$files = Get-ChildItem -Path $root -Recurse -File |
Where-Object {
    $_.Name -like '*֎*' -and
    $_.FullName -match '\\(Files|Additi0ns)\\'
}

$renamed = 0
$errors = 0

foreach ($file in $files) {

    $newName = $file.Name.Replace('֎', '')

    try {
        Rename-Item -LiteralPath $file.FullName -NewName $newName -ErrorAction Stop

        Write-Host "$($file.Name)  ->  $newName"
        $renamed++
    }
    catch {
        Write-Host "ОШИБКА: $($file.FullName)"
        $errors++
    }
}

Write-Host ""
Write-Host "------------------------------"
Write-Host "Найдено файлов:      $($files.Count)"
Write-Host "Переименовано:       $renamed"
Write-Host "Ошибок:              $errors"
Write-Host "------------------------------"
Write-Host ""

Read-Host "Нажмите Enter для закрытия"