#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Universal MP3 ID3 tag updater.

CSV format:
    FILEPATH;TPE2;TIT1;TCON;TBPM;TXXX:OCCASION

Rules:
- FILEPATH is the absolute path to the MP3 file.
- Every other column name must be a valid ID3 text frame name.
- Custom text frames use the column format TXXX:DESCRIPTION.
- The script writes each non-empty CSV cell into the matching ID3 frame.
- Multiple values inside one cell are separated by semicolons.
- Empty cells are skipped by default and do not erase existing tags.
- Use --clear-empty if empty cells should remove the corresponding frame.

Examples:
    py update_tags.py --check
    py update_tags.py --apply
    py update_tags.py --apply --limit 10
    py update_tags.py --apply --clear-empty
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

try:
    import mutagen.id3 as id3
    from mutagen.id3 import ID3, ID3NoHeaderError
except ImportError:
    print("Mutagen is not installed.")
    print("Run: py -m pip install mutagen")
    raise SystemExit(2)


PATH_COLUMN = "FILEPATH"


def split_values(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split(";") if part.strip()]


def read_rows(csv_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        headers = [h.strip() for h in (reader.fieldnames or []) if h and h.strip()]

        if PATH_COLUMN not in headers:
            raise ValueError(f"CSV must contain column: {PATH_COLUMN}")

        tag_columns = [h for h in headers if h != PATH_COLUMN]
        if not tag_columns:
            raise ValueError("CSV contains no ID3 tag columns.")

        unsupported = [name for name in tag_columns if not is_supported_frame(name)]
        if unsupported:
            raise ValueError(
                "Unsupported or non-text ID3 frame columns: "
                + ", ".join(unsupported)
            )

        return tag_columns, list(reader)


def get_frame_class(frame_name: str):
    frame_class = getattr(id3, frame_name, None)
    if frame_class is None:
        raise ValueError(f"Unknown ID3 frame: {frame_name}")
    return frame_class


def is_supported_frame(frame_name: str) -> bool:
    if frame_name.startswith("TXXX:"):
        return bool(frame_name.partition(":")[2].strip())

    try:
        frame_class = get_frame_class(frame_name)
    except ValueError:
        return False

    # Universal updater intentionally supports standard text frames only.
    # They expose a 'text' field and accept encoding/text arguments.
    return frame_name.startswith("T") and frame_name not in {"TXXX"}


def read_frame_values(tags: ID3, frame_name: str) -> list[str]:
    if frame_name.startswith("TXXX:"):
        description = frame_name.partition(":")[2]
        frames = [
            frame
            for frame in tags.getall("TXXX")
            if frame.desc.casefold() == description.casefold()
        ]
    else:
        frames = tags.getall(frame_name)
    if not frames:
        return []

    values: list[str] = []
    for frame in frames:
        frame_text = getattr(frame, "text", [])
        if isinstance(frame_text, (list, tuple)):
            values.extend(str(x).strip() for x in frame_text if str(x).strip())
        elif str(frame_text).strip():
            values.append(str(frame_text).strip())
    return values


def write_frame_values(tags: ID3, frame_name: str, values: list[str]) -> None:
    if frame_name.startswith("TXXX:"):
        description = frame_name.partition(":")[2]
        for frame in list(tags.getall("TXXX")):
            if frame.desc.casefold() == description.casefold():
                tags.delall(frame.HashKey)

        if values:
            tags.add(id3.TXXX(encoding=3, desc=description, text=values))
        return

    frame_class = get_frame_class(frame_name)
    tags.delall(frame_name)

    if values:
        tags.add(frame_class(encoding=3, text=values))


def load_tags(path: Path) -> ID3:
    try:
        return ID3(path)
    except ID3NoHeaderError:
        return ID3()


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Check only; do not write")
    mode.add_argument("--apply", action="store_true", help="Write tags")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--csv", default="update_tags.csv")
    parser.add_argument(
        "--clear-empty",
        action="store_true",
        help="Remove a frame when its CSV cell is empty",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv).resolve()
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}")
        return 2

    tag_columns, rows = read_rows(csv_path)
    if args.limit > 0:
        rows = rows[:args.limit]

    files_changed = 0
    files_unchanged = 0
    missing_files = 0
    errors = 0
    fields_changed = 0

    print("MODE:", "WRITE" if args.apply else "CHECK ONLY")
    print("TAG COLUMNS:", ", ".join(tag_columns))
    print("EMPTY CELLS:", "CLEAR FRAME" if args.clear_empty else "SKIP")
    print("-" * 110)

    for index, row in enumerate(rows, start=1):
        path = Path((row.get(PATH_COLUMN) or "").strip().strip('"'))

        if not path.exists():
            missing_files += 1
            print(f"{index:>4}. FILE NOT FOUND | {path}")
            continue

        if path.suffix.lower() != ".mp3":
            errors += 1
            print(f"{index:>4}. NOT MP3        | {path}")
            continue

        try:
            tags = load_tags(path)
            planned: list[tuple[str, list[str], list[str]]] = []

            for frame_name in tag_columns:
                raw_value = row.get(frame_name) or ""
                new_values = split_values(raw_value)

                if not new_values and not args.clear_empty:
                    continue

                old_values = read_frame_values(tags, frame_name)
                if old_values != new_values:
                    planned.append((frame_name, old_values, new_values))

            if not planned:
                files_unchanged += 1
                print(f"{index:>4}. UNCHANGED      | {path.name}")
                continue

            if args.apply:
                for frame_name, _, new_values in planned:
                    write_frame_values(tags, frame_name, new_values)

                # ID3v2.4 preserves multi-value text frames correctly.
                tags.save(path, v2_version=4)

                verify_tags = ID3(path)
                for frame_name, _, new_values in planned:
                    verified = read_frame_values(verify_tags, frame_name)
                    if verified != new_values:
                        raise RuntimeError(
                            f"{frame_name} verification failed: "
                            f"{verified!r} != {new_values!r}"
                        )
                status = "UPDATED"
            else:
                status = "WILL UPDATE"

            files_changed += 1
            fields_changed += len(planned)

            summary = ", ".join(
                f"{name}: {old or ['∅']} -> {new or ['∅']}"
                for name, old, new in planned
            )
            print(f"{index:>4}. {status:<14} | {path.name} | {summary}")

        except Exception as exc:
            errors += 1
            print(
                f"{index:>4}. ERROR          | "
                f"{type(exc).__name__}: {exc} | {path}"
            )

    print("-" * 110)
    print("Rows:", len(rows))
    print("Files changed:", files_changed)
    print("Fields changed:", fields_changed)
    print("Files unchanged:", files_unchanged)
    print("Missing files:", missing_files)
    print("Errors:", errors)

    return 1 if missing_files or errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
