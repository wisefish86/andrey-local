from __future__ import annotations

import ftplib
import re
import unicodedata
from pathlib import Path
from typing import Any


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def slugify_remote_name(path: Path, slug_cfg: dict[str, Any]) -> str:
    """Build the public/FTP filename from config without renaming the local file."""
    if not slug_cfg.get("enabled", True):
        return path.name

    stem = path.stem
    separator = clean(slug_cfg.get("separator")) or "-"
    translit = slug_cfg.get("transliteration_map", {})

    if slug_cfg.get("transliterate_cyrillic", True):
        converted: list[str] = []
        for char in stem:
            lower = char.lower()
            if lower in translit:
                converted.append(str(translit[lower]))
            else:
                converted.append(char)
        stem = "".join(converted)

    stem = unicodedata.normalize("NFKD", stem)
    stem = stem.encode("ascii", "ignore").decode("ascii")

    if slug_cfg.get("lowercase", True):
        stem = stem.lower()

    stem = re.sub(r"[^a-zA-Z0-9]+", separator, stem)
    stem = re.sub(re.escape(separator) + r"{2,}", separator, stem)
    stem = stem.strip(separator)

    max_len = int(slug_cfg.get("max_stem_length", 120))
    if max_len > 0:
        stem = stem[:max_len].rstrip(separator)

    if not stem:
        stem = "audio"

    extension = path.suffix.lower() or ".mp3"
    return stem + extension


def ftp_ensure_dir(ftp: ftplib.FTP, remote_dir: str) -> None:
    ftp.cwd("/")
    for part in [p for p in remote_dir.strip("/").split("/") if p]:
        try:
            ftp.cwd(part)
        except ftplib.error_perm:
            ftp.mkd(part)
            ftp.cwd(part)


def ftp_remote_size(ftp: ftplib.FTP, remote_name: str) -> int | None:
    """Return size, None for absent/unsupported."""
    try:
        ftp.voidcmd("TYPE I")
        value = ftp.size(remote_name)
        return int(value) if value is not None else None
    except ftplib.error_perm as exc:
        code = str(exc)[:3]
        if code in {"500", "501", "502", "504", "550"}:
            return None
        raise
    except Exception:
        return None



def ftp_remote_exists(ftp: ftplib.FTP, remote_name: str) -> bool | None:
    """True/False when server can answer reliably, None when existence is unknown."""
    try:
        ftp.sendcmd(f"MLST {remote_name}")
        return True
    except ftplib.error_perm as exc:
        code = str(exc)[:3]
        if code == "550":
            return False
        if code not in {"500", "501", "502", "504"}:
            raise

    try:
        ftp.voidcmd("TYPE I")
        size = ftp.size(remote_name)
        return size is not None
    except ftplib.error_perm as exc:
        code = str(exc)[:3]
        if code == "550":
            return False
        if code in {"500", "501", "502", "504"}:
            return None
        raise
    except Exception:
        return None
