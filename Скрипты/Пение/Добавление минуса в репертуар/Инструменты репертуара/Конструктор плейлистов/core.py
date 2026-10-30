"""Read-only local MP3 setlist model and M3U8 import/export.

No functions in this module alter, rename, copy, or delete source MP3 files.
The only saved output is a playlist file explicitly chosen by the user.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys

PENIE_ROOT = Path(__file__).resolve().parents[3]
COMMON = PENIE_ROOT / "_common"
if str(COMMON) not in sys.path:
    sys.path.insert(0, str(COMMON))

from id3_io import load_tags, read_text, read_txxx, read_rating, split_multi

SUPPORTED = {".mp3"}
PLAYLISTS = {".m3u", ".m3u8"}



CONFIG_FILE = Path(__file__).with_name("config.json")

def load_config(path: Path = CONFIG_FILE) -> dict:
    with Path(path).open(encoding="utf-8") as stream:
        config = json.load(stream)
    if not isinstance(config, dict) or not isinstance(config.get("library"), dict):
        raise ValueError("Некорректный config.json: отсутствует раздел library")
    return config

def scan_library(config: dict) -> list[Path]:
    """Find matching MP3 files without modifying the library."""
    settings = config["library"]
    root = Path(settings["path"])
    if not root.is_dir():
        raise FileNotFoundError(f"Папка репертуара не найдена: {root}")
    token = settings.get("filename_contains", "֎")
    if not isinstance(token, str) or not token:
        raise ValueError("library.filename_contains должен быть непустой строкой")
    recursive = bool(settings.get("recursive", True))
    skip = {str(x).casefold() for x in settings.get("exclude_directories", [])}
    paths = root.rglob("*") if recursive else root.iterdir()
    result = [
        p for p in paths
        if p.is_file() and p.suffix.casefold() == ".mp3"
        and token.casefold() in p.name.casefold()
        and not any(part.casefold() in skip for part in p.relative_to(root).parts[:-1])
    ]
    return sorted(result, key=lambda p: str(p).casefold())

@dataclass(frozen=True)
class Track:
    path: Path
    artist: str
    title: str
    clean_title: str
    difficulty: str
    language: str
    energy: str
    role: str
    status: str
    rating: str
    bpm: str
    tags: tuple[str, ...]
    error: str = ""

    @property
    def identity(self) -> str:
        # Stable across technical versions (when MVNM is properly filled).
        return self.artist.casefold() + "\0" + self.clean_title.casefold()


def read_track(path: Path) -> Track:
    """Read song attributes from the existing central ID3 implementation."""
    path = Path(path).resolve()
    if not path.is_file() or path.suffix.lower() not in SUPPORTED:
        raise ValueError(f"Файл MP3 не найден: {path}")
    fields: dict[str, str] = {}
    tags: tuple[str, ...] = ()
    problem = ""
    try:
        id3 = load_tags(path)
        def first(frame: str) -> str:
            values = read_text(id3, frame)
            return values[0] if values else ""
        groups = [tag for value in read_text(id3, "TIT1") for tag in split_multi(value)]
        tags = tuple(groups)
        def with_prefix(prefix: str) -> str:
            return next((tag for tag in groups if tag.startswith(prefix)), "")
        fields = {
            "artist": first("TPE1"),
            "title": first("TIT2"),
            "clean_title": first("MVNM"),
            "difficulty": first("TMOO"),
            "language": with_prefix("Я-"),
            "energy": first("TCON"),
            "role": first("TPE2"),
            "status": "; ".join(read_txxx(id3, "TXXX:OCCASION")),
            "rating": read_rating(id3),
            "bpm": first("TBPM"),
        }
    except Exception as exc:
        problem = f"Не удалось прочитать ID3: {exc}"
    return Track(
        path=path, artist=fields.get("artist") or "—",
        title=fields.get("title") or path.stem,
        clean_title=fields.get("clean_title") or fields.get("title") or path.stem,
        difficulty=fields.get("difficulty") or "сл-#",
        language=fields.get("language") or "Я-#",
        energy=fields.get("energy") or "к-#",
        role=fields.get("role") or "б-#",
        status=fields.get("status") or "г-#",
        rating=fields.get("rating") or "",
        bpm=fields.get("bpm") or "",
        tags=tags, error=problem,
    )


def _relative_playlist_path(value: str, playlist: Path) -> Path:
    # Standard Windows M3U files usually contain absolute paths.
    raw = Path(value)
    return (raw if raw.is_absolute() else playlist.parent / raw).resolve()


def read_playlist(path: Path) -> list[Path]:
    path = Path(path).resolve()
    if not path.is_file() or path.suffix.lower() not in PLAYLISTS:
        raise ValueError("Нужен существующий .m3u или .m3u8")
    text = ""
    for enc in ("utf-8-sig", "cp1251"):
        try:
            text = path.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    result: list[Path] = []
    for line in text.splitlines():
        line = line.strip().strip('"')
        if not line or line.startswith("#"):
            continue
        candidate = _relative_playlist_path(line, path)
        if candidate.is_file() and candidate.suffix.lower() in SUPPORTED:
            result.append(candidate)
    return result


def parse_dropped_text(text: str) -> list[Path]:
    """Accept a multiline list of full paths supplied by other music players."""
    paths: list[Path] = []
    for line in text.splitlines():
        raw = line.strip().strip('"')
        if raw.lower().startswith("file:///"):
            from urllib.parse import unquote, urlparse
            parsed = urlparse(raw)
            if parsed.scheme == "file":
                # On Windows: /C:/folder/file.mp3 -> C:/folder/file.mp3
                raw = unquote(parsed.path).lstrip("/") if len(parsed.path) > 2 and parsed.path[2] == ":" else unquote(parsed.path)
        if raw and Path(raw).is_file():
            paths.append(Path(raw).resolve())
    return paths


def expand_inputs(paths: list[Path]) -> tuple[list[Path], list[str]]:
    """Accept MP3s or M3U(8)s; ignore other files safely."""
    found, warnings = [], []
    for item in paths:
        p = Path(item)
        if p.suffix.lower() in SUPPORTED and p.is_file():
            found.append(p.resolve())
        elif p.suffix.lower() in PLAYLISTS and p.is_file():
            try:
                found.extend(read_playlist(p))
            except (OSError, ValueError) as exc:
                warnings.append(f"{p.name}: {exc}")
        else:
            warnings.append(f"Пропущено (не MP3/M3U): {p}")
    return found, warnings


def append_unique(existing: list[Track], incoming: list[Track]) -> list[Track]:
    result = list(existing)
    seen = {str(track.path).casefold() for track in result}
    for song in incoming:
        if str(song.path).casefold() not in seen:
            result.append(song)
            seen.add(str(song.path).casefold())
    return result


def move_rows(rows: list[Track], selected: list[int], destination: int) -> list[Track]:
    """Reorder a group without touching files or changing their relative order."""
    indexes = sorted({index for index in selected if 0 <= index < len(rows)})
    if not indexes:
        return list(rows)
    destination = max(0, min(len(rows), destination))
    moving = [rows[i] for i in indexes]
    remaining = [track for i, track in enumerate(rows) if i not in indexes]
    insertion = destination - sum(i < destination for i in indexes)
    return remaining[:insertion] + moving + remaining[insertion:]


def replace_rows(rows: list[Track], selected: list[int], replacements: list[Track]) -> list[Track]:
    """Insert replacements at the first selected slot, removing only list entries."""
    indexes = sorted({i for i in selected if 0 <= i < len(rows)})
    if not indexes:
        return append_unique(rows, replacements)
    remaining = [track for index, track in enumerate(rows) if index not in indexes]
    insertion = indexes[0]
    existing = {str(track.path).casefold() for track in remaining}
    incoming = []
    for track in replacements:
        key = str(track.path).casefold()
        if key not in existing:
            incoming.append(track)
            existing.add(key)
    return remaining[:insertion] + incoming + remaining[insertion:]


def repeated_from_history(current: list[Track], history: list[Track]) -> tuple[int, float]:
    """Count distinct *songs*, not multiple backing-track versions."""
    current_names = {x.identity for x in current}
    prior_names = {x.identity for x in history}
    intersection = len(current_names & prior_names)
    return intersection, (intersection / len(current_names) * 100) if current_names else 0.0


def save_playlist(path: Path, tracks: list[Track]) -> None:
    """Write explicit M3U8 only. Never touch the pointed-to MP3 source files."""
    path = Path(path)
    if path.suffix.lower() not in PLAYLISTS:
        raise ValueError("Расширение плейлиста должно быть .m3u8 или .m3u")
    if not tracks:
        raise ValueError("Список пуст")
    lines = ["#EXTM3U"]
    for track in tracks:
        # The actual local Windows path is preserved in the M3U (not a copy).
        display = f"{track.artist} - {track.title}".replace("\r", " ").replace("\n", " ")
        lines.extend((f"#EXTINF:-1,{display}", str(track.path)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
