#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Universal CSV -> MP3 ID3 importer using shared singing ID3 helpers."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

TOOL_ROOT = Path(__file__).resolve().parents[1]
PENIE_ROOT = Path(__file__).resolve().parents[2]
if str(PENIE_ROOT) not in sys.path:
    sys.path.insert(0, str(PENIE_ROOT))

try:
    import mutagen.id3 as id3
except ImportError:
    print("Mutagen is not installed. Run: py -m pip install mutagen")
    raise SystemExit(2)

from _common.id3_io import clean, load_tags, preferred_popm, read_field, split_multi, write_field

DEFAULT_CONFIG = TOOL_ROOT / "config" / "tag_mapping.json"


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        config = json.load(f)
    if not isinstance(config.get("fields"), dict):
        raise ValueError("Config must contain object: fields")
    return config


def direct_spec(column: str) -> dict[str, Any] | None:
    name = column.strip()
    if name.startswith("TXXX:") and name.partition(":")[2].strip():
        return {"kind": "txxx", "frame": name, "empty": "clear"}
    if name.startswith("WXXX:") and name.partition(":")[2].strip():
        return {"kind": "wxxx", "frame": "WXXX", "description": name.partition(":")[2].strip(), "empty": "clear"}
    if name == "WXXX":
        return {"kind": "wxxx", "frame": "WXXX", "description": "", "empty": "clear"}
    if name == "COMM":
        return {"kind": "comment", "frame": "COMM", "empty": "clear"}
    if name == "POPM":
        return {"kind": "rating", "frame": "POPM", "empty": "preserve", "validator": "rating_0_255"}
    frame_class = getattr(id3, name, None)
    if frame_class is None:
        return None
    if name.startswith("T") and name != "TXXX":
        return {"kind": "text", "frame": name, "empty": "clear"}
    if name.startswith("W") and name != "WXXX":
        return {"kind": "url", "frame": name, "empty": "clear"}
    return None


def resolve_columns(headers: list[str], config: dict[str, Any]):
    path_aliases = config.get("path_columns") or ["ПолныйПуть", "FILEPATH"]
    ignore_columns = set(config.get("ignore_columns") or [])
    mapping = config["fields"]
    allow_direct = bool(config.get("direct_id3_columns", True))
    path_column = next((name for name in path_aliases if name in headers), None)
    if not path_column:
        raise ValueError("CSV has no path column. Expected one of: " + ", ".join(path_aliases))

    resolved = []
    unknown = []
    targets: dict[tuple[str, str, str], str] = {}
    for column in headers:
        if column == path_column or column in ignore_columns:
            continue
        spec = mapping.get(column) or (direct_spec(column) if allow_direct else None)
        if spec is None:
            unknown.append(column)
            continue
        kind, frame, desc = clean(spec.get("kind")), clean(spec.get("frame")), clean(spec.get("description"))
        if not kind or not frame:
            raise ValueError(f"Invalid mapping for column {column!r}: {spec!r}")
        key = (kind, frame.casefold(), desc.casefold())
        if key in targets:
            raise ValueError(f"Two CSV columns target the same ID3 field: {targets[key]!r} and {column!r}")
        targets[key] = column
        resolved.append((column, dict(spec)))
    if unknown:
        raise ValueError("Unknown CSV columns. Add them to config/tag_mapping.json or use direct ID3 frame names: " + ", ".join(unknown))
    if not resolved:
        raise ValueError("CSV contains no tag columns to import.")
    return path_column, resolved


def read_csv(csv_path: Path, delimiter: str):
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter=delimiter)
        try:
            headers = [x.strip() for x in next(reader)]
        except StopIteration:
            raise ValueError("CSV is empty.")
        if not headers or any(not x for x in headers):
            raise ValueError("CSV contains an empty header.")
        if len(headers) != len(set(headers)):
            duplicates = sorted({x for x in headers if headers.count(x) > 1})
            raise ValueError("Duplicate CSV headers: " + ", ".join(duplicates))
        rows = []
        for line_no, values in enumerate(reader, start=2):
            if len(values) != len(headers):
                raise ValueError(f"CSV line {line_no}: {len(values)} columns, expected {len(headers)}")
            rows.append(dict(zip(headers, values)))
    if not rows:
        raise ValueError("CSV has no data rows.")
    return headers, rows


def validate_value(column: str, value: str, spec: dict[str, Any], line_no: int):
    validator = spec.get("validator")
    if not value:
        return
    if validator == "year" and (not value.isdigit() or not 1000 <= int(value) <= 2999):
        raise ValueError(f"CSV line {line_no}: invalid year in {column}: {value!r}")
    if validator == "rating_0_255":
        try:
            rating = int(value)
        except ValueError:
            rating = -1
        if not 0 <= rating <= 255:
            raise ValueError(f"CSV line {line_no}: rating in {column} must be integer 0..255: {value!r}")


def preflight(rows, path_column, resolved):
    paths, seen, problems = [], set(), []
    for line_no, row in enumerate(rows, start=2):
        raw = clean(row.get(path_column)).strip('"')
        if not raw:
            problems.append(f"CSV line {line_no}: empty {path_column}")
            continue
        path = Path(raw)
        key = str(path).casefold()
        if key in seen:
            problems.append(f"CSV line {line_no}: duplicate path: {path}")
        seen.add(key)
        if path.suffix.lower() != ".mp3":
            problems.append(f"CSV line {line_no}: not MP3: {path}")
        elif not path.is_file():
            problems.append(f"CSV line {line_no}: file not found: {path}")
        for column, spec in resolved:
            try:
                validate_value(column, clean(row.get(column)), spec, line_no)
            except ValueError as exc:
                problems.append(str(exc))
        paths.append(path)
    if problems:
        preview = "\n".join(problems[:50])
        rest = len(problems) - 50
        if rest > 0:
            preview += f"\n... and {rest} more problem(s)"
        raise ValueError(f"Preflight failed ({len(problems)} problem(s)):\n{preview}")
    return paths


def desired_value(raw: str, spec: dict[str, Any]):
    value = clean(raw)
    return split_multi(value) if spec.get("multi") else value


def plan_changes(row, tags, resolved):
    planned = []
    for column, spec in resolved:
        desired = desired_value(row.get(column, ""), spec)
        if desired in ("", []) and spec.get("empty", "clear") == "preserve":
            continue
        current = read_field(tags, spec)
        if current != desired:
            planned.append((column, spec, current, desired))
    return planned


def verify_changes(path: Path, planned):
    tags = load_tags(path)
    for column, spec, _old, desired in planned:
        actual = read_field(tags, spec)
        if actual != desired:
            raise RuntimeError(f"{column}/{spec['frame']} verification failed: {actual!r} != {desired!r}")


def rollback(path: Path, planned):
    tags = load_tags(path)
    for _column, spec, old, _desired in planned:
        if spec["kind"] == "rating" and old == "":
            frame = preferred_popm(tags)
            if frame is not None:
                tags.delall(frame.HashKey)
        else:
            write_field(tags, spec, old)
    tags.save(path, v2_version=4)


def backup_current(csv_path, headers, rows, paths, resolved, path_column):
    backup_dir = csv_path.parent / "data"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_path = backup_dir / f"{csv_path.stem}_backup_before_import_{stamp}.csv"
    with backup_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\n")
        writer.writeheader()
        for source_row, path in zip(rows, paths):
            tags = load_tags(path)
            out = dict(source_row)
            out[path_column] = str(path)
            for column, spec in resolved:
                current = read_field(tags, spec)
                out[column] = "; ".join(current) if isinstance(current, list) else current
            writer.writerow(out)
    return backup_path


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    csv_path, config_path = Path(args.csv).resolve(), Path(args.config).resolve()
    if not csv_path.is_file():
        print(f"CSV not found: {csv_path}")
        return 2
    if not config_path.is_file():
        print(f"Config not found: {config_path}")
        return 2

    try:
        config = load_config(config_path)
        headers, all_rows = read_csv(csv_path, config.get("delimiter", ";"))
        path_column, resolved = resolve_columns(headers, config)
        all_paths = preflight(all_rows, path_column, resolved)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        return 2

    rows, paths = all_rows, all_paths
    if args.limit > 0:
        rows, paths = rows[:args.limit], paths[:args.limit]

    print("MODE:", "WRITE" if args.apply else "CHECK ONLY")
    print("CSV:", csv_path)
    print("ROWS:", len(rows), f"(full preflight: {len(all_rows)})")
    print("PATH COLUMN:", path_column)
    for column, spec in resolved:
        print(f"  {column} -> {spec['frame']} [{spec['kind']}]")
    print("-" * 120)

    backup_path = None
    if args.apply:
        try:
            backup_path = backup_current(csv_path, headers, rows, paths, resolved, path_column)
            print("BACKUP:", backup_path)
        except Exception as exc:
            print(f"BACKUP ERROR: {type(exc).__name__}: {exc}")
            return 2

    changed = unchanged = field_changes = errors = 0
    for index, (row, path) in enumerate(zip(rows, paths), start=1):
        try:
            tags = load_tags(path)
            planned = plan_changes(row, tags, resolved)
            if not planned:
                unchanged += 1
                print(f"{index:>4}. UNCHANGED   | {path.name}")
                continue
            if args.apply:
                for _column, spec, _old, desired in planned:
                    write_field(tags, spec, desired)
                tags.save(path, v2_version=4)
                try:
                    verify_changes(path, planned)
                except Exception as verify_exc:
                    try:
                        rollback(path, planned)
                        note = " | rollback OK"
                    except Exception as rollback_exc:
                        note = f" | ROLLBACK FAILED: {rollback_exc}"
                    raise RuntimeError(f"{verify_exc}{note}")
                status = "UPDATED"
            else:
                status = "WILL UPDATE"
            changed += 1
            field_changes += len(planned)
            summary = ", ".join(f"{column}: {old if old not in ('', []) else '∅'} -> {new if new not in ('', []) else '∅'}" for column, _spec, old, new in planned)
            print(f"{index:>4}. {status:<11} | {path.name} | {summary}")
        except Exception as exc:
            errors += 1
            print(f"{index:>4}. ERROR       | {type(exc).__name__}: {exc} | {path}")
            if args.apply:
                print("Apply stopped on first error.")
                break

    print("-" * 120)
    print("Rows selected:", len(rows))
    print("Files changed/planned:", changed)
    print("Fields changed/planned:", field_changes)
    print("Files unchanged:", unchanged)
    print("Errors:", errors)
    if backup_path:
        print("Backup CSV:", backup_path)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
