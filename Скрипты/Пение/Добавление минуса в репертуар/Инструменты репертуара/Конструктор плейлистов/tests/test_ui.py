import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from app import MainWindow
from core import read_track


class SetlistUiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_create_window_drag_modes_and_non_destructive_remove(self):
        with TemporaryDirectory() as directory:
            from mutagen.id3 import ID3, TPE1, TIT2, MVNM
            mp3 = Path(directory) / "тест.mp3"
            mp3.write_bytes(b"")
            tags = ID3()
            tags.add(TPE1(encoding=3, text=["Исполнитель"]))
            tags.add(TIT2(encoding=3, text=["Песня"]))
            tags.add(MVNM(encoding=3, text=["Песня"]))
            tags.save(mp3)
            ui = MainWindow()
            track = read_track(mp3)
            ui.current.set_tracks([track])
            ui.history.set_tracks([track])
            self.assertEqual(ui.current.rowCount(), 1)
            self.assertEqual(ui.current.columnCount(), 4)
            self.assertEqual(ui.current.horizontalHeaderItem(1).text(), "Сложность · Песня")
            self.assertEqual(ui.current.item(0, 1).text(), "Песня")
            self.assertEqual(ui.current.item(0, 2).text(), "Исполнитель")
            self.assertEqual(ui.history.rowCount(), 1)
            self.assertEqual(ui.current.defaultDropAction(), Qt.DropAction.CopyAction)
            self.assertIn("100%", ui.summary.text())
            ui.current.selectRow(0)
            ui.remove_selected(ui.current)
            self.assertEqual(ui.current.rowCount(), 0)
            self.assertTrue(mp3.is_file(), "Deleting row must not delete MP3")
            self.assertEqual(ui.history.rowCount(), 1)
            ui.close()


if __name__ == "__main__":
    unittest.main()
