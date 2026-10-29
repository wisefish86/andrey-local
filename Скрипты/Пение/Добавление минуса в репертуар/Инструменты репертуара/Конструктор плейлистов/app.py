"""First-stage Windows setlist editor: drag local MP3 links, inspect tags, export M3U8."""
from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import QItemSelectionModel, QMimeData, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDrag, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QFileDialog, QHeaderView, QLabel, QMainWindow,
    QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QHBoxLayout,
)

from core import Track, append_unique, expand_inputs, move_rows, parse_dropped_text
from core import read_track, repeated_from_history, replace_rows, save_playlist


class ReadWorker(QThread):
    loaded = Signal(str, object, object)

    def __init__(self, destination: str, paths: list[Path], parent=None):
        super().__init__(parent)
        self.destination = destination
        self.paths = paths

    def run(self):
        expanded, warnings = expand_inputs(self.paths)
        tracks = []
        for path in expanded:
            try:
                track = read_track(path)
                tracks.append(track)
                if track.error:
                    warnings.append(f"{path.name}: {track.error}")
            except (OSError, ValueError) as exc:
                warnings.append(f"{path}: {exc}")
        self.loaded.emit(self.destination, tracks, warnings)


class TrackTable(QTableWidget):
    filesDropped = Signal(str, object)
    selectionChanged = Signal()

    HEADERS = ("№", "Исполнитель", "Песня / версия", "Сложность", "Язык", "Энергия", "Рейтинг", "BPM")

    def __init__(self, name: str, owner):
        super().__init__(0, len(self.HEADERS), owner)
        self.name = name
        self.owner = owner
        self.tracks: list[Track] = []
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(False)  # Setlist order is user order, not table sort.
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.setMouseTracking(True)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setVisible(False)
        self.itemSelectionChanged.connect(self.selectionChanged)

    def selected_rows(self) -> list[int]:
        return sorted({index.row() for index in self.selectionModel().selectedRows()})

    def selected_tracks(self) -> list[Track]:
        return [self.tracks[i] for i in self.selected_rows()]

    def set_tracks(self, tracks: list[Track], selected_paths=()):
        self.tracks = list(tracks)
        wanted = {str(path).casefold() for path in selected_paths}
        self.setRowCount(len(self.tracks))
        for row, track in enumerate(self.tracks):
            values = (str(row + 1), track.artist, track.title, track.difficulty,
                      track.language, track.energy, track.rating, track.bpm)
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if col in (0, 3, 6, 7):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setToolTip(
                    str(track.path) + "\nСтатус: " + track.status +
                    "\nРоль в блоке: " + track.role +
                    ("\n" + track.error if track.error else "")
                )
                if track.difficulty.startswith("сл-4"):
                    item.setForeground(QColor("#ffad9f"))
                self.setItem(row, col, item)
            self.setRowHeight(row, 30)
        self.clearSelection()
        selection_model = self.selectionModel()
        for i, track in enumerate(self.tracks):
            if str(track.path).casefold() in wanted:
                selection_model.select(self.model().index(i, 0),
                                       QItemSelectionModel.SelectionFlag.Select |
                                       QItemSelectionModel.SelectionFlag.Rows)
        self.owner.refresh_summary()

    def dragEnterEvent(self, event):
        mime = event.mimeData()
        if isinstance(event.source(), TrackTable) or mime.hasUrls() or mime.hasText():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            self.owner.statusBar().showMessage("Источник не передал пути: " + ", ".join(mime.formats()), 10000)
            event.ignore()

    def dragMoveEvent(self, event):
        if isinstance(event.source(), TrackTable) or event.mimeData().hasUrls() or event.mimeData().hasText():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        source = event.source()
        if isinstance(source, TrackTable):
            moving = source.selected_tracks()
            if source is self:
                target = self.rowAt(int(event.position().y()))
                if target < 0:
                    target = len(self.tracks)
                self.set_tracks(move_rows(self.tracks, self.selected_rows(), target),
                                (track.path for track in moving))
            else:
                self.set_tracks(append_unique(self.tracks, moving),
                                (track.path for track in moving))
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            return
        mime = event.mimeData()
        paths = [Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile()] if mime.hasUrls() else []
        if not paths and mime.hasText():
            paths = parse_dropped_text(mime.text())
        if not paths:
            self.owner.statusBar().showMessage(
                "Не получены локальные пути. Форматы: " + ", ".join(mime.formats()), 12000
            )
            event.ignore()
            return
        self.filesDropped.emit(self.name, paths)
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()

    def startDrag(self, _supported_actions):
        selected = self.selected_tracks()
        if not selected:
            return
        drag = QDrag(self)
        data = QMimeData()
        data.setUrls([QUrl.fromLocalFile(str(track.path)) for track in selected])
        drag.setMimeData(data)
        # Important: never request a MoveAction; MusicBee/AIMP should get file links.
        drag.exec(Qt.DropAction.CopyAction)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self.owner.remove_selected(self)
            event.accept()
            return
        super().keyPressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Конструктор плейлистов · безопасный редактор")
        self.resize(1350, 780)
        self.worker = None
        self.setStyleSheet("""
            QMainWindow, QWidget { background:#111922; color:#e6edf5; font-size:12px; }
            QTableWidget { background:#172333; alternate-background-color:#1b2938;
                           border:1px solid #35465b; gridline-color:#29384a;
                           selection-background-color:#386a89; }
            QHeaderView::section { background:#223247; color:#e6edf5; padding:7px; border:none; }
            QPushButton { background:#263a50; color:#f4f7fa; border:1px solid #51667d;
                          border-radius:7px; padding:9px 12px; }
            QPushButton:hover { background:#35516e; }
            QPushButton:focus-visible { border:2px solid #e5b85f; }
            QLabel { color:#d8e4ef; }
        """)
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(15, 14, 15, 10)
        outer.setSpacing(10)
        intro = QLabel("Перетащи MP3 или M3U8 из MusicBee / Проводника. "
                       "Внутри программы хранятся только ссылки; исходные файлы не изменяются.")
        intro.setWordWrap(True)
        outer.addWidget(intro)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)
        self.current = self.make_panel(splitter, "Текущий плейлист", "current")
        self.history = self.make_panel(splitter, "История прошлого выступления", "history")
        splitter.setSizes([860, 420])
        self.summary = QLabel("Перетащи файлы или используй «Добавить MP3/M3U8»")
        self.summary.setWordWrap(True)
        outer.addWidget(self.summary)
        self.setCentralWidget(root)
        self.statusBar().showMessage("Готово · MP3 защищены от изменения и удаления")
        QShortcut(QKeySequence("Ctrl+S"), self, activated=lambda: self.export_list(self.current))
        QShortcut(QKeySequence("Ctrl+O"), self, activated=lambda: self.pick_files("current"))
        self.refresh_summary()

    def make_panel(self, splitter, title: str, name: str) -> TrackTable:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        heading = QLabel(title)
        heading.setStyleSheet("font-size:16px;font-weight:700;")
        layout.addWidget(heading)
        table = TrackTable(name, self)
        table.filesDropped.connect(self.import_files)
        layout.addWidget(table, 1)
        row = QHBoxLayout()
        layout.addLayout(row)
        def button(label, callback):
            b = QPushButton(label)
            b.clicked.connect(callback)
            row.addWidget(b)
            return b
        button("+ MP3/M3U8", lambda n=name: self.pick_files(n))
        button("Убрать", lambda t=table: self.remove_selected(t))
        if name == "current":
            button("↑", lambda: self.shift_selected(table, -1))
            button("↓", lambda: self.shift_selected(table, 1))
            button("Заменить…", self.replace_selected)
        button("Сохранить M3U8", lambda t=table: self.export_list(t))
        splitter.addWidget(panel)
        return table

    def refresh_summary(self):
        # This runs while the second table is being created too.
        if not hasattr(self, "current") or not hasattr(self, "history"):
            return
        count, percentage = repeated_from_history(self.current.tracks, self.history.tracks)
        message = (f"Текущий: {len(self.current.tracks)} файлов · "
                   f"История: {len(self.history.tracks)} файлов · "
                   f"Повторы песен с прошлого выступления: {count} ({percentage:.0f}%)")
        if self.current.tracks and self.history.tracks and percentage > 20:
            message += "  ⚠ Выше ориентира 10–20%."
        self.summary.setText(message)

    def pick_files(self, destination: str):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Добавить ссылки на MP3 / плейлист",
            str(Path.home()),
            "Песни и плейлисты (*.mp3 *.m3u *.m3u8)"
        )
        if paths:
            self.import_files(destination, [Path(p) for p in paths])

    def import_files(self, destination: str, paths: list[Path]):
        if self.worker and self.worker.isRunning():
            self.statusBar().showMessage("Дождись завершения чтения предыдущей группы.", 5000)
            return
        self.worker = ReadWorker(destination, paths, self)
        self.worker.loaded.connect(self.finish_import)
        self.worker.finished.connect(self.finish_worker)
        self.worker.start()
        self.statusBar().showMessage("Чтение тегов…")

    def finish_import(self, destination: str, tracks: list[Track], warnings: list[str]):
        table = self.current if destination == "current" else self.history
        table.set_tracks(append_unique(table.tracks, tracks), (t.path for t in tracks))
        self.statusBar().showMessage(f"Прочитано {len(tracks)} MP3, ошибок/пропусков: {len(warnings)}", 10000)
        if warnings:
            QMessageBox.warning(self, "Частично загружено", "\n".join(warnings[:15]))
    def finish_worker(self):
        worker = self.worker
        self.worker = None
        if worker is not None:
            worker.deleteLater()

    def remove_selected(self, table: TrackTable):
        indexes = set(table.selected_rows())
        if not indexes:
            return
        table.set_tracks([track for index, track in enumerate(table.tracks) if index not in indexes])
        self.statusBar().showMessage(
            f"Убрано из списка: {len(indexes)}. MP3 на диске не затронуты.", 7000
        )

    def shift_selected(self, table: TrackTable, direction: int):
        rows = table.selected_rows()
        if not rows:
            return
        # A single step preserves the order of a multi-row selection.
        destination = rows[0] + direction if direction < 0 else rows[-1] + direction + 1
        table.set_tracks(move_rows(table.tracks, rows, destination),
                         [track.path for track in table.selected_tracks()])

    def replace_selected(self):
        rows = self.current.selected_rows()
        if not rows:
            QMessageBox.information(self, "Замена", "Выдели одну или несколько песен для замены.")
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Какими MP3 заменить выделенные?",
            str(Path.home()), "MP3 (*.mp3)")
        if not paths:
            return
        replacements = []
        for path in paths:
            try:
                replacements.append(read_track(Path(path)))
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "Замена", str(exc))
                return
        result = replace_rows(self.current.tracks, rows, replacements)
        self.current.set_tracks(result, [track.path for track in replacements])
        self.statusBar().showMessage(
            "Заменены только записи в списке. Оригинальные MP3 сохранены.", 7000
        )

    def export_list(self, table: TrackTable):
        if not table.tracks:
            QMessageBox.information(self, "Сохранение", "Плейлист пуст.")
            return
        suggest = "Плейлист.m3u8" if table.name == "current" else "История выступления.m3u8"
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить ссылки как M3U8",
            str(Path.home() / suggest), "MusicBee / AIMP M3U8 (*.m3u8)")
        if not path:
            return
        try:
            name = Path(path)
            if not name.suffix:
                name = name.with_suffix(".m3u8")
            save_playlist(name, table.tracks)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Ошибка сохранения", str(exc))
            return
        self.statusBar().showMessage(f"Плейлист сохранён: {name}", 10000)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Конструктор плейлистов")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
