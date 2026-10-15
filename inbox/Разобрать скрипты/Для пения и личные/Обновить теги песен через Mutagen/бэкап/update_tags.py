#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Обновляет поле "Блок" в MP3.

В конкретной структуре этих файлов:
    FILEPATH — абсолютный путь к MP3;
    TPE2     — поле, в котором TagScanner хранит "Блок".

TIT1 не трогается: в нём находятся пользовательские теги
(аудитория, сложность, знание текста, язык и т. д.).
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

try:
    from mutagen.id3 import ID3, ID3NoHeaderError, TPE2
except ImportError:
    print("Mutagen не установлен.")
    print("Выполните: py -m pip install mutagen")
    raise SystemExit(2)


def read_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        required = {"FILEPATH", "TPE2"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                "В CSV отсутствуют колонки: " + ", ".join(sorted(missing))
            )
        return list(reader)


def read_tpe2(file_path: Path) -> str:
    try:
        tags = ID3(file_path)
    except ID3NoHeaderError:
        return ""

    frames = tags.getall("TPE2")
    if not frames or not frames[0].text:
        return ""
    return str(frames[0].text[0])


def write_tpe2(file_path: Path, value: str) -> None:
    try:
        tags = ID3(file_path)
    except ID3NoHeaderError:
        tags = ID3()

    tags.delall("TPE2")
    tags.add(TPE2(encoding=3, text=[value]))
    tags.save(file_path, v2_version=4)


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Проверка без записи")
    mode.add_argument("--apply", action="store_true", help="Реальная запись TPE2")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--csv", default="update_tags.csv")
    args = parser.parse_args()

    csv_path = Path(args.csv).resolve()
    if not csv_path.exists():
        print(f"CSV не найден: {csv_path}")
        return 2

    rows = read_rows(csv_path)
    if args.limit > 0:
        rows = rows[:args.limit]

    changed = unchanged = missing = errors = 0
    print("Режим:", "РЕАЛЬНАЯ ЗАПИСЬ" if args.apply else "ПРОВЕРКА БЕЗ ЗАПИСИ")
    print("-" * 100)

    for index, row in enumerate(rows, start=1):
        file_path = Path((row.get("FILEPATH") or "").strip().strip('"'))
        new_value = (row.get("TPE2") or "").strip()

        if not file_path.exists():
            missing += 1
            print(f"{index:>4}. ФАЙЛ НЕ НАЙДЕН | {file_path}")
            continue

        if file_path.suffix.lower() != ".mp3":
            errors += 1
            print(f"{index:>4}. НЕ MP3           | {file_path}")
            continue

        if not new_value:
            errors += 1
            print(f"{index:>4}. ПУСТОЙ TPE2      | {file_path}")
            continue

        try:
            old_value = read_tpe2(file_path)

            if old_value == new_value:
                unchanged += 1
                print(f"{index:>4}. БЕЗ ИЗМЕНЕНИЙ   | {old_value} | {file_path.name}")
                continue

            if args.apply:
                write_tpe2(file_path, new_value)
                verified = read_tpe2(file_path)
                if verified != new_value:
                    raise RuntimeError(
                        f"Проверка записи не пройдена: '{verified}' вместо '{new_value}'"
                    )
                status = "ОБНОВЛЕНО"
            else:
                status = "БУДЕТ ОБНОВЛЕНО"

            changed += 1
            print(
                f"{index:>4}. {status:<17} | "
                f"{old_value or '∅'} -> {new_value} | {file_path.name}"
            )

        except Exception as exc:
            errors += 1
            print(f"{index:>4}. ОШИБКА | {type(exc).__name__}: {exc} | {file_path}")

    print("-" * 100)
    print(f"Строк обработано: {len(rows)}")
    print(f"Изменений: {changed}")
    print(f"Уже совпадали: {unchanged}")
    print(f"Файлы не найдены: {missing}")
    print(f"Ошибки: {errors}")

    return 1 if missing or errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
