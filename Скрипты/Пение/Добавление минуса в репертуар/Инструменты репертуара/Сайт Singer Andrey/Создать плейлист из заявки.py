"""Create a MusicBee-compatible M3U8 from an exported selection of song IDs."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

def main():
    p = argparse.ArgumentParser()
    p.add_argument("selection", type=Path, help="JSON containing song_ids: [...]")
    p.add_argument("--catalog", type=Path, required=True, help="Private repertoire.json")
    p.add_argument("--root", type=Path, required=True, help="Current music library root")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    selection = json.loads(args.selection.read_text(encoding="utf-8-sig"))
    catalog = json.loads(args.catalog.read_text(encoding="utf-8-sig"))
    ids = selection.get("song_ids")
    if not isinstance(ids, list) or not ids or any(not isinstance(x,str) for x in ids):
        p.error("Selection must contain nonempty song_ids array of strings")
    grouped = {}
    for track in catalog.get("tracks", []):
        grouped.setdefault(track.get("song_id"), []).append(track)
    lines = ["#EXTM3U"]
    missing = []
    for song_id in dict.fromkeys(ids):
        tracks = grouped.get(song_id, [])
        valid = []
        for track in tracks:
            rel = track.get("relative_path")
            if not rel:
                continue
            path = (args.root / Path(rel)).resolve()
            if not path.is_relative_to(args.root.resolve()) or not path.is_file():
                continue
            valid.append((track, path))
        if not valid:
            missing.append(song_id)
            continue
        track, path = valid[0]
        length = track.get("duration_seconds")
        seconds = round(length) if isinstance(length, (int, float)) else -1
        lines.extend([f'#EXTINF:{seconds},{track.get("artist","")} - {track.get("name","")}', str(path)])
    if missing:
        raise SystemExit("Missing files/song IDs; playlist not written: " + ", ".join(missing))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print("Saved:", args.output)

if __name__ == "__main__":
    main()
