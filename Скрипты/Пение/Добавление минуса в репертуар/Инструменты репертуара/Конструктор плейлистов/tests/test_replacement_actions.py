import os
import random
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication, QPushButton
from core import Track, display_rating, random_replacement_candidates, version_length
from app import MainWindow


def song(i, difficulty=1, work=None, variant=""):
    return Track(Path(f"/fake/{i}{variant}.mp3"), "Singer", str(i), str(i),
                 f"сл-{difficulty}-test", "Я-рус", "к-Сред", "б-4-Развитие",
                 "г-1-База", "186", "", (), work_id=work or f"в-{i}")


class ReplacementContract(unittest.TestCase):
    def test_real_musicbee_half_stars(self):
        for raw, expected in (("118", "2,5"), ("128", "3"), ("186", "3,5"),
                              ("196", "4"), ("242", "4,5"), ("255", "5")):
            self.assertEqual(display_rating(raw), expected)

    def test_unused_compositions_and_vocal_compatibility(self):
        original = [song(1, 2), song(2, 3), song(3, 2)]
        catalog = [song(2, 1, "в-2"), song(4, 3), song(5, 1), song(6, 2)]
        result = random_replacement_candidates(original, 1, catalog,
                    {song(2, 3).work_id and ("__work__", "2")},
                    rng=random.Random(3))
        self.assertEqual(result[0].work_id, "в-5")
        self.assertTrue(all(s.work_id != "в-2" for s in result))
        self.assertEqual(result[0].difficulty, "сл-1-test")

    def test_s_f_version_detected_before_other_suffix(self):
        self.assertEqual(version_length(song(1, variant=" [S] (cut)")), "S")
        self.assertEqual(version_length(song(1, variant=" [F]")), "F")


class VisibleBlockActions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def new_window(self):
        with patch("app.load_config", return_value={"library": {"auto_load": False}, "blocks": {}}):
            return MainWindow()

    def choose_menu(self, ui, caption, table=None):
        table = table or ui.block_tables.get("block:0", ui.current)
        menu = ui.build_track_menu(table)
        actions = [a for a in menu.actions() if a.text() == caption]
        self.assertEqual(len(actions), 1, caption)
        actions[0].trigger()

    def test_move_and_remove_selected_visible_song(self):
        ui = self.new_window()
        try:
            ui.block_plan = [([song(1), song(2), song(3)], [song(4)])]
            ui.render_block_editor()
            ui.block_tables["block:0"].selectRow(1)
            self.assertTrue(ui.insert_tracks_at(ui.block_tables["block:0"], "block:0", 0))
            self.assertEqual([t.title for t in ui.block_plan[0][0]], ["2", "1", "3"])
            self.assertEqual(ui.selected_playlist_slot(), ("block:0", 0))
            self.assertTrue(ui.insert_tracks_at(ui.block_tables["block:0"], "block:0", 2))
            self.assertEqual([t.title for t in ui.block_plan[0][0]], ["1", "2", "3"])
            self.choose_menu(ui, "Убрать из плейлиста")
            self.assertEqual([t.title for t in ui.block_plan[0][0]], ["1", "3"])
            self.assertEqual(len(ui.block_plan[0][1]), 1)
        finally:
            ui.close()

    def test_add_button_uses_visible_block_not_click_boolean(self):
        ui = self.new_window()
        try:
            ui.block_plan = [([song(1)], [])]
            ui.render_block_editor()
            ui.block_tables["block:0"].selectRow(0)
            with patch.object(ui, "pick_files") as pick:
                self.choose_menu(ui, "Добавить MP3/M3U8 из файла…")
                pick.assert_called_once_with("block:0")
        finally:
            ui.close()

    def test_duplicate_work_is_located_not_added(self):
        ui = self.new_window()
        try:
            ui.block_plan = [([song(1)], [song(3)])]
            ui.render_block_editor()
            ui.catalog.set_tracks([song(99, work="в-1")])
            ui.catalog.selectRow(0)
            with patch("app.QMessageBox.information") as notice:
                result = ui.insert_tracks_at(ui.catalog, "block:0", 1)
            self.assertFalse(result)
            self.assertEqual(len(ui.block_plan[0][0]), 1)
            self.assertEqual(ui.selected_playlist_slot(), ("block:0", 0))
            notice.assert_called_once()
        finally:
            ui.close()

    def test_selection_moves_from_main_to_reserve(self):
        ui = self.new_window()
        try:
            ui.block_plan = [([song(1)], [song(2)])]
            ui.render_block_editor()
            ui.block_tables["block:0"].selectRow(0)
            ui.block_tables["reserve:0"].selectRow(0)
            self.assertEqual(ui.selected_playlist_slot(), ("reserve:0", 0))
            self.assertEqual(ui.block_tables["block:0"].selected_rows(), [])
        finally:
            ui.close()

    def test_s_f_button_changes_selected_visible_version(self):
        ui = self.new_window()
        try:
            short = song(1, variant=" [S]")
            full = song(1, variant=" [F]")
            ui.block_plan = [([short], [])]
            ui.catalog_all = [short, full]
            ui.render_block_editor()
            ui.block_tables["block:0"].selectRow(0)
            with patch("app.QInputDialog.getItem", side_effect=lambda *a: (a[3][-1], True)):
                self.choose_menu(ui, "Выбрать версию S/F…")
            self.assertEqual(ui.block_plan[0][0][0].path, full.path)
        finally:
            ui.close()

    def test_reserve_heading_has_no_average_rating(self):
        ui = self.new_window()
        try:
            ui.block_plan = [([song(1), song(2)], [song(3), song(4), song(5)])]
            ui.render_block_editor()
            block_label = ui.block_area.widget().layout().itemAt(0).widget().text()
            reserve_label = ui.block_area.widget().layout().itemAt(2).widget().text()
            self.assertIn("ср. рейтинг", block_label)
            self.assertNotIn("ср. рейтинг", reserve_label)
        finally:
            ui.close()

    def test_quick_replace_uses_filtered_unused_song(self):
        ui = self.new_window()
        try:
            ui.block_plan = [([song(1, 2), song(2, 3), song(3, 2)], [song(4, 2)])]
            ui.catalog.tracks = [song(5, 3), song(6, 1), song(4, 1)]
            ui.render_block_editor()
            ui.block_tables["block:0"].selectRow(1)
            with patch("app.block_duration", return_value=(12.0, 0)), patch("app.track_minutes", return_value=3.0):
                self.choose_menu(ui, "Заменить случайной песней")
            self.assertEqual(ui.block_plan[0][0][1].work_id, "в-6")
            self.assertEqual(ui.selected_playlist_slot(), ("block:0", 1))
        finally:
            ui.close()


if __name__ == "__main__":
    unittest.main()
