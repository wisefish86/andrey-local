"""Offscreen integration test for manual cover linking."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from mutagen.id3 import ID3, TCOM

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from PySide6.QtWidgets import QApplication, QMessageBox
import review_gui
import cover_links
from sync_versions import planned_folders, cross_folder_suggestions, current_version, apply_changes


class CoverGuiTest(unittest.TestCase):
    def test_link_and_remember(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / "Bad Guy _____ Billie Eilish"
            cover = root / "Bad Guy (cover) _____ The Interrupters"
            original.mkdir()
            cover.mkdir()
            files = []
            for folder in (original, cover):
                p = folder / "minus ֎.mp3"
                p.write_bytes(b"")
                ID3().save(p)
                files.append(p)
            decision_path = root / "links.json"
            def backed_up(items, _dest):
                return apply_changes(items, root / "backups")
            with patch.object(cover_links, "PATH", decision_path), patch.object(
                    review_gui, "apply_changes", side_effect=backed_up), patch.object(
                    QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), patch.object(
                    QMessageBox, "information"):
                window = review_gui.ReviewWindow(
                    root, planned_folders(root), cross_folder_suggestions(root))
                self.assertEqual(len(window.options), 1)
                window.options[0][1].setCurrentIndex(1)
                window.apply_selected()
                self.assertEqual(current_version(ID3(files[0])), "в-Bad-Guy")
                self.assertEqual(current_version(ID3(files[1])), "в-Bad-Guy")
                self.assertEqual(cover_links.read_links()[str(cover)], str(original))
                self.assertEqual(len(list((root / "backups").rglob("*.mp3"))), 2)
                window.close()


if __name__ == "__main__":
    unittest.main()
