import sys
import tempfile
import unittest
from pathlib import Path
from mutagen.id3 import ID3, TIT1

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sync_versions import planned_folders, apply_changes, current_version, generated_version, song_folder_info, cross_folder_suggestions, duplicate_title_targets


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

    def test_generation_uses_song_title_only(self):
        self.assertEqual(generated_version(self.song.name), "в-Не-вспоминай")

    def test_title_without_artist_and_spaces(self):
        self.assertEqual(generated_version("After Dark _____ Tito & Tarantula"), "в-After-Dark")

    def test_cover_recognition_and_ambiguous_originals(self):
        titles = ("Wonderful Life _____ Hurts",
                  "Wonderful Life _____ Zucchero",
                  "Wonderful Life (cover) _____ Max Oazo")
        for name in titles:
            folder = self.root / name
            folder.mkdir()
            mp3(folder / "one ֎.mp3")
        self.assertTrue(song_folder_info(self.root / titles[2])[3])
        targets = duplicate_title_targets(self.root)
        self.assertEqual(targets[str(self.root / titles[0])], "в-Wonderful-Life-Hurts")
        self.assertEqual(targets[str(self.root / titles[1])], "в-Wonderful-Life-Zucchero")
        suggestions = cross_folder_suggestions(self.root)
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["status"], "ambiguous")
        self.assertEqual(len(suggestions[0]["possible_originals"]), 2)
        self.assertEqual(len(planned_folders(self.root)), 2)

    def test_version_suffix_not_in_generated_work_id(self):
        self.assertEqual(generated_version("Bad Guy (cover) _____ The Interrupters"), "в-Bad-Guy")
        self.assertEqual(generated_version("Ayo Technology (cover) _____ Milow"), "в-Ayo-Technology")
        self.assertEqual(generated_version("Мама (acoustic) _____ Burito"), "в-Мама")
        self.assertEqual(generated_version("Some (Other Song) _____ Artist"), "в-Some-(Other-Song)")

    def test_duplicate_originals_override_existing_tags(self):
        for performer, tag in (("Hurts", "в-Wonderful-Life"), ("Zucchero", "в-Old")):
            folder = self.root / ("Wonderful Life _____ " + performer)
            folder.mkdir()
            mp3(folder / "one ֎.mp3", tag)
        planned = planned_folders(self.root)
        self.assertEqual(len(planned), 2)
        expected = {"Hurts": "в-Wonderful-Life-Hurts",
                    "Zucchero": "в-Wonderful-Life-Zucchero"}
        for item in planned:
            performer = Path(item["folder"]).name.split("_____")[1].strip()
            self.assertEqual(item["target"], expected[performer])
            self.assertEqual(item["status"], "change")
        written, errors = apply_changes(planned, self.root / "backup")
        self.assertEqual((written, errors), (2, []))
        self.assertEqual([item["status"] for item in planned_folders(self.root)], ["ok", "ok"])

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
        self.assertEqual(plan[0]["target"], "в-Не-вспоминай")
        count, failures = apply_changes(plan, self.root / "backups")
        self.assertEqual((count, failures), (2, []))
        self.assertEqual(current_version(ID3(a)), "в-Не-вспоминай")
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
