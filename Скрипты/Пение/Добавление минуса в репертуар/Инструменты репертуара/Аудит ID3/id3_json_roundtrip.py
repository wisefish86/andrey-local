"""Compact editable ID3 export and guarded batch import.

Only the metadata fields edited by the repertoire app are writable.
Lyrics, ReplayGain, BPM, ratings, covers and other frames remain untouched.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path, PurePosixPath

from mutagen import id3

TOOL_ROOT = Path(__file__).resolve().parent
APP_ROOT = TOOL_ROOT.parents[1]
sys.path.insert(0, str(APP_ROOT.parent))
from _common.id3_io import (
    clean, load_tags, read_text, read_txxx, read_url, read_wxxx,
    write_text, write_txxx, write_url, write_wxxx,
)

CONFIG_PATH = TOOL_ROOT / "config.json"
MAIN_CONFIG_PATH = APP_ROOT / "config.json"
DATA = TOOL_ROOT / "data"
FORMAT = "andrey_repertoire_gpt"
VERSION = 2
# The main editor hard-codes these five manually editable text/url fields.
# The rest of its fields are dynamically derived from its config.json.
GUI_SIMPLE_FIELDS = frozenset({"TPE1", "MVNM", "TIT2", "TDRC", "WOAS", "TCOM"})
EXCLUDED = {"USLT", "SYLT", "APIC", "GEOB", "PRIV", "COMM"}
UNSAFE_TEXT = {"TIPL", "TMCL", "IPLS"}  # Structured text frames, not plain lists.
BINARY_KEYS = {"MCDI", "ETCO", "MLLT", "SYTC", "RVA2", "EQU2", "UFID", "POPM"}


def digest(value) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def settings() -> tuple[dict, dict]:
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    main = json.loads(MAIN_CONFIG_PATH.read_text(encoding="utf-8-sig"))
    if not isinstance(cfg.get("excluded_folders"), list) or not all(
        isinstance(v, str) and v and "/" not in v and "\\" not in v
        for v in cfg["excluded_folders"]
    ):
        raise ValueError("config.json: excluded_folders must be folder names")
    if not isinstance(cfg.get("gpt_simple_fields"), list):
        raise ValueError("config.json: gpt_simple_fields must be an array")
    limit = cfg.get("max_text_chars")
    if type(limit) is not int or not 1 <= limit <= 100000:
        raise ValueError("config.json: invalid max_text_chars")
    cap = cfg.get("max_changed_tracks")
    if type(cap) is not int or not 1 <= cap <= 100000:
        raise ValueError("config.json: invalid max_changed_tracks")
    cfg["_allowed_fields"] = allowed_fields(cfg, main)
    return cfg, main

def allowed_fields(cfg: dict, main: dict) -> set[str]:
    """The GUI's editable fields are the sole whitelist for GPT exchange."""
    simple = cfg.get("gpt_simple_fields")
    if not isinstance(simple, list) or not all(isinstance(x, str) for x in simple):
        raise ValueError("gpt_simple_fields must be a list of frame names")
    if len(simple) != len(set(simple)) or not set(simple).issubset(GUI_SIMPLE_FIELDS):
        raise ValueError("gpt_simple_fields contains duplicate or non-GUI fields")
    names = set(simple)
    if not isinstance(main.get("fields"), list):
        raise ValueError("Main app config has no managed fields")
    for field in main["fields"]:
        if not isinstance(field, dict) or not isinstance(field.get("storage"), dict):
            raise ValueError("Invalid managed field in main app config")
        storage = field["storage"]
        kind = storage.get("kind")
        frame = storage.get("frame")
        if kind == "tit1_group":
            if frame != "TIT1":
                raise ValueError("Unexpected grouped ID3 frame in GUI: " + str(frame))
            names.add("TIT1")
        elif kind in ("text", "txxx", "url", "wxxx"):
            if not field_is_safe(frame):
                raise ValueError("Unsupported GUI-managed ID3 frame: " + str(frame))
            names.add(frame)
        else:
            raise ValueError("Unexpected field storage in GUI: " + str(kind))
    if not names:
        raise ValueError("GPT field whitelist is empty")
    return names


def field_is_safe(key: str) -> bool:
    if not isinstance(key, str) or len(key) > 160:
        return False
    if key == "MVNM":
        return True  # Movement name: GUI song title, a text frame not starting with T.
    if key.startswith("TXXX:") or key.startswith("WXXX:"):
        return bool(key[5:]) and not any(ord(c) < 32 for c in key[5:])
    if len(key) != 4 or key in EXCLUDED or key in UNSAFE_TEXT or key in BINARY_KEYS:
        return False
    frame_type = getattr(id3, key, None)
    if key.startswith("T") and frame_type and issubclass(frame_type, id3.TextFrame):
        return True
    if key.startswith("W") and frame_type and issubclass(frame_type, id3.UrlFrame):
        return True
    return False


def value_of(tags, key: str):
    if key == "MVNM":
        return read_text(tags, "MVNM")
    if key.startswith("TXXX:"):
        return read_txxx(tags, key)
    if key.startswith("WXXX:"):
        return read_wxxx(tags, key[5:])
    if key.startswith("T"):
        return read_text(tags, key)
    if key.startswith("W"):
        return read_url(tags, key)
    raise ValueError("Unsupported field " + key)


def blank_of(key: str):
    return [] if key.startswith("T") else ""


def write_value(tags, key: str, value):
    if key == "MVNM":
        write_text(tags, "MVNM", value)
    elif key.startswith("TXXX:"):
        write_txxx(tags, key, value)
    elif key.startswith("WXXX:"):
        write_wxxx(tags, key[5:], value)
    elif key.startswith("T"):
        write_text(tags, key, value)
    else:
        write_url(tags, key, value)


def validate_value(key: str, value, maximum: int):
    if key.startswith("T") or key == "MVNM":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ValueError(key + ": expected array of strings (e.g. [\"с-Кавказ\"])")
        if len(value) > 64 or any(len(v) > maximum for v in value):
            raise ValueError(key + ": too many or too long text entries")
    else:
        if not isinstance(value, str) or len(value) > maximum:
            raise ValueError(key + ": expected a short string")


def safe_export_tags(tags, cfg) -> tuple[dict, dict]:
    """Export ONLY managed GUI fields (including currently unset fields)."""
    allowed = cfg["_allowed_fields"]
    values = {}
    for key in sorted(allowed, key=str.casefold):
        value = value_of(tags, key)
        # Never silently omit an editable field; fail the affected track instead.
        validate_value(key, value, cfg["max_text_chars"])
        values[key] = value
    return values, {}


def path_in_root(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or "\\" in relative or "\x00" in relative:
        raise ValueError("Invalid relative_path")
    p = PurePosixPath(relative)
    if not relative or p.is_absolute() or len(p.parts) < 2 or any(
        x in ("", ".", "..") or ":" in x for x in p.parts
    ):
        raise ValueError("Invalid relative_path: " + repr(relative))
    dest = root.joinpath(*p.parts)
    if dest.is_symlink() or any(parent.is_symlink() for parent in dest.parents if parent != root):
        raise ValueError("Symlinks are not allowed: " + relative)
    if not dest.resolve(strict=False).is_relative_to(root.resolve()):
        raise ValueError("Path escapes repertoire root")
    return dest


def identity(relative: str) -> str:
    return hashlib.sha1(relative.encode("utf-8")).hexdigest()[:16]


def iter_mp3(root: Path, marker: str, excluded: set[str]):
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [name for name in dirs
                   if name.casefold() not in excluded
                   and not (Path(current) / name).is_symlink()]
        for name in sorted(files, key=str.casefold):
            path = Path(current) / name
            if path.suffix.casefold() == ".mp3" and marker in name and not path.is_symlink():
                yield path


def export_json(root: Path, marker: str, cfg: dict, output: Path) -> int:
    tracks, errors, skipped_total = [], [], Counter()
    excluded = {v.casefold() for v in cfg["excluded_folders"]}
    for path in iter_mp3(root, marker, excluded):
        try:
            rel = path.relative_to(root).as_posix()
            tag_values, skipped = safe_export_tags(load_tags(path), cfg)
            skipped_total.update(skipped)
            stat = path.stat()
            tracks.append({
                "id": identity(rel), "relative_path": rel,
                "file_size_bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                "tags": tag_values,
                "baseline_hashes": {key: digest(value) for key, value in tag_values.items()},
            })
        except Exception as exc:
            errors.append({"file": str(path), "error": repr(exc)})
    tracks.sort(key=lambda x: x["relative_path"].casefold())
    payload = {
        "schema_version": VERSION, "format": FORMAT,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "library_root": str(root), "marker": marker,
        "excluded_folders": cfg["excluded_folders"],
        "managed_fields": sorted(cfg["_allowed_fields"], key=str.casefold),
        "track_count": len(tracks), "error_count": len(errors),
        "tracks": tracks, "errors": errors,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Экспортировано: {len(tracks)} MP3; ошибок: {len(errors)}")
    print(f"Компактный JSON: {output}")
    return int(bool(errors))


def preflight(root: Path, payload: dict, cfg: dict, marker: str):
    if payload.get("format") != FORMAT or payload.get("schema_version") != VERSION:
        raise ValueError("Wrong JSON format/version; use the editable exporter")
    if payload.get("errors") or payload.get("error_count"):
        raise ValueError("Export contains scan errors; re-export after resolving them")
    if not isinstance(payload.get("tracks"), list):
        raise ValueError("tracks must be an array")
    if str(root.resolve()).casefold() != str(Path(payload.get("library_root", "")).resolve()).casefold():
        raise ValueError("Library root differs from exported snapshot")
    if marker != payload.get("marker"):
        raise ValueError("MP3 marker changed; re-export")
    allowed = cfg["_allowed_fields"]
    if payload.get("managed_fields") != sorted(allowed, key=str.casefold):
        raise ValueError("GUI field schema has changed; re-export for GPT")
    seen, planned, errors = set(), [], []
    exclusions = {v.casefold() for v in cfg["excluded_folders"]}
    for track in payload["tracks"]:
        try:
            rel = track["relative_path"]
            if not isinstance(rel, str) or rel.casefold() in seen:
                raise ValueError("duplicate/invalid relative_path")
            seen.add(rel.casefold())
            path = path_in_root(root, rel)
            if any(part.casefold() in exclusions for part in PurePosixPath(rel).parts[:-1]):
                raise ValueError("The MP3 is now in an excluded directory")
            if marker not in path.name or path.suffix.casefold() != ".mp3":
                raise ValueError("Invalid MP3 marker or suffix")
            if identity(rel) != track.get("id"):
                raise ValueError("Track ID does not match its relative path")
            desired = track["tags"]
            baselines = track["baseline_hashes"]
            if not isinstance(desired, dict) or not isinstance(baselines, dict):
                raise ValueError("tags/baseline_hashes must be objects")
            if set(desired) != allowed or set(baselines) != allowed:
                raise ValueError("GPT tag keys changed or contain forbidden frames; re-export")
            if not path.is_file():
                raise ValueError("Source MP3 missing")
            stat = path.stat()
            if stat.st_size != track.get("file_size_bytes") or stat.st_mtime_ns != track.get("mtime_ns"):
                raise ValueError("Source MP3 changed since export; re-export first")
            tags = load_tags(path)
            changes = []
            for key, desired_value in desired.items():
                if key not in allowed or not field_is_safe(key):
                    raise ValueError("Tag is not managed by the repertoire editor: " + key)
                validate_value(key, desired_value, cfg["max_text_chars"])
                old_hash = baselines[key]
                if not isinstance(old_hash, str) or len(old_hash) != 64:
                    raise ValueError("Invalid baseline_hash for " + key)
                if digest(value_of(tags, key)) != old_hash:
                    raise ValueError("Conflicting tag changed since export: " + key)
                if digest(desired_value) != old_hash:
                    changes.append((key, desired_value))
            if changes:
                planned.append((path, rel, changes, (stat.st_size, stat.st_mtime_ns)))
        except Exception as exc:
            errors.append({"file": track.get("relative_path", "?") if isinstance(track, dict) else "?",
                           "error": f"{type(exc).__name__}: {exc}"})
    return planned, errors


def run_import(root: Path, marker: str, cfg: dict, json_path: Path, apply: bool) -> int:
    payload = json.loads(json_path.read_text(encoding="utf-8-sig"))
    planned, errors = preflight(root, payload, cfg, marker)
    if len(planned) > cfg["max_changed_tracks"]:
        errors.append({"file": "*", "error": "Max changed tracks exceeded; adjust config deliberately"})
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = DATA / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / f"import_{'apply' if apply else 'preview'}_{timestamp}.json"
    result = {
        "mode": "apply" if apply else "preview", "source_json": str(json_path),
        "change_count": len(planned),
        "changes": [{"file": rel, "fields": [key for key, _ in changes]}
                    for _, rel, changes, _ in planned],
        "errors": errors, "changed_files": [], "backup_dir": "",
    }
    if apply and not errors and planned:
        backup_dir = DATA / "backups" / timestamp
        result["backup_dir"] = str(backup_dir)
        backups = []
        modified = []
        try:
            # Back up the full MP3 (including lyrics/artwork) BEFORE any write.
            for path, rel, _, _ in planned:
                backup = backup_dir.joinpath(*PurePosixPath(rel).parts)
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backup)
                backups.append((path, backup))
            for path, rel, changes, before in planned:
                stat = path.stat()
                if (stat.st_size, stat.st_mtime_ns) != before:
                    raise RuntimeError("File changed during import: " + rel)
                # Mark as modified before save: rollback includes even a partial write.
                modified.append(path)
                tags = load_tags(path)
                for key, value in changes:
                    write_value(tags, key, value)
                tags.save(path, v2_version=4)
                check = load_tags(path)
                for key, value in changes:
                    actual = value_of(check, key)
                    expected = value
                    if digest(actual) != digest(expected):
                        raise RuntimeError("Failed verification for " + rel + " / " + key)
                result["changed_files"].append(rel)
        except Exception as exc:
            errors.append({"file": "*", "error": "Import failed; restoring backups: " + repr(exc)})
            for path in reversed(modified):
                backup = next((saved for original, saved in backups if original == path), None)
                if backup:
                    try:
                        shutil.copy2(backup, path)
                    except Exception as rollback_exc:
                        errors.append({"file": str(path), "error": "ROLLBACK FAILED: " + repr(rollback_exc)})
            result["changed_files"] = []
    result["errors"] = errors
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Режим: {'ПРИМЕНИТЬ' if apply else 'ПРОВЕРКА'}")
    print(f"Файлов с изменениями: {len(planned)}")
    print(f"Ошибок/конфликтов: {len(errors)}")
    for item in result["changes"][:20]:
        print("  ", item["file"], "→", ", ".join(item["fields"]))
    for item in errors[:20]:
        print("ОШИБКА:", item)
    if result["backup_dir"]:
        print("Резервные MP3:", result["backup_dir"])
    print("Отчёт:", report)
    return int(bool(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description="GPT JSON exchange for GUI-managed repertoire tags only")
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export", help="Compact JSON of editable text tags")
    export.add_argument("--output", type=Path, help="Where to write JSON")
    exp = sub.add_parser("import", help="Check or apply edits in compact JSON")
    exp.add_argument("--json", required=True, type=Path, help="Edited JSON")
    exp.add_argument("--apply", action="store_true", help="Write changes (default: preview)")
    for mode in (export, exp):
        mode.add_argument("--root", type=Path, help="Override repertoire root for controlled testing")
    args = parser.parse_args()
    try:
        cfg, main_cfg = settings()
        root = (args.root or Path(main_cfg["paths"]["library_root"])).resolve()
        if not root.is_dir():
            raise ValueError("Repertoire root does not exist: " + str(root))
        marker = clean(main_cfg["site_export"]["marker"])
        if not marker:
            raise ValueError("MP3 marker missing in main config")
        if args.command == "export":
            output = args.output or (DATA / "exports" / (
                "repertoire_for_gpt_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json"))
            return export_json(root, marker, cfg, output.resolve())
        if not args.json.is_file():
            raise ValueError("Edited JSON not found: " + str(args.json))
        return run_import(root, marker, cfg, args.json.resolve(), args.apply)
    except Exception as exc:
        print("ОШИБКА:", type(exc).__name__, exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
