"""First-stage Windows setlist editor: drag local MP3 links, inspect tags, export M3U8."""
from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import QItemSelectionModel, QMimeData, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDrag, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QFileDialog, QHeaderView, QLabel, QMainWindow,
    QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QHBoxLayout, QSpinBox, QDialog, QComboBox, QLineEdit, QPlainTextEdit, QFormLayout, QScrollArea,
)

from core import Track, append_unique, expand_inputs, move_rows, parse_dropped_text
from core import read_track, repeated_from_history, replace_rows, save_playlist, load_config, scan_library, distribute_blocks, export_block_playlist, block_duration, vocal_warnings, unique_songs, add_unique_songs, replacement_candidates, filtered_restaurant_catalog, load_restaurant_presets, save_restaurant_presets, link_versions


class ReadWorker(QThread):
    loaded = Signal(str, object, object)

    def __init__(self, destination: str, paths: list[Path], parent=None):
        super().__init__(parent)
        self.destination = destination
        self.paths = paths

    def run(self):
        if self.destination == "catalog":
            try:
                expanded, warnings = scan_library(load_config()), []
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.loaded.emit(self.destination, [], [str(exc)])
                return
        else:
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
    PLAYLIST_HEADERS = ("№", "Сложность · Песня", "Исполнитель")
    DIFFICULTY_SIGNS = {"сл-1": "🠒", "сл-2": "⇉", "сл-3": "⇶", "сл-4": "^"}

    def __init__(self, name: str, owner):
        headers = self.PLAYLIST_HEADERS if name == "current" or name.startswith(("block:", "reserve:")) else self.HEADERS
        super().__init__(0, len(headers), owner)
        self.name = name
        self.owner = owner
        self.tracks: list[Track] = []
        self.setHorizontalHeaderLabels(headers)
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
        self.horizontalHeader().setSectionResizeMode(1 if name == "current" or name.startswith(("block:", "reserve:")) else 2, QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setVisible(False)
        self.itemSelectionChanged.connect(self.selectionChanged)

    def selected_rows(self) -> list[int]:
        return sorted({index.row() for index in self.selectionModel().selectedRows()})

    def selected_tracks(self) -> list[Track]:
        return [self.tracks[i] for i in self.selected_rows()]

    def set_tracks(self, tracks: list[Track], selected_paths=()):
        self.tracks = list(tracks)
        if self.name == "current" and hasattr(self.owner, "block_plan"):
            self.owner.block_plan = None
        wanted = {str(path).casefold() for path in selected_paths}
        self.setRowCount(len(self.tracks))
        for row, track in enumerate(self.tracks):
            sign = next((symbol for key, symbol in self.DIFFICULTY_SIGNS.items()
                         if key in track.difficulty), "")
            values = ((str(row + 1), f"{sign}{track.title}" if sign else track.title, track.artist)
                      if self.name == "current" or self.name.startswith(("block:", "reserve:")) else
                      (str(row + 1), track.artist, track.title, track.difficulty,
                       track.language, track.energy, track.rating, track.bpm))
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if col == 0 or (self.name != "current" and col in (3, 6, 7)):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setToolTip(
                    str(track.path) + "\nСтатус: " + track.status +
                    "\nРоль в блоке: " + track.role +
                    ("\n" + track.error if track.error else "")
                )
                if track.difficulty.startswith("сл-4") and (self.name not in ("current",) and not self.name.startswith(("block:", "reserve:")) or col == 1):
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
        if self.name == "catalog":
            event.ignore()
            return
        mime = event.mimeData()
        if isinstance(event.source(), TrackTable) or mime.hasUrls() or mime.hasText():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            self.owner.statusBar().showMessage("Источник не передал пути: " + ", ".join(mime.formats()), 10000)
            event.ignore()

    def dragMoveEvent(self, event):
        if self.name == "catalog":
            event.ignore()
            return
        if isinstance(event.source(), TrackTable) or event.mimeData().hasUrls() or event.mimeData().hasText():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        if self.name == "catalog":
            event.ignore()
            return
        source = event.source()
        if isinstance(source, TrackTable) and self.name.startswith(("block:", "reserve:")):
            self.owner.drop_into_block(source, self, event)
            return
        if isinstance(source, TrackTable):
            moving = source.selected_tracks()
            if source is self:
                target = self.rowAt(int(event.position().y()))
                if target < 0:
                    target = len(self.tracks)
                self.set_tracks(move_rows(self.tracks, self.selected_rows(), target),
                                (track.path for track in moving))
            else:
                self.set_tracks((add_unique_songs if self.name == "current" else append_unique)(self.tracks, moving),
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
        if event.key() == Qt.Key.Key_Delete and self.name != "catalog":
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
        self.block_plan = None
        self.block_tables = {}
        self.replacement_history = {}
        self.catalog_all = []
        self.presets = load_restaurant_presets()
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
        intro = QLabel("Каталог минусов загружается автоматически. "
                       "Перетащи песни в плейлист и сохрани M3U8; исходные MP3 не изменяются.")
        intro.setWordWrap(True)
        outer.addWidget(intro)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)
        self.catalog = self.make_panel(splitter, "Каталог минусов", "catalog")
        self.current = self.make_panel(splitter, "Текущий плейлист", "current")
        self.history = self.make_panel(splitter, "История прошлого выступления", "history")
        self.history.parentWidget().hide()
        splitter.setSizes([780, 560, 0])
        venue_controls = QHBoxLayout()
        outer.addLayout(venue_controls)
        venue_controls.addWidget(QLabel("Пресет ресторана:"))
        self.venue = QComboBox()
        self.venue.currentTextChanged.connect(self.apply_restaurant_preset)
        venue_controls.addWidget(self.venue)
        edit_venue = QPushButton("Настроить фильтры…")
        edit_venue.clicked.connect(self.edit_restaurant_preset)
        venue_controls.addWidget(edit_venue)
        venue_controls.addStretch(1)
        self.reload_venue_names()
        options = load_config().get("blocks", {})
        controls = QHBoxLayout()
        outer.addLayout(controls)
        controls.addWidget(QLabel("Блоков:"))
        self.block_count = QSpinBox()
        self.block_count.setRange(3, 6)
        self.block_count.setValue(options.get("default_count", 4))
        controls.addWidget(self.block_count)
        controls.addWidget(QLabel("Минут на блок:"))
        self.block_minutes = QSpinBox()
        self.block_minutes.setRange(10, 60)
        self.block_minutes.setValue(options.get("target_minutes", 25))
        controls.addWidget(self.block_minutes)
        controls.addWidget(QLabel("Резервов на блок:"))
        self.reserve_count = QSpinBox()
        self.reserve_count.setRange(0, 5)
        self.reserve_count.setValue(options.get("reserve_per_block", 2))
        controls.addWidget(self.reserve_count)
        generate = QPushButton("Сформировать блоки")
        generate.clicked.connect(self.generate_blocks)
        controls.addWidget(generate)
        controls.addStretch(1)
        self.block_count.valueChanged.connect(self.invalidate_plan)
        self.block_minutes.valueChanged.connect(self.invalidate_plan)
        self.reserve_count.valueChanged.connect(self.invalidate_plan)
        self.summary = QLabel("Перетащи файлы или используй «Добавить MP3/M3U8»")
        self.summary.setWordWrap(True)
        outer.addWidget(self.summary)
        self.setCentralWidget(root)
        self.statusBar().showMessage("Готово · MP3 защищены от изменения и удаления")
        QShortcut(QKeySequence("Ctrl+S"), self, activated=lambda: self.export_list(self.current))
        QShortcut(QKeySequence("Ctrl+O"), self, activated=lambda: self.pick_files("current"))
        self.refresh_summary()
        try:
            if load_config().get("library", {}).get("auto_load", True):
                self.reload_catalog()
        except (OSError, ValueError) as exc:
            self.statusBar().showMessage(f"Конфигурация: {exc}", 15000)

    def make_panel(self, splitter, title: str, name: str) -> TrackTable:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        heading = QLabel(title)
        heading.setStyleSheet("font-size:16px;font-weight:700;")
        layout.addWidget(heading)
        table = TrackTable(name, self)
        table.filesDropped.connect(self.import_files)
        layout.addWidget(table, 1)
        if name == "current":
            self.block_area = QScrollArea()
            self.block_area.setWidgetResizable(True)
            self.block_area.hide()
            layout.addWidget(self.block_area, 1)
        row = QHBoxLayout()
        layout.addLayout(row)
        def button(label, callback):
            b = QPushButton(label)
            b.clicked.connect(callback)
            row.addWidget(b)
            return b
        if name == "catalog":
            self.catalog_search = QLineEdit()
            self.catalog_search.setPlaceholderText("Поиск по песне, исполнителю, версии или тегу…")
            self.catalog_search.setClearButtonEnabled(True)
            self.catalog_search.textChanged.connect(self.apply_restaurant_preset)
            layout.insertWidget(1, self.catalog_search)
            button("↻ Обновить", self.reload_catalog)
            button("→ В плейлист", self.add_catalog_selection)
            button("Связать версии…", self.link_selected_versions)
        else:
            button("+ MP3/M3U8", lambda n=name: self.pick_files(n))
            button("Убрать", lambda t=table: self.remove_selected(t))
        if name == "current":
            button("↑", lambda: self.shift_selected(table, -1))
            button("↓", lambda: self.shift_selected(table, 1))
            button("Заменить ↻", self.quick_replace)
            button("Выбрать файл…", self.replace_selected)
            button("Сохранить блоки M3U8", self.export_blocks)
        if name != "catalog":
            button("Сохранить M3U8", lambda t=table: self.export_list(t))
        splitter.addWidget(panel)
        return table

    def refresh_summary(self):
        # This runs while the second table is being created too.
        if not hasattr(self, "current") or not hasattr(self, "history"):
            return
        count, percentage = repeated_from_history(self.current.tracks, self.history.tracks)
        message = (f"Каталог: {len(self.catalog.tracks)} файлов · "
                   f"Текущий: {len(self.current.tracks)} файлов · "
                   f"История: {len(self.history.tracks)} файлов · "
                   f"Повторы песен с прошлого выступления: {count} ({percentage:.0f}%)")
        if self.current.tracks and self.history.tracks and percentage > 20:
            message += "  ⚠ Выше ориентира 10–20%."
        self.summary.setText(message)

    def reload_venue_names(self, selected=None):
        chosen = selected or self.venue.currentText() or "Все песни"
        self.venue.blockSignals(True)
        self.venue.clear()
        self.venue.addItems(["Все песни"] + sorted(self.presets))
        self.venue.setCurrentText(chosen if chosen in self.presets or chosen == "Все песни" else "Все песни")
        self.venue.blockSignals(False)
        self.apply_restaurant_preset()

    def apply_restaurant_preset(self, *_):
        if not hasattr(self, "catalog"):
            return
        preset = self.presets.get(self.venue.currentText(), {})
        matches = filtered_restaurant_catalog(self.catalog_all, preset)
        query = self.catalog_search.text().strip().casefold() if hasattr(self, "catalog_search") else ""
        if query:
            words = query.split()
            matches = [t for t in matches if all(word in
                       " ".join((t.title, t.clean_title, t.artist, t.work_id,
                                 t.difficulty, t.role, t.energy, " ".join(t.tags))).casefold()
                       for word in words)]
        self.catalog.set_tracks(matches)

    def edit_restaurant_preset(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Пресет ресторана")
        dialog.resize(510, 430)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        layout.addLayout(form)
        name = QLineEdit(dialog)
        current = self.venue.currentText()
        name.setText("" if current == "Все песни" else current)
        form.addRow("Ресторан / название пресета:", name)
        existing = self.presets.get(current, {})
        included = QPlainTextEdit(dialog)
        included.setPlainText("\\n".join(existing.get("include_tags", [])))
        excluded = QPlainTextEdit(dialog)
        excluded.setPlainText("\\n".join(existing.get("exclude_tags", [])))
        form.addRow("Допустить по тегам (один на строку):", included)
        form.addRow("Исключить по тегам (один на строку):", excluded)
        explanation = QLabel("Пустое поле «Допустить» — без дополнительных ограничений. "
                             "Если оно заполнено, подходит песня с любым из перечисленных тегов. "
                             "Исключения всегда имеют приоритет.")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        save = QPushButton("Сохранить пресет")
        layout.addWidget(save)
        def commit():
            title = name.text().strip()
            if not title or title == "Все песни":
                QMessageBox.warning(dialog, "Пресет", "Укажи уникальное название ресторана.")
                return
            def lines(widget):
                return list(dict.fromkeys(x.strip() for x in widget.toPlainText().splitlines() if x.strip()))
            if current not in ("Все песни", title) and current in self.presets:
                QMessageBox.information(dialog, "Пресет", "Создан новый пресет; прежний сохранён.")
            self.presets[title] = {"include_tags": lines(included), "exclude_tags": lines(excluded)}
            try:
                save_restaurant_presets(self.presets)
            except OSError as exc:
                QMessageBox.warning(dialog, "Ошибка сохранения", str(exc))
                return
            self.reload_venue_names(title)
            dialog.accept()
        save.clicked.connect(commit)
        dialog.exec()

    def reload_catalog(self):
        if self.worker and self.worker.isRunning():
            self.statusBar().showMessage("Сканирование уже выполняется.", 5000)
            return
        self.worker = ReadWorker("catalog", [], self)
        self.worker.loaded.connect(self.finish_import)
        self.worker.finished.connect(self.finish_worker)
        self.worker.start()
        self.statusBar().showMessage("Сканирование основного репертуара…")

    def link_selected_versions(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Выбери все версии одного произведения (2 или больше)",
            str(Path(load_config()["library"]["path"])), "Минусовки (*.mp3)")
        if len(paths) < 2:
            return
        code, ok = __import__("PySide6.QtWidgets", fromlist=["QInputDialog"]).QInputDialog.getText(
            self, "Общий тег произведения", "Тег для всех выбранных файлов (например, в-мамабурито):")
        if not ok:
            return
        answer = QMessageBox.question(self, "Подтвердить запись ID3",
            f"Записать общий тег {code} в {len(paths)} MP3?\\n"
            "Перед изменением каждого файла будут созданы полные резервные копии.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        from datetime import datetime
        backup = Path(__file__).with_name("data") / "version_backups" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        try:
            count = link_versions([Path(p) for p in paths], code, backup)
        except (OSError, ValueError, Exception) as exc:
            QMessageBox.critical(self, "Не удалось связать версии", str(exc))
            return
        self.statusBar().showMessage(f"Связано файлов: {count}. Резервные копии: {backup}", 14000)
        self.reload_catalog()

    def add_catalog_selection(self):
        chosen = self.catalog.selected_tracks()
        if chosen:
            self.current.set_tracks(add_unique_songs(self.current.tracks, chosen),
                                    [t.path for t in chosen])

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
        if destination.startswith(("block:", "reserve:")) and self.block_plan is not None:
            kind, index = destination.split(":")
            target = self.block_plan[int(index)][0 if kind == "block" else 1]
            from core import song_key
            used = {song_key(t) for main, reserve in self.block_plan for t in main + reserve}
            for track in tracks:
                if song_key(track) not in used:
                    target.append(track)
                    used.add(song_key(track))
            self.current.tracks = [song for main, reserve in self.block_plan for song in main]
            self.render_block_editor()
            return
        table = {"current": self.current, "history": self.history, "catalog": self.catalog}[destination]
        if destination == "catalog":
            self.catalog_all = tracks
            self.apply_restaurant_preset()
        else:
            combine = add_unique_songs if destination == "current" else append_unique
            table.set_tracks(combine(table.tracks, tracks), (t.path for t in tracks))
        self.statusBar().showMessage(f"Прочитано {len(tracks)} MP3, ошибок/пропусков: {len(warnings)}", 10000)
        if warnings and destination == "catalog":
            self.statusBar().showMessage("Каталог: " + "; ".join(warnings[:3]), 15000)
        elif warnings:
            QMessageBox.warning(self, "Частично загружено", "\n".join(warnings[:15]))
    def finish_worker(self):
        worker = self.worker
        self.worker = None
        if worker is not None:
            worker.deleteLater()

    def remove_selected(self, table: TrackTable):
        indexes = set(table.selected_rows())
        if not indexes or table.name == "catalog":
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

    def quick_replace(self):
        rows = self.current.selected_rows()
        if len(rows) != 1:
            QMessageBox.information(self, "Замена", "Выдели одну песню для быстрой замены.")
            return
        row = rows[0]
        selected = self.current.tracks[row]
        # Track the original slot's rejected songs across repeated clicks.
        key = (row, len(self.current.tracks))
        rejected = self.replacement_history.setdefault(key, set())
        rejected.add(str(selected.path).casefold())
        options = replacement_candidates(self.current.tracks, row, self.catalog.tracks, rejected)
        if not options:
            self.statusBar().showMessage("Подходящие альтернативы закончились.", 7000)
            return
        next_track = options[0]
        updated = list(self.current.tracks)
        updated[row] = next_track
        self.current.set_tracks(updated, [next_track.path])
        self.statusBar().showMessage(
            f"Замена: {selected.title} → {next_track.title}. Ещё раз — следующая альтернатива.", 9000)

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

    def invalidate_plan(self, *_):
        self.block_plan = None

    def generate_blocks(self):
        if self.block_plan is not None:
            response = QMessageBox.question(self, "Пересоздать блоки?",
                "Блоки уже редактировались. Пересоздание изменит их распределение и резервы. Продолжить?")
            if response != QMessageBox.StandardButton.Yes:
                return
        if not self.current.tracks:
            QMessageBox.information(self, "Блоки", "Сначала добавь песни в текущий плейлист.")
            return
        count = self.block_count.value()
        target = self.block_minutes.value()
        groups = distribute_blocks(self.current.tracks, count, target)
        used = {str(t.path).casefold() for t in self.current.tracks}
        available = [
            t for t in self.catalog.tracks
            if str(t.path).casefold() not in used
            and t.status.startswith(("г-1-", "г-2-", "г-3-"))
            and t.difficulty.startswith(("сл-1", "сл-2"))
        ]
        result = []
        for main, _ in groups:
            chosen = available[:self.reserve_count.value()]
            del available[:len(chosen)]
            result.append((main, chosen))
        self.block_plan = result
        self.render_block_editor()
        counts = ", ".join(f"{len(main)}+{len(reserve)}" for main, reserve in result)
        self.statusBar().showMessage(f"Блоки (основные+резерв): {counts}", 15000)
        self.statusBar().showMessage("Блоки готовы: " + counts, 12000)

    def render_block_editor(self):
        if self.block_plan is None:
            return
        container = QWidget()
        layout = QVBoxLayout(container)
        self.block_tables = {}
        for idx, (main, reserve) in enumerate(self.block_plan):
            for kind, songs in (("block", main), ("reserve", reserve)):
                key = f"{kind}:{idx}"
                minutes, missing = block_duration(songs)
                heading = QLabel(f"{idx + 1} {'блок' if kind == 'block' else 'запас'}"
                                 f" · {int(minutes)}:{int(round(minutes % 1 * 60)):02d}"
                                 + (f" · {missing} без длительности" if missing else ""))
                heading.setStyleSheet("font-weight:700;font-size:14px;padding-top:9px;")
                layout.addWidget(heading)
                table = TrackTable(key, self)
                table.setMinimumHeight(max(72, min(260, len(songs) * 30 + 36)))
                table.set_tracks(songs)
                self.block_tables[key] = table
                layout.addWidget(table)
        layout.addStretch()
        self.block_area.setWidget(container)
        self.current.hide()
        self.block_area.show()

    def drop_into_block(self, source, target, event):
        if self.block_plan is None:
            event.ignore()
            return
        moving = source.selected_tracks()
        if not moving:
            event.ignore()
            return
        key = target.name
        kind, number = key.split(":")
        destination = self.block_plan[int(number)][0 if kind == "block" else 1]
        # Reject duplicate songs across every block and reserve.
        from core import song_key
        chosen = {song_key(song) for song in moving}
        occupied = {song_key(song) for main, reserve in self.block_plan
                    for song in main + reserve if song not in moving}
        if chosen & occupied:
            self.statusBar().showMessage("Эта песня уже есть в программе.", 6000)
            event.ignore()
            return
        if source.name.startswith(("block:", "reserve:")):
            src_kind, src_number = source.name.split(":")
            src_list = self.block_plan[int(src_number)][0 if src_kind == "block" else 1]
            src_list[:] = [song for song in src_list if song not in moving]
        insert = target.rowAt(int(event.position().y()))
        insert = len(destination) if insert < 0 else insert
        if source is target:
            # Source was removed above; correct insertion for rows before target.
            insert -= sum(i < insert for i in source.selected_rows())
        insert = max(0, min(insert, len(destination)))
        destination[insert:insert] = moving
        self.current.tracks = [song for main, reserve in self.block_plan for song in main]
        self.render_block_editor()
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        self.statusBar().showMessage("Перенесено в блок; длительность пересчитана.", 5000)

    def export_blocks(self):
        if self.block_plan is None:
            self.generate_blocks()
            if self.block_plan is None:
                return
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить блоки с разделителями",
            str(Path.home() / "Выступление.m3u8"), "M3U8 (*.m3u8)")
        if not path:
            return
        try:
            export_block_playlist(Path(path), self.block_plan)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Ошибка экспорта", str(exc))
            return
        self.statusBar().showMessage(f"Блоки сохранены: {path}", 12000)

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
