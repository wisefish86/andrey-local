#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Импорт финального TrackList CSV обратно в MP3 по колонке «ПолныйПуть».

Сценарий:
    py import_tracklist.py --check --csv TrackList_ИТОГОВЫЙ_ДЛЯ_ИМПОРТА.csv
    py import_tracklist.py --apply --csv TrackList_ИТОГОВЫЙ_ДЛЯ_ИМПОРТА.csv

Перед --apply выполняется полный preflight. Если хотя бы один путь отсутствует,
дублируется или CSV имеет неверную структуру, ни один MP3 не изменяется.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path

try:
    import mutagen.id3 as id3
    from mutagen.id3 import ID3
except ImportError:
    print("Mutagen is not installed.")
    print("Run: py -m pip install mutagen")
    raise SystemExit(2)

from update_tags import load_tags, read_frame_values, write_frame_values


PATH_COLUMN = "ПолныйПуть"

EXPECTED_COLUMNS = [
    "Индекс",
    "Исполнитель",
    "Название",
    "НазваниеЧистое",
    "Альбом",
    "АльбомАртист",
    "Год",
    "Жанр",
    "Настроение",
    "Теги",
    "Ситуация",
    "Комментарий",
    "Композитор",
    "АвторСлов",
    "Издатель",
    "Рейтинг",
    "WWW",
    "WWWSOURCE",
    PATH_COLUMN,
]

# kind:
# - text: standard ID3 text frame
# - txxx: custom TXXX frame
# - comment: COMM
# - url: standard URL frame
# - wxxx: user-defined URL
# - rating: POPM rating byte; blank keeps the current rating
FIELDS = [
    ("Исполнитель", "text", "TPE1", False),
    ("Название", "text", "TIT2", False),
    ("НазваниеЧистое", "text", "MVNM", False),
    ("Альбом", "text", "TALB", False),
    ("АльбомАртист", "text", "TPE2", False),
    ("Год", "text", "TDRC", False),
    ("Жанр", "text", "TCON", False),
    ("Настроение", "text", "TMOO", False),
    ("Теги", "text", "TIT1", True),
    ("Ситуация", "txxx", "TXXX:OCCASION", False),
    ("Комментарий", "comment", "COMM", False),
    ("Композитор", "text", "TCOM", False),
    ("АвторСлов", "text", "TEXT", False),
    ("Издатель", "text", "TPUB", False),
    ("Рейтинг", "rating", "POPM", False),
    ("WWW", "wxxx", "WXXX", False),
    ("WWWSOURCE", "url", "WOAS", False),
]


def clean(value) -> str:
    return (value or "").strip()


def split_multi(value: str) -> list[str]:
    return [part.strip() for part in value.split(";") if part.strip()]


def read_csv(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        headers = reader.fieldnames or []
        if headers != EXPECTED_COLUMNS:
            missing = [x for x in EXPECTED_COLUMNS if x not in headers]
            extra = [x for x in headers if x not in EXPECTED_COLUMNS]
            raise ValueError(
                "Unexpected CSV columns/order.\n"
                f"Expected: {EXPECTED_COLUMNS}\n"
                f"Actual:   {headers}\n"
                f"Missing:  {missing or 'none'}\n"
                f"Extra:    {extra or 'none'}"
            )
        rows = list(reader)

    if not rows:
        raise ValueError("CSV has no data rows.")
    return rows


def preflight(rows: list[dict[str, str]]) -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()
    problems: list[str] = []

    for n, row in enumerate(rows, start=2):
        raw = clean(row.get(PATH_COLUMN)).strip('"')
        if not raw:
            problems.append(f"CSV line {n}: empty {PATH_COLUMN}")
            continue

        path = Path(raw)
        key = str(path).casefold()
        if key in seen:
            problems.append(f"CSV line {n}: duplicate path: {path}")
        seen.add(key)

        if path.suffix.lower() != ".mp3":
            problems.append(f"CSV line {n}: not MP3: {path}")
        elif not path.is_file():
            problems.append(f"CSV line {n}: file not found: {path}")

        rating = clean(row.get("Рейтинг"))
        if rating:
            try:
                value = int(rating)
                if not 0 <= value <= 255:
                    raise ValueError
            except ValueError:
                problems.append(
                    f"CSV line {n}: rating must be integer 0..255 or empty: {rating!r}"
                )

        year = clean(row.get("Год"))
        if year and not year.isdigit():
            problems.append(f"CSV line {n}: year is not numeric: {year!r}")

        paths.append(path)

    if problems:
        preview = "\n".join(problems[:50])
        more = len(problems) - 50
        if more > 0:
            preview += f"\n... and {more} more problem(s)"
        raise ValueError(f"Preflight failed ({len(problems)} problem(s)):\n{preview}")

    return paths


def read_comment(tags: ID3) -> str:
    values: list[str] = []
    for frame in tags.getall("COMM"):
        text = getattr(frame, "text", [])
        if isinstance(text, (list, tuple)):
            values.extend(str(x).strip() for x in text if str(x).strip())
        elif str(text).strip():
            values.append(str(text).strip())
    return "; ".join(values)


def write_comment(tags: ID3, value: str) -> None:
    tags.delall("COMM")
    if value:
        tags.add(id3.COMM(encoding=3, lang="eng", desc="", text=[value]))


def read_url(tags: ID3, frame_name: str) -> str:
    frames = tags.getall(frame_name)
    if not frames:
        return ""
    return clean(getattr(frames[0], "url", ""))


def write_url(tags: ID3, frame_name: str, value: str) -> None:
    tags.delall(frame_name)
    if value:
        frame_class = getattr(id3, frame_name)
        tags.add(frame_class(url=value))


def read_wxxx(tags: ID3) -> str:
    frames = tags.getall("WXXX")
    if not frames:
        return ""
    return clean(getattr(frames[0], "url", ""))


def write_wxxx(tags: ID3, value: str) -> None:
    tags.delall("WXXX")
    if value:
        tags.add(id3.WXXX(encoding=3, desc="", url=value))


RATING_OWNER = "Windows Media Player 9 Series"


def _preferred_popm(tags: ID3):
    frames = tags.getall("POPM")
    for frame in frames:
        if clean(getattr(frame, "email", "")).casefold() == RATING_OWNER.casefold():
            return frame
    return frames[0] if frames else None


def read_rating(tags: ID3) -> str:
    frame = _preferred_popm(tags)
    if frame is None:
        return ""
    rating = int(getattr(frame, "rating", 0) or 0)
    return "" if rating == 0 else str(rating)


def write_rating(tags: ID3, value: str) -> None:
    frame = _preferred_popm(tags)

    # Blank rating is skipped in normal import. This branch is mainly for rollback.
    if not value:
        if frame is not None:
            frame.rating = 0
        return

    rating = int(value)
    if frame is not None:
        frame.rating = rating
        return

    tags.add(id3.POPM(email=RATING_OWNER, rating=rating, count=0))


def desired_values(row: dict[str, str], column: str, multi: bool):
    value = clean(row.get(column))
    if multi:
        return split_multi(value)
    return value


def read_field(tags: ID3, kind: str, frame_name: str, multi: bool):
    if kind in {"text", "txxx"}:
        values = read_frame_values(tags, frame_name)
        if multi:
            return values
        return values[0] if values else ""
    if kind == "comment":
        return read_comment(tags)
    if kind == "url":
        return read_url(tags, frame_name)
    if kind == "wxxx":
        return read_wxxx(tags)
    if kind == "rating":
        return read_rating(tags)
    raise ValueError(f"Unsupported field kind: {kind}")


def write_field(tags: ID3, kind: str, frame_name: str, multi: bool, desired):
    if kind in {"text", "txxx"}:
        values = desired if multi else ([desired] if desired else [])
        write_frame_values(tags, frame_name, values)
    elif kind == "comment":
        write_comment(tags, desired)
    elif kind == "url":
        write_url(tags, frame_name, desired)
    elif kind == "wxxx":
        write_wxxx(tags, desired)
    elif kind == "rating":
        write_rating(tags, desired)
    else:
        raise ValueError(f"Unsupported field kind: {kind}")


def collect_current_row(csv_row: dict[str, str], tags: ID3) -> dict[str, str]:
    current = {name: "" for name in EXPECTED_COLUMNS}
    current["Индекс"] = clean(csv_row.get("Индекс"))
    current[PATH_COLUMN] = clean(csv_row.get(PATH_COLUMN))

    for column, kind, frame_name, multi in FIELDS:
        value = read_field(tags, kind, frame_name, multi)
        current[column] = "; ".join(value) if isinstance(value, list) else value
    return current


def write_backup(csv_path: Path, rows: list[dict[str, str]], paths: list[Path]) -> Path:
    data_dir = csv_path.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_path = data_dir / f"TrackList_backup_before_import_{stamp}.csv"

    with backup_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=EXPECTED_COLUMNS,
            delimiter=";",
            quoting=csv.QUOTE_ALL,
            lineterminator="\n",
        )
        writer.writeheader()
        for row, path in zip(rows, paths):
            writer.writerow(collect_current_row(row, load_tags(path)))
    return backup_path


def plan_changes(row: dict[str, str], tags: ID3):
    planned = []
    for column, kind, frame_name, multi in FIELDS:
        desired = desired_values(row, column, multi)

        # Blank rating preserves the current POPM/play counter.
        if kind == "rating" and desired == "":
            continue

        current = read_field(tags, kind, frame_name, multi)
        if current != desired:
            planned.append((column, kind, frame_name, multi, current, desired))
    return planned


def verify_changes(path: Path, planned) -> None:
    tags = ID3(path)
    for column, kind, frame_name, multi, _old, desired in planned:
        actual = read_field(tags, kind, frame_name, multi)
        if actual != desired:
            raise RuntimeError(
                f"{column}/{frame_name} verification failed: "
                f"{actual!r} != {desired!r}"
            )


def rollback(path: Path, planned) -> None:
    tags = load_tags(path)
    for _column, kind, frame_name, multi, old, _desired in planned:
        write_field(tags, kind, frame_name, multi, old)
    tags.save(path, v2_version=4)


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Preview only; do not write")
    mode.add_argument("--apply", action="store_true", help="Write tags")
    parser.add_argument("--csv", required=True, help="Path to TrackList CSV")
    parser.add_argument("--limit", type=int, default=0, help="Process first N rows after preflight")
    args = parser.parse_args()

    csv_path = Path(args.csv).resolve()
    if not csv_path.is_file():
        print(f"CSV not found: {csv_path}")
        return 2

    try:
        all_rows = read_csv(csv_path)
        all_paths = preflight(all_rows)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        return 2

    rows = all_rows
    paths = all_paths
    if args.limit > 0:
        rows = rows[: args.limit]
        paths = paths[: args.limit]

    print("MODE:", "WRITE" if args.apply else "CHECK ONLY")
    print("CSV:", csv_path)
    print("ROWS:", len(rows), f"(preflight checked all {len(all_rows)})")
    print("PATH MODE: exact path from CSV column 'ПолныйПуть'")
    print("EMPTY CELLS: clear mapped field; blank Rating preserves current POPM")
    print("-" * 120)

    backup_path = None
    if args.apply:
        try:
            backup_path = write_backup(csv_path, rows, paths)
            print("BACKUP:", backup_path)
        except Exception as exc:
            print(f"BACKUP ERROR: {type(exc).__name__}: {exc}")
            print("Nothing was changed.")
            return 2

    files_changed = 0
    files_unchanged = 0
    fields_changed = 0
    errors = 0

    for index, (row, path) in enumerate(zip(rows, paths), start=1):
        try:
            tags = load_tags(path)
            planned = plan_changes(row, tags)

            if not planned:
                files_unchanged += 1
                print(f"{index:>4}. UNCHANGED   | {path.name}")
                continue

            if args.apply:
                for _column, kind, frame_name, multi, _old, desired in planned:
                    write_field(tags, kind, frame_name, multi, desired)
                tags.save(path, v2_version=4)

                try:
                    verify_changes(path, planned)
                except Exception as verify_exc:
                    try:
                        rollback(path, planned)
                        rollback_note = " | rollback OK"
                    except Exception as rollback_exc:
                        rollback_note = f" | ROLLBACK FAILED: {rollback_exc}"
                    raise RuntimeError(f"{verify_exc}{rollback_note}")

                status = "UPDATED"
            else:
                status = "WILL UPDATE"

            files_changed += 1
            fields_changed += len(planned)
            summary = ", ".join(
                f"{column}: {old if old not in ('', []) else '∅'} -> "
                f"{new if new not in ('', []) else '∅'}"
                for column, _kind, _frame, _multi, old, new in planned
            )
            print(f"{index:>4}. {status:<11} | {path.name} | {summary}")

        except Exception as exc:
            errors += 1
            print(f"{index:>4}. ERROR       | {type(exc).__name__}: {exc} | {path}")
            if args.apply:
                print("Apply stopped on first error. Remaining files were not touched.")
                break

    print("-" * 120)
    print("Rows selected:", len(rows))
    print("Files changed/planned:", files_changed)
    print("Fields changed/planned:", fields_changed)
    print("Files unchanged:", files_unchanged)
    print("Errors:", errors)
    if backup_path:
        print("Backup CSV:", backup_path)

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
