"""Regression tests for M3U8 export of selected songs and all their versions."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

PROGRAM = Path(__file__).resolve().parents[1] / "Создать плейлист из заявки.py"
spec = importlib.util.spec_from_file_location("singer_playlist_builder", PROGRAM)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
build_playlist = module.build_playlist


class PlaylistTests(unittest.TestCase):
    def test_every_version_and_song_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for filename in ("v1.mp3", "v2.mp3", "v3.mp3"):
                (root / filename).write_bytes(b"mp3")
            catalog = {"tracks": [
                {"song_id": "a", "relative_path": "v1.mp3", "artist": "Burito",
                 "name": "Мама", "title": "Мама +Б", "duration_seconds": 200},
                {"song_id": "a", "relative_path": "v2.mp3", "artist": "Burito",
                 "name": "Мама", "title": "Мама -Б", "duration_seconds": 202},
                {"song_id": "b", "relative_path": "v3.mp3", "artist": "Sting",
                 "name": "Shape", "title": "Shape [N]", "duration_seconds": 235},
            ]}
            lines, songs, versions = build_playlist({"song_ids": ["b", "a", "a"]}, catalog, root)
            self.assertEqual((songs, versions), (2, 3))
            self.assertEqual(lines[0], "#EXTM3U")
            self.assertEqual(lines[1], "#EXTINF:235,Sting - Shape [N]")
            self.assertEqual(lines[3], "#EXTINF:200,Burito - Мама +Б")
            self.assertEqual(lines[5], "#EXTINF:202,Burito - Мама -Б")
            self.assertEqual(len(lines), 7)

    def test_missing_variant_does_not_silently_disappear(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "v1.mp3").write_bytes(b"x")
            catalog = {"tracks": [
                {"song_id": "a", "relative_path": "v1.mp3"},
                {"song_id": "a", "relative_path": "missing.mp3"},
            ]}
            with self.assertRaisesRegex(ValueError, "missing file"):
                build_playlist({"song_ids": ["a"]}, catalog, root)

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "outside library root"):
                build_playlist({"song_ids": ["a"]}, {
                    "tracks": [{"song_id": "a", "relative_path": "../outside.mp3"}]
                }, Path(tmp))

    def test_empty_selection_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "nonempty song_ids"):
                build_playlist({"song_ids": []}, {"tracks": []}, Path(tmp))


if __name__ == "__main__":
    unittest.main()
