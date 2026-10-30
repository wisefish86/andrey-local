from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import (read_track, append_unique, save_playlist, read_playlist, move_rows,
                  replace_rows, repeated_from_history, expand_inputs, parse_dropped_text, scan_library, load_config, divider_path, export_block_playlist, distribute_blocks)
from mutagen.id3 import ID3, TPE1, TIT2, MVNM, TMOO, TCON, TIT1, TPE2, TXXX, TBPM


class SetlistCoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.a = self.make_mp3("Мама +Б.mp3", title="Мама +Б", clean="Мама")
        self.b = self.make_mp3("Мама -Б.mp3", title="Мама -Б", clean="Мама")
        self.c = self.make_mp3("Другой.mp3", title="Другой", clean="Другой")

    def make_mp3(self, filename, title, clean):
        path = self.root / filename
        path.write_bytes(b"")
        tags = ID3()
        tags.add(TPE1(encoding=3, text=["Burito"]))
        tags.add(TIT2(encoding=3, text=[title]))
        tags.add(MVNM(encoding=3, text=[clean]))
        tags.add(TMOO(encoding=3, text=["сл-3-Сложно"]))
        tags.add(TCON(encoding=3, text=["к-Динамич"]))
        tags.add(TIT1(encoding=3, text=["Я-рус; а-Унив; э-20е"]))
        tags.add(TPE2(encoding=3, text=["б-4-Развитие"]))
        tags.add(TXXX(encoding=3, desc="OCCASION", text=["г-2-Рабочие"]))
        tags.add(TBPM(encoding=3, text=["120"]))
        tags.save(path)
        return path

    def test_reads_canonical_musicbee_fields(self):
        a = read_track(self.a)
        self.assertEqual(a.artist, "Burito")
        self.assertEqual(a.title, "Мама +Б")
        self.assertEqual(a.clean_title, "Мама")
        self.assertEqual(a.difficulty, "сл-3-Сложно")
        self.assertEqual(a.language, "Я-рус")
        self.assertEqual(a.energy, "к-Динамич")
        self.assertEqual(a.role, "б-4-Развитие")
        self.assertEqual(a.status, "г-2-Рабочие")
        self.assertEqual(a.bpm, "120")
        self.assertIn("э-20е", a.tags)

    def test_m3u_round_trip_preserves_unicode_and_order(self):
        tracks = [read_track(p) for p in (self.a, self.b, self.c)]
        playlist = self.root / "Вечер.m3u8"
        source = self.a.read_bytes()
        save_playlist(playlist, tracks)
        self.assertEqual(source, self.a.read_bytes(), "MP3 must be unmodified")
        text = playlist.read_text(encoding="utf-8-sig")
        self.assertTrue(text.startswith("#EXTM3U\n"))
        self.assertIn(str(self.a), text)
        self.assertEqual(read_playlist(playlist), [self.a.resolve(), self.b.resolve(), self.c.resolve()])
        self.assertEqual(playlist.read_bytes()[:3], b"\xef\xbb\xbf")

    def test_deduplicate_by_path_not_song_name(self):
        a, b = read_track(self.a), read_track(self.b)
        self.assertEqual(len(append_unique([a], [a, b, b])), 2)

    def test_replace_multiple_removes_only_entries(self):
        a, b, c = (read_track(p) for p in (self.a, self.b, self.c))
        self.assertEqual(replace_rows([a, b, c], [0, 1], [c]), [c])
        self.assertTrue(self.a.is_file())
        self.assertTrue(self.b.is_file())
        self.assertTrue(self.c.is_file())

    def test_group_reorder(self):
        a, b, c = (read_track(p) for p in (self.a, self.b, self.c))
        self.assertEqual(move_rows([a, b, c], [0, 1], 3), [c, a, b])
        self.assertEqual(move_rows([a, b, c], [2], 0), [c, a, b])

    def test_history_counts_songs_not_versions(self):
        a, b, c = (read_track(p) for p in (self.a, self.b, self.c))
        self.assertEqual(repeated_from_history([a, b, c], [b]), (1, 50.0))

    def test_dragged_paths_and_m3u_import(self):
        playlist = self.root / "source.m3u8"
        save_playlist(playlist, [read_track(self.a), read_track(self.c)])
        paths, warnings = expand_inputs([playlist])
        self.assertEqual(paths, [self.a.resolve(), self.c.resolve()])
        self.assertEqual(warnings, [])
        self.assertEqual(parse_dropped_text(f'"{self.a}"\n"{self.c}"'), [self.a.resolve(), self.c.resolve()])

    def test_catalog_scan_is_recursive_filtered_and_read_only(self):
        library = self.root / "Основной репертуар"
        folder = library / "Исполнитель"
        folder.mkdir(parents=True)
        included = folder / "Песня ֎ Артист.mp3"
        included.write_bytes(b"test")
        (folder / "Песня без маркера.mp3").write_bytes(b"test")
        (folder / "Песня _____ Артист.mp3").write_bytes(b"test")
        (folder / "Песня ֎ Артист.wav").write_bytes(b"test")
        staging = library / "- - Добавляю в репертуар"
        staging.mkdir()
        (staging / "Черновик ֎ Артист.mp3").write_bytes(b"test")
        config = {"library": {"path": str(library), "filename_contains": "֎",
                  "recursive": True, "exclude_directories": ["- - Добавляю в репертуар"]}}
        self.assertEqual(scan_library(config), [included])
        self.assertEqual(included.read_bytes(), b"test")
        config["library"]["recursive"] = False
        self.assertEqual(scan_library(config), [])

    def test_catalog_missing_path_is_explicit(self):
        with self.assertRaises(FileNotFoundError):
            scan_library({"library": {"path": str(self.root / "нет")}})

    def test_block_export_uses_original_divider_files(self):
        directory = self.root / "deviders"
        directory.mkdir()
        for number in range(1, 4):
            (directory / f"━━ {number} блок ━━.mp3").write_bytes(b"divider")
            (directory / f"━━ {number} (запас.) ━━.mp3").write_bytes(b"reserve")
        songs = [read_track(self.a), read_track(self.b), read_track(self.c)]
        blocks = [([songs[0]], [songs[1]]), ([songs[2]], []), ([], [])]
        out = self.root / "Сеты.m3u8"
        export_block_playlist(out, blocks, directory)
        content = out.read_text(encoding="utf-8-sig")
        for number in range(1, 4):
            self.assertIn(str(divider_path(number, False, directory)), content)
            self.assertIn(str(divider_path(number, True, directory)), content)
        self.assertEqual(out.read_bytes()[:3], b"\\xef\\xbb\\xbf")
        self.assertEqual(self.a.read_bytes(), songs[0].path.read_bytes())
        self.assertEqual(len(distribute_blocks(songs, 3, 25)), 3)

    def test_no_inadvertent_source_deletion_or_overwrite(self):
        a=read_track(self.a)
        before=self.a.read_bytes()
        # A nonexistent output path must never act on MP3 metadata.
        self.assertEqual(append_unique([a], []), [a])
        with self.assertRaises(ValueError):
            save_playlist(self.root / "bad.mp3", [a])
        self.assertEqual(self.a.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
