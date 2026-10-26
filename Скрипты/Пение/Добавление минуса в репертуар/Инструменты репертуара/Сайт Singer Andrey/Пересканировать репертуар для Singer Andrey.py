from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from collections import defaultdict
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

from _common.id3_io import clean, load_tags, read_field, read_text, read_url

CONFIG_PATH = APP_ROOT / "config.json"


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def first_text(tags, frame: str) -> str:
    values = read_text(tags, frame)
    return values[0] if values else ""


def tit1_values(tags) -> list[str]:
    return [clean(x) for x in read_text(tags, "TIT1") if clean(x)]


def field_value(tags, field: dict[str, Any]):
    storage = field.get("storage", {})
    kind = storage.get("kind")
    control = field.get("control")

    if kind == "tit1_group":
        values = tit1_values(tags)
        prefix = clean(storage.get("prefix"))
        if storage.get("prefix_casefold"):
            selected = [x for x in values if x.casefold().startswith(prefix.casefold())]
        else:
            selected = [x for x in values if x.startswith(prefix)]
        return selected if control == "multi_select" else (selected[0] if selected else "")

    if kind in {"text", "txxx", "url", "wxxx", "rating", "lyrics", "comment"}:
        value = read_field(tags, storage)
        return value

    return ""


def schema_from_config(config: dict[str, Any]) -> dict[str, Any]:
    fields = []
    for field in config.get("fields", []):
        fields.append(
            {
                "id": field.get("id"),
                "label": field.get("label"),
                "control": field.get("control"),
                "section": field.get("section"),
                "options": field.get("options", []),
            }
        )

    return {
        "fields": fields,
        "fixed_tags": config.get("fixed_tags", {}),
        "title_flags": config.get("title", {}).get("flags", {}),
    }


def build_track(path: Path, root: Path, config: dict[str, Any]) -> dict[str, Any]:
    tags = load_tags(path)
    relative = path.relative_to(root).as_posix()
    lyrics_spec = dict(
        config.get("lyrics", {}).get(
            "storage",
            {"kind": "lyrics", "frame": "USLT", "language": "eng", "description": ""},
        )
    )
    lyrics = read_field(tags, lyrics_spec)
    include_lyrics = bool(config.get("site_export", {}).get("include_lyrics", False))

    managed = {}
    for field in config.get("fields", []):
        managed[field["id"]] = field_value(tags, field)

    replaygain_gain = read_field(
        tags,
        {"kind": "txxx", "frame": "TXXX:replaygain_track_gain"},
    )
    replaygain_peak = read_field(
        tags,
        {"kind": "txxx", "frame": "TXXX:replaygain_track_peak"},
    )

    try:
        duration = round(float(MP3(path).info.length), 2)
    except Exception:
        duration = None

    track = {
        "id": hashlib.sha1(relative.encode("utf-8")).hexdigest()[:16],
        "artist": first_text(tags, "TPE1"),
        "name": first_text(tags, "MVNM"),
        "title": first_text(tags, "TIT2"),
        "album": first_text(tags, "TALB"),
        "year": first_text(tags, "TDRC"),
        "bpm": first_text(tags, "TBPM"),
        "plus_url": read_url(tags, "WOAS"),
        "replaygain": {
            "track_gain": replaygain_gain,
            "track_peak": replaygain_peak,
        },
        "managed": managed,
        "has_lyrics": bool(clean(lyrics)),
        "source_name": path.name,
        "duration_seconds": duration,
        "relative_path": relative,
        "folder_name": path.parent.name,
    }
    if include_lyrics:
        track["lyrics"] = lyrics
    return track


def scan(config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    site_cfg = config.get("site_export", {})
    root = Path(config.get("paths", {}).get("library_root", ""))
    if not root.is_dir():
        raise RuntimeError(f"Не найден library_root: {root}")

    marker = clean(site_cfg.get("marker")) or "֎"
    excluded = {
        clean(name).casefold()
        for name in site_cfg.get("exclude_dirs", [])
        if clean(name)
    }

    tracks: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d.casefold() not in excluded]
        folder = Path(current)

        for name in sorted(files, key=str.casefold):
            path = folder / name
            if path.suffix.lower() != ".mp3" or marker not in path.name:
                continue

            try:
                tracks.append(build_track(path, root, config))
            except Exception as exc:
                errors.append(
                    {
                        "file": str(path),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

    tracks.sort(
        key=lambda x: (
            clean(x.get("artist")).casefold(),
            clean(x.get("name")).casefold(),
            clean(x.get("title")).casefold(),
        )
    )
    return tracks, errors


def main() -> int:
    config = load_config()
    site_cfg = config.get("site_export", {})
    tracks, errors = scan(config)

    output = APP_ROOT / Path(site_cfg.get("output_file", "data/site/repertoire.json"))
    output.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema_version": int(site_cfg.get("schema_version", 1)),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "andrey-local / MP3 ID3",
        "track_count": len(tracks),
        "error_count": len(errors),
        "schema": schema_from_config(config),
        "tracks": tracks,
        "errors": errors,
    }

    # Public catalogue: one song per Artist + MVNM. Local JSON retains every version.
    grouped = defaultdict(list)
    warnings = []
    for track in tracks:
        artist = clean(track["artist"])
        name = clean(track["name"])
        if artist and name:
            stable = artist.casefold() + chr(0) + name.casefold()
            song_id = hashlib.sha1(stable.encode("utf-8")).hexdigest()[:16]
        else:
            song_id = track["id"]
            warnings.append({"track_id": track["id"], "reason": "missing_artist_or_name"})
        track["song_id"] = song_id
        grouped[song_id].append(track)

    songs = []
    for song_id, variants in grouped.items():
        chosen = variants[0]
        songs.append({
            "id": song_id,
            "artist": chosen["artist"],
            "name": chosen["name"],
            "duration_seconds": chosen["duration_seconds"],
            "year": chosen["year"],
            "bpm": chosen["bpm"],
            "genre": chosen["managed"].get("energy", ""),
            "version_count": len(variants),
        })
    songs.sort(key=lambda song: (clean(song["artist"]).casefold(), clean(song["name"]).casefold()))
    payload["songs"] = songs
    payload["song_count"] = len(songs)
    payload["warnings"] = warnings

    public_output = output.with_name("repertoire.public.json")
    public_output.write_text(json.dumps({
        "schema_version": 2,
        "generated_at": payload["generated_at"],
        "song_count": len(songs),
        "songs": songs,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    output.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2 if site_cfg.get("pretty_json", True) else None,
        ),
        encoding="utf-8",
    )

    print("Готово")
    print(f"Минусовок: {len(tracks)}")
    print(f"Ошибок: {len(errors)}")
    print(f"Внутренний JSON: {output}")
    print(f"Публичный JSON: {public_output}")
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
