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
    canonical_name_present: bool = True
    work_id: str = ""

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
            "work_id": next((x for v in read_text(id3, "TCOM") for x in split_multi(v) if x.startswith("в-")), ""),
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
        canonical_name_present=bool(fields.get("clean_title")),
        work_id=fields.get("work_id", ""),
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


def divider_path(number: int, reserve: bool = False, folder: Path | None = None) -> Path:
    """Resolve one of the shipped divider MP3 files without guessing its glyphs."""
    if not 1 <= number <= 6:
        raise ValueError("Номер блока должен быть от 1 до 6")
    folder = Path(folder) if folder is not None else Path(__file__).with_name("deviders")
    marker = "(запас.)" if reserve else "блок"
    matches = [p for p in folder.glob("*.mp3")
               if p.name.find(f"{number} {marker}") >= 0]
    if len(matches) != 1:
        raise FileNotFoundError(f"Не найден единственный разделитель: {number} {marker}")
    return matches[0].resolve()


def export_block_playlist(path: Path, blocks: list[tuple[list[Track], list[Track]]],
                          folder: Path | None = None) -> None:
    """Export original divider MP3 references and ordered main/reserve tracks."""
    if not 3 <= len(blocks) <= 6:
        raise ValueError("Количество блоков должно быть от 3 до 6")
    entries: list[tuple[str, Path]] = []
    for n, (main, reserve) in enumerate(blocks, start=1):
        entries.append((f"{n} блок", divider_path(n, False, folder)))
        entries.extend((f"{song.artist} - {song.title}", song.path) for song in main)
        entries.append((f"{n} (запас.)", divider_path(n, True, folder)))
        entries.extend((f"{song.artist} - {song.title}", song.path) for song in reserve)
    if not any(main for main, _ in blocks):
        raise ValueError("Нет песен для экспорта")
    lines = ["#EXTM3U"]
    for title, target in entries:
        lines.extend((f"#EXTINF:-1,{title}", str(target)))
    out = Path(path)
    if out.suffix.casefold() not in PLAYLISTS:
        raise ValueError("Нужен .m3u или .m3u8")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


def track_minutes(song: Track) -> float | None:
    """Actual MP3 running time; unknown values remain unknown."""
    from mutagen import File as AudioFile
    try:
        audio = AudioFile(str(song.path))
        value = float(audio.info.length) / 60 if audio and audio.info else 0
        return value if value > 0 else None
    except (OSError, ValueError, AttributeError):
        return None


def block_duration(songs: list[Track]) -> tuple[float, int]:
    times = [track_minutes(song) for song in songs]
    return sum(v for v in times if v is not None), sum(v is None for v in times)


def vocal_warnings(songs: list[Track]) -> list[str]:
    """Warnings, not forced reordering: the singer retains editorial control."""
    alerts = []
    for i, song in enumerate(songs):
        level = next((n for n in (1, 2, 3, 4) if f"сл-{n}" in song.difficulty), 0)
        previous = next((n for n in (1, 2, 3, 4)
                         if i and f"сл-{n}" in songs[i - 1].difficulty), 0)
        if level >= 3 and previous >= 3:
            alerts.append(f"Песни {i}–{i + 1}: две сложные подряд")
        if level == 4:
            alerts.append(f"Песня {i + 1}: пиковая нагрузка")
    return alerts

def distribute_blocks(tracks: list[Track], number: int, target_minutes: int,
                      reserve_count: int = 2) -> list[tuple[list[Track], list[Track]]]:
    """Keep manual song order, partition by real runtime, add distinct easy reserves."""
    if not 3 <= number <= 6 or not 10 <= target_minutes <= 60:
        raise ValueError("Неверные параметры блоков")
    lengths = [track_minutes(t) or 0.0 for t in tracks]
    # Missing duration is not fabricated; assign tracks evenly as a fallback.
    blocks: list[list[Track]] = [[] for _ in range(number)]
    if all(v > 0 for v in lengths):
        position = 0
        elapsed = 0.0
        for song, minutes in zip(tracks, lengths):
            if position < number - 1 and blocks[position] and elapsed + minutes > target_minutes:
                position += 1
                elapsed = 0.0
            blocks[position].append(song)
            elapsed += minutes
    else:
        for index, song in enumerate(tracks):
            blocks[min(number - 1, index * number // max(len(tracks), 1))].append(song)
    # Reserve songs are drawn from remaining eligible medium/easy catalogue externally;
    # never silently duplicate an already scheduled performance.
    return [(group, []) for group in blocks]


def song_key(track: Track) -> tuple[str, str]:
    """Song identity by artist and canonical MVNM; never guess empty MVNM."""
    from unicodedata import normalize
    def norm(value: str) -> str:
        return " ".join(normalize("NFKC", value).casefold().split())
    work = norm(track.work_id)
    if work.startswith("в-") and len(work) > 2:
        return "__work__", work[2:]
    if not track.canonical_name_present:
        return "__path__", norm(str(track.path))
    return norm(track.artist), norm(track.clean_title)


def unique_songs(tracks: list[Track]) -> list[Track]:
    """Show one representative technical version per song in the catalog."""
    seen: set[tuple[str, str]] = set()
    result = []
    for track in tracks:
        key = song_key(track)
        if key not in seen:
            seen.add(key)
            result.append(track)
    return result


def add_unique_songs(existing: list[Track], incoming: list[Track]) -> list[Track]:
    keys = {song_key(t) for t in existing}
    result = list(existing)
    for track in incoming:
        key = song_key(track)
        if key not in keys:
            result.append(track)
            keys.add(key)
    return result


def replacement_candidates(current: list[Track], selected_index: int,
                           catalog: list[Track], rejected: set[str] | None = None) -> list[Track]:
    """Stable ranked alternatives; excludes selected and all already-used songs."""
    if selected_index < 0 or selected_index >= len(current):
        return []
    selected = current[selected_index]
    occupied = {song_key(t) for t in current}
    rejected = rejected or set()
    approved = ("г-1-", "г-2-", "г-3-")
    eligible = [
        t for t in catalog
        if t.status.startswith(approved)
        and song_key(t) not in occupied
        and str(t.path).casefold() not in rejected
    ]
    eligible = unique_songs(eligible)
    def score(t: Track) -> tuple[int, int, int, str]:
        return (
            int(t.role == selected.role),
            int(t.energy == selected.energy),
            int(t.difficulty == selected.difficulty),
            t.title.casefold(),
        )
    return sorted(eligible, key=lambda t: (-score(t)[0], -score(t)[1], -score(t)[2], score(t)[3]))

def eligible_for_restaurant(track: Track, preset: dict) -> bool:
    """Hard exclusions precede every selection or replacement."""
    if not track.status.startswith(("г-1-", "г-2-", "г-3-")):
        return False
    banned = {str(v).casefold() for v in preset.get("exclude_tags", [])}
    required = {str(v).casefold() for v in preset.get("include_tags", [])}
    tags = {v.casefold() for v in track.tags}
    tags.update(v.strip().casefold() for v in track.status.split(";") if v.strip())
    tags.update(v.casefold() for v in (track.role, track.difficulty, track.energy, track.work_id) if v)
    if banned & tags:
        return False
    if required and not (required & tags):
        return False
    return True


def filtered_restaurant_catalog(tracks: list[Track], preset: dict) -> list[Track]:
    return unique_songs([song for song in tracks if eligible_for_restaurant(song, preset)])

PRESETS_FILE = Path(__file__).with_name("restaurant_presets.json")

def load_restaurant_presets(path: Path = PRESETS_FILE) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Неверный формат пресетов")
    return data

def save_restaurant_presets(presets: dict, path: Path = PRESETS_FILE) -> None:
    """Save editable local presets; MP3 files are never modified."""
    if not isinstance(presets, dict):
        raise ValueError("Неверный формат пресетов")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(presets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)

def link_versions(paths: list[Path], code: str, backup_dir: Path) -> int:
    """Apply one shared Cyrillic work tag, preserving other TIT1 groups with backups."""
    import re
    import shutil
    from mutagen.id3 import ID3, TCOM
    code = code.strip()
    if not re.fullmatch(r"в-[^\s;]+", code):
        raise ValueError("Нужен тег в-Название с дефисами вместо пробелов")
    files = list(dict.fromkeys(Path(p).resolve() for p in paths))
    if len(files) < 2:
        raise ValueError("Для связывания выбери не менее двух MP3")
    if any(not p.is_file() or p.suffix.casefold() != ".mp3" for p in files):
        raise ValueError("Каждый выбранный файл должен быть существующим MP3")
    planned = []
    for path in files:
        tags = ID3(path)
        values = [part for text in read_text(tags, "TCOM") for part in split_multi(text)]
        existing = [value for value in values if value.casefold().startswith("в-")]
        if any(value.casefold() != code.casefold() for value in existing):
            raise ValueError(f"Конфликт группы произведения: {path.name} — {existing}")
        cleaned = [value for value in values if not value.casefold().startswith("в-")]
        planned.append((path, tags, cleaned + [code]))
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    for index, (path, _, _) in enumerate(planned):
        shutil.copy2(path, backup_dir / f"{index + 1:03d}_{path.name}")
    for path, tags, values in planned:
        tags.delall("TCOM")
        tags.add(TCOM(encoding=3, text=["; ".join(values)]))
        tags.save(path)
    return len(planned)
