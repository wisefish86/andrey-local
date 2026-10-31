import sys
import tempfile
import unittest
from pathlib import Path
from mutagen.id3 import ID3, TIT1

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sync_versions import planned_folders, apply_changes, current_version, generated_version


def mp3(path: Path, title_tags=""):
    path.write_bytes(b"")
    tags = ID3()
    if title_tags:
        tags.add(TIT1(encoding=3, text=[title_tags]))
    tags.save(path)


class VersionSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.song = self.root / "Не вспоминай _____ Niletto & Олег Майами & Леша Свик"
        self.song.mkdir()

    def test_generation_from_folder_and_first_artist(self):
        self.assertEqual(generated_version(self.song.name), "в-Не вспоминай-Niletto")

    def test_ignore_single_nested_and_non_marker(self):
        mp3(self.song / "one ֎.mp3")
        mp3(self.song / "other.mp3")
        sub = self.song / "Additi0ns"
        sub.mkdir()
        mp3(sub / "two ֎.mp3")
        self.assertEqual(planned_folders(self.root), [])

    def test_new_version_and_preserve_unrelated_tags(self):
        a = self.song / "a ֎.mp3"
        b = self.song / "b ֎.mp3"
        mp3(a, "а-Универсальная; Я-рус")
        mp3(b, "н-Нежная")
        plan = planned_folders(self.root)
        self.assertEqual(plan[0]["target"], "в-Не вспоминай-Niletto")
        count, failures = apply_changes(plan, self.root / "backups")
        self.assertEqual((count, failures), (2, []))
        self.assertEqual(current_version(ID3(a)), "в-Не вспоминай-Niletto")
        self.assertIn("а-Универсальная", str(ID3(a).getall("TIT1")[0].text))
        self.assertEqual(planned_folders(self.root)[0]["status"], "ok")

    def test_first_existing_version_wins_conflicts(self):
        a = self.song / "01 ֎.mp3"
        b = self.song / "02 ֎.mp3"
        c = self.song / "03 ֎.mp3"
        mp3(a, "в-МоёСокращение")
        mp3(b, "в-Другое")
        mp3(c)
        plan = planned_folders(self.root)
        self.assertEqual(plan[0]["target"], "в-МоёСокращение")
        count, failures = apply_changes(plan, self.root / "backups")
        self.assertEqual((count, failures), (2, []))
        self.assertTrue(all(current_version(ID3(p)) == "в-МоёСокращение" for p in (a, b, c)))
        self.assertEqual(len(list((self.root / "backups").rglob("*.mp3"))), 2)


if __name__ == "__main__":
    unittest.main()
