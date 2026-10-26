from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from mutagen.id3 import ID3, ID3NoHeaderError
from mutagen.mp3 import MP3


def find_app_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "config.json").is_file() and (candidate / "src").is_dir():
            return candidate
    raise RuntimeError("Не найден корень программы с config.json")


APP_ROOT = find_app_root(Path(__file__).resolve().parent)
PENIE_ROOT = APP_ROOT.parent
if str(PENIE_ROOT) not in sys.path:
    sys.path.insert(0, str(PENIE_ROOT))

from _common.id3_io import clean, read_rating, read_text, read_txxx, read_url

CONFIG_PATH = APP_ROOT / "config.json"
DEFAULT_OUTPUT_DIR = APP_ROOT / "data" / "id3_audit"


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def first(values: list[str]) -> str:
    return values[0] if values else ""


def serialize_bytes(value: bytes | bytearray | memoryview) -> dict[str, Any]:
    raw = bytes(value)
    return {
        "_type": "bytes",
        "encoding": "base64",
        "size": len(raw),
        "data": base64.b64encode(raw).decode("ascii"),
    }


def serialize_value(value: Any, depth: int = 0) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return serialize_bytes(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [serialize_value(item, depth + 1) for item in value]
    if isinstance(value, dict):
        return {
            str(key): serialize_value(item, depth + 1)
            for key, item in value.items()
        }
    if depth >= 8:
        return repr(value)

    if isinstance(value, ID3):
        return {
            "_type": "ID3",
            "version": list(value.version) if getattr(value, "version", None) else None,
            "frames": [serialize_frame(frame, depth + 1) for frame in value.values()],
        }

    try:
        return str(value)
    except Exception:
        return repr(value)


def frame_attribute_names(frame: Any) -> list[str]:
    names: list[str] = []
    for collection_name in ("_framespec", "_optionalspec"):
        for spec in getattr(frame, collection_name, ()) or ():
            name = getattr(spec, "name", "")
            if name and name not in names:
                names.append(name)

    for name in (
        "encoding", "text", "url", "desc", "lang", "mime", "type",
        "format", "data", "owner", "email", "rating", "count",
        "element_id", "start_time", "end_time", "start_offset",
        "end_offset", "sub_frames",
    ):
        if hasattr(frame, name) and name not in names:
            names.append(name)
    return names


def serialize_frame(frame: Any, depth: int = 0) -> dict[str, Any]:
    attributes: dict[str, Any] = {}
    for name in frame_attribute_names(frame):
        try:
            attributes[name] = serialize_value(getattr(frame, name), depth + 1)
        except Exception as exc:
            attributes[name] = {
                "_type": "serialization_error",
                "error": f"{type(exc).__name__}: {exc}",
            }

    try:
        pretty = frame.pprint()
    except Exception as exc:
        pretty = f"<pprint error: {type(exc).__name__}: {exc}>"

    return {
        "frame_id": clean(getattr(frame, "FrameID", "")),
        "hash_key": clean(getattr(frame, "HashKey", "")),
        "class": frame.__class__.__name__,
        "attributes": attributes,
        "pprint": pretty,
    }


def read_id3(path: Path) -> tuple[ID3, bool]:
    try:
        return ID3(path), True
    except ID3NoHeaderError:
        return ID3(), False


def audio_info(path: Path) -> dict[str, Any]:
    try:
        audio = MP3(path)
        info = audio.info
        result: dict[str, Any] = {}
        for name in (
            "length", "bitrate", "sample_rate", "channels", "mode",
            "bitrate_mode", "encoder_info", "encoder_settings", "sketchy",
            "track_gain", "track_peak", "album_gain", "album_peak",
        ):
            if hasattr(info, name):
                result[name] = serialize_value(getattr(info, name))
        return result
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def summary(tags: ID3) -> dict[str, Any]:
    return {
        "artist": first(read_text(tags, "TPE1")),
        "clean_title": first(read_text(tags, "MVNM")),
        "title": first(read_text(tags, "TIT2")),
        "album": first(read_text(tags, "TALB")),
        "album_artist": first(read_text(tags, "TPE2")),
        "year": first(read_text(tags, "TDRC")),
        "genre": read_text(tags, "TCON"),
        "mood": read_text(tags, "TMOO"),
        "group_tags": read_text(tags, "TIT1"),
        "occasion": read_txxx(tags, "TXXX:OCCASION"),
        "bpm": first(read_text(tags, "TBPM")),
        "plus_url": read_url(tags, "WOAS"),
        "rating": read_rating(tags),
        "replaygain_track_gain": first(read_txxx(tags, "TXXX:replaygain_track_gain")),
        "replaygain_track_peak": first(read_txxx(tags, "TXXX:replaygain_track_peak")),
        "uslt_count": len(tags.getall("USLT")),
        "sylt_count": len(tags.getall("SYLT")),
    }


def build_track(path: Path, root: Path) -> dict[str, Any]:
    tags, has_id3 = read_id3(path)
    relative = path.relative_to(root).as_posix()
    stat = path.stat()

    frames = [serialize_frame(frame) for frame in tags.values()]
    frame_ids = Counter(item["frame_id"] or item["class"] for item in frames)

    return {
        "id": hashlib.sha1(relative.encode("utf-8")).hexdigest()[:16],
        "relative_path": relative,
        "full_path": str(path),
        "file_name": path.name,
        "file_size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "audio": audio_info(path),
        "summary": summary(tags),
        "id3": {
            "has_header": has_id3,
            "version": list(tags.version) if has_id3 else None,
            "frame_count": len(frames),
            "frame_id_counts": dict(sorted(frame_ids.items(), key=lambda item: item[0].casefold())),
            "frames": frames,
        },
    }


def scan(
    root: Path,
    marker: str,
    excluded_dirs: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, str]], Counter[str]]:
    tracks: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    frame_types: Counter[str] = Counter()

    for current, dirs, files in os.walk(root):
        dirs[:] = [
            name
            for name in dirs
            if name.casefold() not in excluded_dirs
        ]
        folder = Path(current)

        for name in sorted(files, key=str.casefold):
            path = folder / name
            if path.suffix.lower() != ".mp3" or marker not in path.name:
                continue
            try:
                track = build_track(path, root)
                tracks.append(track)
                frame_types.update(track["id3"]["frame_id_counts"])
            except Exception as exc:
                errors.append({
                    "file": str(path),
                    "error": f"{type(exc).__name__}: {exc}",
                })

    tracks.sort(
        key=lambda item: (
            clean(item.get("summary", {}).get("artist")).casefold(),
            clean(item.get("summary", {}).get("clean_title")).casefold(),
            clean(item.get("summary", {}).get("title")).casefold(),
            clean(item.get("relative_path")).casefold(),
        )
    )
    return tracks, errors, frame_types


def default_output_path() -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return DEFAULT_OUTPUT_DIR / f"id3_full_export_{stamp}.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Полный безопасный экспорт ID3 всех репертуарных MP3 в JSON."
    )
    parser.add_argument("--root", help="Переопределить корневую папку репертуара.")
    parser.add_argument("--output", help="Явно указать путь выходного JSON.")
    parser.add_argument(
        "--use-site-excludes",
        action="store_true",
        help="Исключить служебные папки из site_export.exclude_dirs.",
    )
    args = parser.parse_args()

    config = load_config()
    root = Path(args.root or config.get("paths", {}).get("library_root", ""))
    if not root.is_dir():
        print(f"ОШИБКА: не найден library_root: {root}")
        return 2

    site_cfg = config.get("site_export", {})
    marker = clean(site_cfg.get("marker")) or "֎"
    excluded_list = [
        clean(name)
        for name in site_cfg.get("exclude_dirs", [])
        if clean(name)
    ] if args.use_site_excludes else []
    excluded_dirs = {name.casefold() for name in excluded_list}

    output = Path(args.output).resolve() if args.output else default_output_path()
    output.parent.mkdir(parents=True, exist_ok=True)

    print("Полный аудит ID3")
    print(f"Корень: {root}")
    print(f"Маркер: {marker}")
    print(
        "Исключённые папки: "
        + (", ".join(excluded_list) if excluded_list else "нет")
    )
    print()

    tracks, errors, frame_types = scan(root, marker, excluded_dirs)

    payload = {
        "schema_version": 1,
        "export_kind": "full_id3_audit",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "andrey-local / MP3 ID3 / Mutagen",
        "library_root": str(root),
        "marker": marker,
        "excluded_dirs": excluded_list,
        "track_count": len(tracks),
        "error_count": len(errors),
        "frame_type_counts": dict(
            sorted(frame_types.items(), key=lambda item: (-item[1], item[0].casefold()))
        ),
        "tracks": tracks,
        "errors": errors,
    }

    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("Готово")
    print(f"Минусовок: {len(tracks)}")
    print(f"Ошибок: {len(errors)}")
    print(f"JSON: {output}")
    if frame_types:
        print()
        print("ID3-фреймы:")
        for frame_id, count in frame_types.most_common():
            print(f"  {frame_id}: {count}")

    if errors:
        print()
        print("Ошибки:")
        for item in errors[:30]:
            print(f"- {item['file']}: {item['error']}")
        if len(errors) > 30:
            print(f"... ещё {len(errors) - 30}")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
