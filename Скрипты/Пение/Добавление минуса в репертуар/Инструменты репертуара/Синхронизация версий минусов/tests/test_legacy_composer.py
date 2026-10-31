import sys
import tempfile
import unittest
from pathlib import Path
from mutagen.id3 import ID3, TIT1
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sync_versions import planned_folders, apply_changes, current_version


class MigrationTest(unittest.TestCase):
    def test_old_work_id_is_moved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            directory = root / "Bad Guy _____ Billie Eilish"
            directory.mkdir()
            mp3 = directory / "a ֎.mp3"
            mp3.write_bytes(b"")
            tags = ID3()
            tags.add(TIT1(encoding=3, text=["Я-англ; в-Bad-Guy"]))
            tags.save(mp3)
            plan = planned_folders(root)
            self.assertEqual(len(plan), 1)
            changed, errors = apply_changes(plan, root / "backup")
            self.assertEqual((changed, errors), (1, []))
            self.assertEqual(current_version(ID3(mp3)), "в-Bad-Guy")
            self.assertNotIn("в-Bad-Guy", str(ID3(mp3).getall("TIT1")[0].text))
