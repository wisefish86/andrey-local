from __future__ import annotations

from pathlib import Path
from typing import Any

import mutagen.id3 as id3
from mutagen.id3 import ID3, ID3NoHeaderError

RATING_OWNER = "Windows Media Player 9 Series"


def clean(value: Any) -> str:
    return str(value or "").strip()


def split_multi(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split(";") if part.strip()]


def load_tags(path: Path) -> ID3:
    try:
        return ID3(path)
    except ID3NoHeaderError:
        return ID3()


def read_text(tags: ID3, frame_name: str) -> list[str]:
    values: list[str] = []
    for frame in tags.getall(frame_name):
        text = getattr(frame, "text", [])
        if isinstance(text, (list, tuple)):
            values.extend(clean(x) for x in text if clean(x))
        elif clean(text):
            values.append(clean(text))
    return values


def write_text(tags: ID3, frame_name: str, values: list[str]) -> None:
    frame_class = getattr(id3, frame_name, None)
    if frame_class is None or frame_name == "TXXX":
        raise ValueError(f"Unsupported text frame: {frame_name}")
    tags.delall(frame_name)
    if values:
        tags.add(frame_class(encoding=3, text=values))


def read_txxx(tags: ID3, frame_name: str) -> list[str]:
    desc = frame_name.partition(":")[2]
    values: list[str] = []
    for frame in tags.getall("TXXX"):
        if clean(frame.desc).casefold() == desc.casefold():
            values.extend(clean(x) for x in frame.text if clean(x))
    return values


def write_txxx(tags: ID3, frame_name: str, values: list[str]) -> None:
    desc = frame_name.partition(":")[2]
    for frame in list(tags.getall("TXXX")):
        if clean(frame.desc).casefold() == desc.casefold():
            tags.delall(frame.HashKey)
    if values:
        tags.add(id3.TXXX(encoding=3, desc=desc, text=values))


def read_comment(tags: ID3) -> str:
    values: list[str] = []
    for frame in tags.getall("COMM"):
        values.extend(clean(x) for x in getattr(frame, "text", []) if clean(x))
    return "; ".join(values)


def write_comment(tags: ID3, value: str) -> None:
    tags.delall("COMM")
    if value:
        tags.add(id3.COMM(encoding=3, lang="eng", desc="", text=[value]))


def read_url(tags: ID3, frame_name: str) -> str:
    frames = tags.getall(frame_name)
    return clean(getattr(frames[0], "url", "")) if frames else ""


def write_url(tags: ID3, frame_name: str, value: str) -> None:
    frame_class = getattr(id3, frame_name, None)
    if frame_class is None:
        raise ValueError(f"Unsupported URL frame: {frame_name}")
    tags.delall(frame_name)
    if value:
        tags.add(frame_class(url=value))


def read_wxxx(tags: ID3, description: str = "") -> str:
    for frame in tags.getall("WXXX"):
        if clean(frame.desc).casefold() == clean(description).casefold():
            return clean(frame.url)
    return ""


def write_wxxx(tags: ID3, description: str, value: str) -> None:
    description = clean(description)
    for frame in list(tags.getall("WXXX")):
        if clean(frame.desc).casefold() == description.casefold():
            tags.delall(frame.HashKey)
    if value:
        tags.add(id3.WXXX(encoding=3, desc=description, url=value))


def read_lyrics(tags: ID3, language: str = "eng", description: str = "") -> str:
    language = clean(language) or "eng"
    description = clean(description)
    fallback = None
    for frame in tags.getall("USLT"):
        if fallback is None:
            fallback = frame
        if clean(getattr(frame, "lang", "")).casefold() == language.casefold() and clean(getattr(frame, "desc", "")).casefold() == description.casefold():
            return str(getattr(frame, "text", "") or "")
    return str(getattr(fallback, "text", "") or "") if fallback is not None else ""


def write_lyrics(tags: ID3, value: str, language: str = "eng", description: str = "") -> None:
    language = clean(language) or "eng"
    description = clean(description)
    for frame in list(tags.getall("USLT")):
        if clean(getattr(frame, "lang", "")).casefold() == language.casefold() and clean(getattr(frame, "desc", "")).casefold() == description.casefold():
            tags.delall(frame.HashKey)
    if value:
        tags.add(id3.USLT(encoding=3, lang=language, desc=description, text=str(value)))


def preferred_popm(tags: ID3):
    frames = tags.getall("POPM")
    for frame in frames:
        if clean(getattr(frame, "email", "")).casefold() == RATING_OWNER.casefold():
            return frame
    return frames[0] if frames else None


def read_rating(tags: ID3) -> str:
    frame = preferred_popm(tags)
    if frame is None:
        return ""
    rating = int(getattr(frame, "rating", 0) or 0)
    return "" if rating == 0 else str(rating)


def write_rating(tags: ID3, value: str) -> None:
    rating = int(value)
    frame = preferred_popm(tags)
    if frame is not None:
        frame.rating = rating
    else:
        tags.add(id3.POPM(email=RATING_OWNER, rating=rating, count=0))


def read_field(tags: ID3, spec: dict[str, Any]):
    kind = spec["kind"]
    frame = spec["frame"]
    multi = bool(spec.get("multi"))
    if kind == "text":
        values = read_text(tags, frame)
        return values if multi else (values[0] if values else "")
    if kind == "txxx":
        values = read_txxx(tags, frame)
        return values if multi else (values[0] if values else "")
    if kind == "comment":
        return read_comment(tags)
    if kind == "url":
        return read_url(tags, frame)
    if kind == "wxxx":
        return read_wxxx(tags, clean(spec.get("description")))
    if kind == "rating":
        return read_rating(tags)
    if kind == "lyrics":
        return read_lyrics(tags, clean(spec.get("language")) or "eng", clean(spec.get("description")))
    raise ValueError(f"Unsupported field kind: {kind}")


def write_field(tags: ID3, spec: dict[str, Any], desired) -> None:
    kind = spec["kind"]
    frame = spec["frame"]
    multi = bool(spec.get("multi"))
    if kind == "text":
        values = list(desired) if multi else ([desired] if desired else [])
        write_text(tags, frame, values)
    elif kind == "txxx":
        values = list(desired) if multi else ([desired] if desired else [])
        write_txxx(tags, frame, values)
    elif kind == "comment":
        write_comment(tags, desired)
    elif kind == "url":
        write_url(tags, frame, desired)
    elif kind == "wxxx":
        write_wxxx(tags, clean(spec.get("description")), desired)
    elif kind == "rating":
        write_rating(tags, desired)
    elif kind == "lyrics":
        write_lyrics(
            tags,
            desired,
            clean(spec.get("language")) or "eng",
            clean(spec.get("description")),
        )
    else:
        raise ValueError(f"Unsupported field kind: {kind}")
