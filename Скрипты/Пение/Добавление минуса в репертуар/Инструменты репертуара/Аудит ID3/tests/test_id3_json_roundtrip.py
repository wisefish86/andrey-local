"""Integration checks for guarded ID3 JSON import. No real repertoire files."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

from mutagen.id3 import APIC, ID3, TPE1, TIT1, TXXX, USLT

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL))
import id3_json_roundtrip as api


class Id3JsonRoundtripTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repertoire"
        self.root.mkdir()
        self.folder = self.root / "Song _____ Artist"
        self.folder.mkdir()
        self.mp3 = self.folder / "Song ֎ demo.mp3"
        self.mp3.write_bytes(b"mock-mp3-stream")
        tag = ID3()
        tag.add(TPE1(encoding=3, text=["Artist"]))
        tag.add(TIT1(encoding=3, text=["а-Унив", "с-23Фев"]))
        tag.add(TXXX(encoding=3, desc="OCCASION", text=["г-2-Рабочие"]))
        tag.add(USLT(encoding=3, lang="eng", desc="", text="Important full lyrics"))
        tag.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="", data=b"binary-art"))
        tag.save(self.mp3)
        self.config = {
            "default_fields": ["TPE1", "TIT1", "TXXX:OCCASION", "TIT2", "WOAS"],
            "excluded_folders": ["Files", "Additi0ns"],
            "max_text_chars": 2000,
            "max_changed_tracks": 500,
            "include_rating": True,
        }
        self.data = Path(self.tmp.name) / "data"
        self.orig_data = api.DATA
        api.DATA = self.data
        self.addCleanup(lambda: setattr(api, "DATA", self.orig_data))
        self.file = self.data / "exports" / "edit.json"
        self.assertEqual(api.export_json(self.root, "֎", self.config, self.file), 0)
        self.original = json.loads(self.file.read_text(encoding="utf-8"))

    def edited(self, **new_values):
        payload = copy.deepcopy(self.original)
        payload["tracks"][0]["tags"].update(new_values)
        self.file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def test_export_excludes_lyrics_art_and_audio_binary(self):
        payload = self.original
        values = payload["tracks"][0]["tags"]
        self.assertEqual(values["TIT1"], ["а-Унив", "с-23Фев"])
        self.assertEqual(values["TXXX:OCCASION"], ["г-2-Рабочие"])
        self.assertNotIn("USLT", values)
        self.assertNotIn("APIC", values)
        self.assertNotIn("Important full lyrics", self.file.read_text(encoding="utf-8"))
        self.assertNotIn("binary-art", self.file.read_text(encoding="utf-8"))

    def test_edit_preview_and_apply_preserve_binary(self):
        self.edited(TIT1=["а-Ситуац", "с-Кавказ"])
        before = self.mp3.read_bytes()
        self.assertEqual(api.run_import(self.root, "֎", self.config, self.file, False), 0)
        self.assertEqual(before, self.mp3.read_bytes(), "Preview must not change MP3")
        self.assertEqual(api.run_import(self.root, "֎", self.config, self.file, True), 0)
        tags = ID3(self.mp3)
        self.assertEqual(api.read_text(tags, "TIT1"), ["а-Ситуац", "с-Кавказ"])
        self.assertEqual(tags.getall("USLT")[0].text, "Important full lyrics")
        self.assertEqual(tags.getall("APIC")[0].data, b"binary-art")
        self.assertTrue(list((self.data / "backups").rglob("*.mp3")))

    def test_changed_source_rejected_with_no_write(self):
        self.edited(TIT1=["с-Кавказ"])
        tags = ID3(self.mp3)
        tags.add(TXXX(encoding=3, desc="additional", text=["after export"]))
        tags.save(self.mp3)
        before = self.mp3.read_bytes()
        self.assertEqual(api.run_import(self.root, "֎", self.config, self.file, True), 1)
        self.assertEqual(before, self.mp3.read_bytes())

    def test_tampered_path_and_key_rejected(self):
        self.edited(TIT1=["с-Кавказ"])
        payload = json.loads(self.file.read_text(encoding="utf-8"))
        payload["tracks"][0]["relative_path"] = "../outside.mp3"
        self.file.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(api.run_import(self.root, "֎", self.config, self.file, True), 1)
        self.edited(TIT1=["с-Кавказ"], **{"TXXX:new_without_baseline": ["x"]})
        self.assertEqual(api.run_import(self.root, "֎", self.config, self.file, True), 1)

    def test_no_edits_causes_no_backup_and_no_save(self):
        before = self.mp3.stat().st_mtime_ns
        self.assertEqual(api.run_import(self.root, "֎", self.config, self.file, True), 0)
        self.assertEqual(before, self.mp3.stat().st_mtime_ns)
        self.assertFalse((self.data / "backups").exists())


if __name__ == "__main__":
    unittest.main()
