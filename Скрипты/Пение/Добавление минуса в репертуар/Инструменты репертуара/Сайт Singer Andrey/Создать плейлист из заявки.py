"""Build a MusicBee-compatible M3U8 with every local version of selected songs.

This utility uses the private local catalogue only. Never publish the playlist
or its absolute file paths to the public song-selection website.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_playlist(selection: dict, catalog: dict, root: Path) -> tuple[list[str], int, int]:
    """Return lines, number of songs and number of MP3 versions, or fail clearly."""
    ids = selection.get("song_ids")
    if not isinstance(ids, list) or not ids or any(not isinstance(x, str) or not x for x in ids):
        raise ValueError("Selection must contain nonempty song_ids array of strings")
    if not isinstance(catalog.get("tracks"), list):
        raise ValueError("Private catalogue must contain tracks array")
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"Music library root does not exist: {root}")

    grouped: dict[str, list[dict]] = {}
    for track in catalog["tracks"]:
        if isinstance(track, dict) and isinstance(track.get("song_id"), str):
            grouped.setdefault(track["song_id"], []).append(track)

    lines = ["#EXTM3U"]
    missing: list[str] = []
    seen_paths: set[Path] = set()
    version_count = 0
    selected_ids = list(dict.fromkeys(ids))
    for song_id in selected_ids:
        variants = grouped.get(song_id, [])
        if not variants:
            missing.append(f"song_id {song_id}: not found in private catalogue")
            continue
        for track in variants:
            relative_path = track.get("relative_path")
            if not isinstance(relative_path, str) or not relative_path:
                missing.append(f"song_id {song_id}: missing relative_path")
                continue
            path = (root / Path(relative_path)).resolve()
            if not path.is_relative_to(root):
                missing.append(f"song_id {song_id}: path outside library root")
                continue
            if not path.is_file():
                missing.append(f"song_id {song_id}: missing file {relative_path}")
                continue
            if path in seen_paths:
                continue
            seen_paths.add(path)
            duration = track.get("duration_seconds")
            seconds = round(duration) if isinstance(duration, (int, float)) and not isinstance(duration, bool) else -1
            artist = str(track.get("artist") or "").replace("\n", " ").replace("\r", " ")
            # TIT2 distinguishes shortened, remixed, transposed and back-vocal versions.
            title = str(track.get("title") or track.get("name") or path.stem)
            title = title.replace("\n", " ").replace("\r", " ")
            lines.extend((f"#EXTINF:{seconds},{artist} - {title}", str(path)))
            version_count += 1
    if missing:
        # Don't silently omit any available technical version: rescan the catalogue.
        raise ValueError("Incomplete private catalogue / missing MP3; playlist not written:\n" + "\n".join(missing))
    return lines, len(selected_ids), version_count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("selection", type=Path, help="JSON containing song_ids: [...]")
    parser.add_argument("--catalog", type=Path, required=True, help="Private repertoire.json")
    parser.add_argument("--root", type=Path, required=True, help="Current music library root")
    parser.add_argument("--output", type=Path, required=True, help="Output M3U8 playlist")
    args = parser.parse_args()
    selection = json.loads(args.selection.read_text(encoding="utf-8-sig"))
    catalog = json.loads(args.catalog.read_text(encoding="utf-8-sig"))
    try:
        lines, songs, versions = build_playlist(selection, catalog, args.root)
    except ValueError as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print(f"Saved: {args.output} ({songs} songs, {versions} MP3 versions)")


if __name__ == "__main__":
    main()
