"""First-stage Windows setlist editor: drag local MP3 links, inspect tags, export M3U8."""
from __future__ import annotations

from pathlib import Path
import sys
import json

from PySide6.QtCore import QItemSelectionModel, QMimeData, Qt, QThread, QUrl, Signal, QTimer
from PySide6.QtGui import QColor, QDrag, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QFileDialog, QHeaderView, QLabel, QMainWindow,
    QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QHBoxLayout, QSpinBox, QDialog, QComboBox, QLineEdit, QPlainTextEdit, QFormLayout, QScrollArea, QCheckBox, QGridLayout, QInputDialog, QMenu,
)

from core import Track, append_unique, expand_inputs, move_rows, parse_dropped_text
from core import read_track, repeated_from_history, replace_rows, save_playlist, load_config, scan_library, distribute_blocks, export_block_playlist, block_duration, vocal_warnings, unique_songs, add_unique_songs, replacement_candidates, filtered_restaurant_catalog, load_restaurant_presets, save_restaurant_presets, link_versions, build_language_balanced_list, song_key, version_length, display_rating, difficulty_level, validate_hard_spacing, random_replacement_candidates, track_minutes


class FocusTagEdit(QPlainTextEdit):
    def __init__(self, on_focus):
        super().__init__()
        self.on_focus = on_focus

    def focusInEvent(self, event):
        self.on_focus(self)
        super().focusInEvent(event)


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
    PLAYLIST_HEADERS = ("№", "Сложность · Песня", "Исполнитель", "Рейтинг")
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
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
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
            self.owner.invalidate_plan()
        wanted = {str(path).casefold() for path in selected_paths}
        self.setRowCount(len(self.tracks))
        for row, track in enumerate(self.tracks):
            sign = next((symbol for key, symbol in self.DIFFICULTY_SIGNS.items()
                         if key in track.difficulty), "")
            alternatives = (sum(t.path.parent == track.path.parent and
                                song_key(t) == song_key(track) for t in self.owner.catalog_all)
                            if self.name == "current" else 0)
            marked_title = f"{sign}{track.title}" if sign else track.title
            if alternatives > 1:
                marked_title += f"  ⇄ {alternatives}"
            values = ((str(row + 1), marked_title, track.artist, display_rating(track.rating))
                      if self.name == "current" or self.name.startswith(("block:", "reserve:")) else
                      (str(row + 1), track.artist, track.title, track.difficulty,
                       track.language, track.energy, display_rating(track.rating), track.bpm))
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
        if isinstance(source, TrackTable):
            row = self.rowAt(int(event.position().y()))
            if row < 0:
                row = len(self.tracks)
            elif int(event.position().y()) > self.rowViewportPosition(row) + self.rowHeight(row) // 2:
                row += 1
            accepted = self.owner.insert_tracks_at(source, self.name, row)
            event.setDropAction(Qt.DropAction.CopyAction)
            if accepted:
                event.accept()
            else:
                event.ignore()
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
        self.active_block_key = None
        self._updating_block_selection = False
        self.replacement_history = {}
        self.undo_stack = []
        self.catalog_all = []
        self.presets = load_restaurant_presets()
        self.session_path = Path(__file__).with_name("data") / "last_session.json"
        try:
            self.session = json.loads(self.session_path.read_text(encoding="utf-8")) if self.session_path.exists() else {}
        except (OSError, ValueError):
            self.session = {}
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
        venue_controls = self.catalog_filters_layout
        venue_controls.addWidget(QLabel("Пресет ресторана:"))
        self.venue = QComboBox()
        self.venue.currentTextChanged.connect(self.apply_restaurant_preset)
        venue_controls.addWidget(self.venue)
        edit_venue = QPushButton("Настроить фильтры…")
        edit_venue.clicked.connect(self.edit_restaurant_preset)
        venue_controls.addWidget(edit_venue)
        self.ratio_hint = QLabel("")
        venue_controls.addWidget(self.ratio_hint)
        self.target_songs = QSpinBox()
        self.target_songs.setRange(1, 200)
        self.target_songs.setValue(24)
        venue_controls.addWidget(self.target_songs)
        pick_ratio = QPushButton("Добрать по доле языков")
        pick_ratio.clicked.connect(self.fill_language_ratio)
        venue_controls.addWidget(pick_ratio)
        self.reload_venue_names(self.session.get("venue"))
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
        history_controls = QHBoxLayout()
        outer.addLayout(history_controls)
        history_label = QLabel("Прошлое выступление · ограничение повторов 30%:")
        history_controls.addWidget(history_label)
        self.history_count_label = QLabel("Не загружено")
        history_controls.addWidget(self.history_count_label)
        load_history = QPushButton("Загрузить прошлый M3U8…")
        load_history.clicked.connect(self.load_previous_playlist)
        history_controls.addWidget(load_history)
        clear_history = QPushButton("Очистить историю")
        clear_history.clicked.connect(self.clear_previous_playlist)
        history_controls.addWidget(clear_history)
        history_controls.addStretch(1)
        self.summary = QLabel("Перетащи файлы или используй «Добавить MP3/M3U8»")
        self.summary.setWordWrap(True)
        outer.addWidget(self.summary)
        self.setCentralWidget(root)
        self.statusBar().showMessage("Готово · MP3 защищены от изменения и удаления")
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_current_playlist)
        QShortcut(QKeySequence.StandardKey.Undo, self, activated=self.undo_last_change)
        QShortcut(QKeySequence("Ctrl+O"), self, activated=lambda: self.pick_files("current"))
        self.refresh_summary()
        try:
            if load_config().get("library", {}).get("auto_load", True):
                self.reload_catalog()
        except (OSError, ValueError) as exc:
            self.statusBar().showMessage(f"Конфигурация: {exc}", 15000)

    def closeEvent(self, event):
        self.save_session()
        super().closeEvent(event)

    def save_session(self):
        state = {"venue": self.venue.currentText()}
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.session_path.with_suffix(".tmp")
        try:
            temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.session_path)
        except OSError as exc:
            self.statusBar().showMessage(str(exc), 10000)

    def restore_session_playlist(self):
        paths = self.session.get("playlist", [])
        if not isinstance(paths, list):
            return
        tracks = []
        for path in paths:
            try:
                if isinstance(path, str) and Path(path).is_file():
                    tracks.append(read_track(Path(path)))
            except (OSError, ValueError):
                continue
        if tracks:
            self.current.set_tracks(add_unique_songs([], tracks))

    def make_panel(self, splitter, title: str, name: str) -> TrackTable:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        heading = QLabel(title)
        heading.setStyleSheet("font-size:16px;font-weight:700;")
        layout.addWidget(heading)
        if name == "catalog":
            self.catalog_filters_layout = QHBoxLayout()
            layout.addLayout(self.catalog_filters_layout)
        table = TrackTable(name, self)
        table.filesDropped.connect(self.import_files)
        if name in ("current", "catalog"):
            table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            table.customContextMenuRequested.connect(lambda pos, t=table: self.open_track_menu(t, pos))
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
            self.hide_used = QCheckBox("Скрыть песни, уже добавленные справа")
            self.hide_used.setChecked(True)
            self.hide_used.toggled.connect(self.apply_restaurant_preset)
            layout.insertWidget(2, self.hide_used)
            button("↻ Обновить", self.reload_catalog)
            button("→ В плейлист", self.add_catalog_selection)
            button("Связать версии…", self.link_selected_versions)
        elif name == "current":
            button("Сохранить M3U8", self.save_current_playlist)
        splitter.addWidget(panel)
        return table

    def record_undo(self):
        snapshot = (list(self.current.tracks),
                    None if self.block_plan is None else
                    [(list(main), list(reserve)) for main, reserve in self.block_plan])
        self.undo_stack.append(snapshot)
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)

    def undo_last_change(self):
        if not self.undo_stack:
            self.statusBar().showMessage("Отменять нечего.", 4000)
            return
        tracks, plan = self.undo_stack.pop()
        self.block_plan = None if plan is None else [(list(a), list(b)) for a, b in plan]
        if self.block_plan is None:
            self.current.set_tracks(tracks)
            self.block_area.hide()
            self.current.show()
        else:
            self.current.tracks = list(tracks)
            self.render_block_editor()
        self.apply_restaurant_preset()
        self.refresh_summary()
        self.statusBar().showMessage("Последнее изменение плейлиста отменено.", 5000)

    def after_playlist_edit(self):
        self.apply_restaurant_preset()
        self.refresh_summary()

    def highlight_existing(self, track):
        key = song_key(track)
        if self.block_plan is not None:
            for name, table in self.block_tables.items():
                for row, existing in enumerate(table.tracks):
                    if song_key(existing) == key:
                        table.selectRow(row)
                        self.block_area.ensureWidgetVisible(table)
                        return
        else:
            for row, existing in enumerate(self.current.tracks):
                if song_key(existing) == key:
                    self.current.selectRow(row)
                    self.current.scrollToItem(self.current.item(row, 1))
                    return

    def insert_tracks_at(self, source, target_key, insertion):
        """Move existing block songs or insert catalogue songs exactly at drop position."""
        if source is None:
            return False
        moving = source.selected_tracks()
        if not moving:
            return False
        if target_key == "current" and self.block_plan is None:
            destination = self.current.tracks
        elif self.block_plan is not None and target_key.startswith(("block:", "reserve:")):
            destination = self.slot_tracks(target_key)
        else:
            return False
        src_key = source.name if source.name == "current" or source.name.startswith(("block:", "reserve:")) else None
        same = src_key == target_key
        all_songs = ([song for main, reserve in self.block_plan for song in main + reserve]
                     if self.block_plan is not None else self.current.tracks)
        moving_paths = {str(t.path).casefold() for t in moving} if src_key else set()
        occupied = {song_key(t) for t in all_songs if str(t.path).casefold() not in moving_paths}
        seen = set()
        duplicate = next((t for t in moving if song_key(t) in occupied or
                          (song_key(t) in seen)), None)
        # Check selected works for collisions too, not just file paths.
        for t in moving:
            seen.add(song_key(t))
        if duplicate is not None:
            self.highlight_existing(duplicate)
            QMessageBox.information(self, "Песня уже добавлена",
                                    "Это произведение уже есть в плейлисте. Оно выделено справа.")
            return False
        if len({song_key(t) for t in moving}) != len(moving):
            QMessageBox.information(self, "Дубли", "Выбери только одну версию каждого произведения.")
            return False
        insertion = max(0, min(int(insertion), len(destination)))
        if same:
            selected_indices = source.selected_rows()
            insertion -= sum(row < insertion for row in selected_indices)
        self.record_undo()
        if src_key is not None:
            source_items = self.slot_tracks(src_key) if self.block_plan is not None else self.current.tracks
            source_items[:] = [t for t in source_items if str(t.path).casefold() not in moving_paths]
        destination[insertion:insertion] = moving
        if self.block_plan is None:
            self.current.set_tracks(destination, [t.path for t in moving])
        else:
            self.current.tracks = [t for main, _ in self.block_plan for t in main]
            self.render_block_editor()
            table = self.block_tables[target_key]
            for row in range(insertion, insertion + len(moving)):
                table.selectRow(row)
            self.block_area.ensureWidgetVisible(table)
        self.after_playlist_edit()
        return True

    def build_track_menu(self, table):
        menu = QMenu(table)
        has_selection = bool(table.selected_rows())
        if table is self.catalog:
            add = menu.addAction("Добавить в плейлист")
            add.setEnabled(has_selection)
            add.triggered.connect(self.add_catalog_selection)
        else:
            remove = menu.addAction("Убрать из плейлиста")
            remove.setEnabled(has_selection)
            remove.triggered.connect(lambda: self.remove_selected(table))
            change = menu.addAction("Заменить случайной песней")
            change.setEnabled(has_selection)
            change.triggered.connect(self.quick_replace)
            versions = menu.addAction("Выбрать версию S/F…")
            versions.setEnabled(has_selection)
            versions.triggered.connect(self.choose_technical_version)
            menu.addSeparator()
            add = menu.addAction("Добавить MP3/M3U8 из файла…")
            add.triggered.connect(lambda: self.pick_files(table.name))
        menu.addSeparator()
        undo = menu.addAction("Отменить изменение  Ctrl+Z")
        undo.setEnabled(bool(self.undo_stack))
        undo.triggered.connect(self.undo_last_change)
        return menu

    def open_track_menu(self, table, point):
        row = table.rowAt(point.y())
        if row >= 0 and row not in table.selected_rows():
            table.selectRow(row)
        self.build_track_menu(table).exec(table.viewport().mapToGlobal(point))

    def load_previous_playlist(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбери плейлист предыдущего выступления",
            str(Path.home()), "Плейлисты (*.m3u8 *.m3u)")
        if not path:
            return
        self.history.set_tracks([])
        self.history.parentWidget().show()
        self.import_files("history", [Path(path)])

    def clear_previous_playlist(self):
        self.history.set_tracks([])
        self.history.parentWidget().hide()

    def refresh_summary(self):
        # This runs while the second table is being created too.
        if not all(hasattr(self, name) for name in ("catalog", "current", "history", "summary")):
            return
        count, percentage = repeated_from_history(self.current.tracks, self.history.tracks)
        message = (f"Каталог: {len(self.catalog.tracks)} файлов · "
                   f"Текущий: {len(self.current.tracks)} файлов · "
                   f"История: {len(self.history.tracks)} файлов · "
                   f"Повторы песен с прошлого выступления: {count} ({percentage:.0f}%)")
        if self.current.tracks and self.history.tracks and percentage > 20:
            message += "  ⚠ Выше ориентира 10–20%."
        self.summary.setText(message)
        if hasattr(self, "history_count_label"):
            self.history_count_label.setText(f"{len(self.history.tracks)} песен" if self.history.tracks else "Не загружено")

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
        if hasattr(self, "hide_used") and self.hide_used.isChecked():
            occupied = ({song_key(t) for main, reserve in self.block_plan for t in main + reserve}
                        if self.block_plan is not None
                        else {song_key(t) for t in self.current.tracks})
            matches = [t for t in matches if song_key(t) not in occupied]
        self.catalog.set_tracks(matches)
        if hasattr(self, "ratio_hint"):
            target = int(preset.get("english_target_percent", load_config().get("selection", {}).get("language_english_percent", 50)))
            tolerance = int(preset.get("language_tolerance_percent", 10))
            self.ratio_hint.setText(f"Цель: {target}% ±{tolerance}% англ.")

    def fill_language_ratio(self):
        preset = self.presets.get(self.venue.currentText(), {})
        percentage = int(preset.get("english_target_percent", load_config().get("selection", {}).get("language_english_percent", 50)))
        try:
            selected = build_language_balanced_list(
                self.current.tracks, self.catalog.tracks,
                self.target_songs.value(), percentage,
                int(preset.get("language_tolerance_percent", load_config().get("selection", {}).get("language_tolerance_percent", 10))),
                bool(load_config().get("selection", {}).get("prefer_alternation", True)))
        except ValueError as exc:
            QMessageBox.warning(self, "Подбор по языкам", str(exc))
            return
        self.current.set_tracks(selected)
        self.invalidate_plan()
        self.statusBar().showMessage("Добавлены песни по сохранённой доле языков. "
                                     "Ранее выбранные песни сохранены.", 10000)

    def edit_restaurant_preset(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Фильтры каталога · шаблон ресторана")
        dialog.resize(680, 680)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        layout.addLayout(form)
        current = self.venue.currentText()
        existing = self.presets.get(current, {})
        name = QLineEdit("" if current == "Все песни" else current)
        form.addRow("Название шаблона:", name)
        active_field = [None]
        included = FocusTagEdit(lambda widget: active_field.__setitem__(0, widget))
        included.setMaximumHeight(62)
        included.setPlainText("\n".join(existing.get("include_tags", [])))
        excluded = FocusTagEdit(lambda widget: active_field.__setitem__(0, widget))
        excluded.setMaximumHeight(62)
        excluded.setPlainText("\n".join(existing.get("exclude_tags", [])))
        form.addRow("Включать по тегам (любой из):", included)
        form.addRow("Исключать по тегам:", excluded)
        included.cursorPositionChanged.connect(lambda: active_field.__setitem__(0, included))
        excluded.cursorPositionChanged.connect(lambda: active_field.__setitem__(0, excluded))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        pane = QWidget()
        pane_layout = QVBoxLayout(pane)
        groups = {}
        try:
            config_path = Path(__file__).resolve().parents[1] / "config.json"
            schema = json.loads(config_path.read_text(encoding="utf-8-sig"))
            for field in schema.get("fields", []):
                choices = [str(option[0]) for option in field.get("options", [])
                           if isinstance(option, list) and option and option[0]]
                choices = [tag for tag in choices if not tag.startswith("в-")]
                if choices:
                    groups[field.get("label", field.get("id", "Теги"))] = list(dict.fromkeys(choices))
        except (OSError, ValueError, TypeError):
            pass
        known = {tag for choices in groups.values() for tag in choices}
        extras = {tag for track in self.catalog_all
                  for tag in (*track.tags, track.language, track.difficulty,
                              track.energy, track.role, track.status)
                  if tag and not tag.startswith("в-") and tag not in known}
        if extras:
            groups["Другие теги"] = sorted(extras, key=str.casefold)
        for title, choices in groups.items():
            pane_layout.addWidget(QLabel(title))
            grid = QGridLayout()
            for i, tag in enumerate(choices):
                chip = QPushButton(tag)
                chip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                chip.clicked.connect(lambda checked=False, code=tag:
                    (active_field[0] or included).appendPlainText(code))
                grid.addWidget(chip, i // 4, i % 4)
            pane_layout.addLayout(grid)
        scroll.setWidget(pane)
        layout.addWidget(scroll, 1)
        ratio = QSpinBox()
        ratio.setRange(0, 100)
        ratio.setSuffix("% английских · ориентир")
        ratio.setValue(int(existing.get("english_target_percent", load_config().get("selection", {}).get("language_english_percent", 50))))
        form.addRow("Доля английских:", ratio)
        tolerance = QSpinBox()
        tolerance.setRange(0, 50)
        tolerance.setSuffix("% допуска")
        tolerance.setValue(int(existing.get("language_tolerance_percent", 10)))
        form.addRow("Допуск доли языка:", tolerance)
        layout.addWidget(QLabel("Доля языка — ориентир; вручную выбранные песни не удаляются."))
        save = QPushButton("Сохранить шаблон и применить")
        layout.addWidget(save)
        def commit():
            title = name.text().strip()
            if not title or title == "Все песни":
                QMessageBox.warning(dialog, "Шаблон", "Укажи название ресторана.")
                return
            def lines(widget):
                return list(dict.fromkeys(x.strip() for x in widget.toPlainText().splitlines() if x.strip()))
            preset = {"include_tags": lines(included), "exclude_tags": lines(excluded),
                      "english_target_percent": ratio.value(),
                      "language_tolerance_percent": tolerance.value()}
            for field in ("language", "difficulty", "energy"):
                if field + "_allow" in existing:
                    preset[field + "_allow"] = existing[field + "_allow"]
            self.presets[title] = preset
            try:
                save_restaurant_presets(self.presets)
            except OSError as exc:
                QMessageBox.warning(dialog, "Ошибка сохранения", str(exc))
                return
            dialog.accept()
            QTimer.singleShot(0, lambda chosen=title: self.reload_venue_names(chosen))
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
        if not self.catalog.selected_tracks():
            return
        if self.block_plan is not None:
            key = self.active_block_key if self.active_block_key in self.block_tables else "block:0"
            self.insert_tracks_at(self.catalog, key, len(self.slot_tracks(key)))
        else:
            self.insert_tracks_at(self.catalog, "current", len(self.current.tracks))

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
            if any(song_key(track) not in used for track in tracks):
                self.record_undo()
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
            if self.block_plan is None and self.current.tracks:
                self.current.set_tracks(self.current.tracks)
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

    def activate_block_selection(self, key: str):
        if self._updating_block_selection or key not in self.block_tables:
            return
        if not self.block_tables[key].selected_rows():
            return
        self.active_block_key = key
        self._updating_block_selection = True
        try:
            for other_key, table in self.block_tables.items():
                if other_key != key:
                    table.clearSelection()
        finally:
            self._updating_block_selection = False

    def selected_playlist_slot(self):
        if self.block_plan is not None:
            key = self.active_block_key
            if key in self.block_tables:
                rows = self.block_tables[key].selected_rows()
                if len(rows) == 1:
                    return key, rows[0]
            choices = [(key, i) for key, table in self.block_tables.items()
                       for i in table.selected_rows()]
            return choices[0] if len(choices) == 1 else None
        rows = self.current.selected_rows()
        return ("current", rows[0]) if len(rows) == 1 else None

    def remove_selected(self, table: TrackTable):
        if self.block_plan is not None and (table is self.current or table.name.startswith(("block:", "reserve:"))):
            slot = self.selected_playlist_slot()
            if slot is None:
                self.statusBar().showMessage("Выдели песню в видимом блоке.", 6000)
                return
            key, _ = slot
            rows = self.block_tables[key].selected_rows()
            tracks = self.slot_tracks(key)
            self.record_undo()
            tracks[:] = [track for i, track in enumerate(tracks) if i not in rows]
            self.current.tracks = [song for main, _ in self.block_plan for song in main]
            self.render_block_editor()
            self.after_playlist_edit()
            self.statusBar().showMessage(f"Убрано {len(rows)} из блока. MP3 не затронуты.", 7000)
            return
        indexes = set(table.selected_rows())
        if not indexes or table.name == "catalog":
            return
        self.record_undo()
        table.set_tracks([track for index, track in enumerate(table.tracks) if index not in indexes])
        self.after_playlist_edit()
        self.statusBar().showMessage(
            f"Убрано из списка: {len(indexes)}. MP3 на диске не затронуты.", 7000)

    def shift_selected(self, table: TrackTable, direction: int):
        if self.block_plan is not None:
            slot = self.selected_playlist_slot()
            if slot is None:
                self.statusBar().showMessage("Выдели песню в видимом блоке.", 6000)
                return
            key, row = slot
            tracks = self.slot_tracks(key)
            new_row = max(0, min(len(tracks) - 1, row + direction))
            if new_row == row:
                return
            self.record_undo()
            tracks[row], tracks[new_row] = tracks[new_row], tracks[row]
            self.current.tracks = [song for main, _ in self.block_plan for song in main]
            self.render_block_editor()
            self.block_tables[key].selectRow(new_row)
            return
        rows = table.selected_rows()
        if not rows:
            return
        destination = rows[0] + direction if direction < 0 else rows[-1] + direction + 1
        selected_paths = [track.path for track in table.selected_tracks()]
        self.record_undo()
        table.set_tracks(move_rows(table.tracks, rows, destination), selected_paths)

    def slot_tracks(self, key):
        if key == "current":
            return self.current.tracks
        kind, idx = key.split(":")
        return self.block_plan[int(idx)][0 if kind == "block" else 1]

    def replace_slot(self, key, index, track):
        self.record_undo()
        if key == "current":
            tracks = list(self.current.tracks)
            tracks[index] = track
            self.current.set_tracks(tracks, [track.path])
        else:
            self.slot_tracks(key)[index] = track
            self.current.tracks = [t for main, _ in self.block_plan for t in main]
            self.render_block_editor()
            self.block_tables[key].selectRow(index)
        self.after_playlist_edit()

    def quick_replace(self):
        slot = self.selected_playlist_slot()
        if slot is None:
            QMessageBox.information(self, "Замена", "Выдели одну песню в видимом блоке.")
            return
        key, row = slot
        songs = self.slot_tracks(key)
        selected = songs[row]
        occupied = ([track for main, reserve in self.block_plan for track in main + reserve]
                    if self.block_plan is not None else self.current.tracks)
        used = {song_key(t) for t in occupied}
        candidates = random_replacement_candidates(songs, row, self.catalog.tracks, used)
        if not candidates:
            QMessageBox.information(self, "Замена",
                                    "В отфильтрованном каталоге нет новых композиций.")
            return

        replacement = None
        if key.startswith("block:"):
            current_minutes, missing = block_duration(songs)
            selected_minutes = track_minutes(selected)
            limit = self.block_minutes.value()
            if selected_minutes is None or missing:
                self.statusBar().showMessage("Неизвестная длительность — подбираю замену без проверки лимита.", 6000)
                replacement = candidates[0]
            else:
                for candidate in candidates:
                    minutes = track_minutes(candidate)
                    if minutes is not None and current_minutes - selected_minutes + minutes <= limit + 0.001:
                        replacement = candidate
                        break
        else:
            replacement = candidates[0]
        if replacement is None:
            QMessageBox.information(self, "Замена",
                                    "Свободные песни есть, но ни одна не помещается в лимит длительности блока.")
            return
        self.replace_slot(key, row, replacement)
        self.statusBar().showMessage(
            f"Случайная замена: {selected.title} → {replacement.title}. MP3 не изменены.", 9000)

    def choose_technical_version(self):
        slot = self.selected_playlist_slot()
        if slot is None:
            QMessageBox.information(self, "Версии", "Выдели одну песню в видимом блоке.")
            return
        key, row = slot
        selected = self.slot_tracks(key)[row]
        # Only arrangements of the exact same song folder: no cross-artist covers.
        variants = [t for t in self.catalog_all
                    if t.path.parent == selected.path.parent
                    and song_key(t) == song_key(selected)]
        if all(t.path != selected.path for t in variants):
            variants.append(selected)
        variants = sorted(variants, key=lambda t: (
            {"S": 0, "F": 1}.get(version_length(t), 2), t.path.name.casefold()))
        if len(variants) < 2:
            QMessageBox.information(self, "Версии", "Других версий этой песни в папке не найдено.")
            return
        options = [f"{version_length(t) or '—'} · {t.path.name}" for t in variants]
        current_idx = next(i for i, t in enumerate(variants) if t.path == selected.path)
        chosen, ok = QInputDialog.getItem(
            self, "Версии одной песни", "Выбери минусовку:", options, current_idx, False)
        if not ok:
            return
        replacement = variants[options.index(chosen)]
        if replacement.path == selected.path:
            return
        self.replace_slot(key, row, replacement)
        self.statusBar().showMessage("Версия заменена без изменения MP3.", 8000)

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
        if hasattr(self, "block_area"):
            self.block_area.hide()
            self.current.show()

    def generate_blocks(self):
        if self.block_plan is not None:
            response = QMessageBox.question(self, "Пересоздать блоки?",
                "Блоки уже редактировались. Пересоздание изменит их распределение и резервы. Продолжить?")
            if response != QMessageBox.StandardButton.Yes:
                return
        count = self.block_count.value()
        target = self.block_minutes.value()
        manual = bool(self.current.tracks)
        source = self.current.tracks if manual else self.catalog.tracks
        if len(source) < count:
            QMessageBox.warning(self, "Недостаточно песен",
                "После фильтрации недостаточно песен для выбранного числа блоков.")
            return
        if not manual:
            preset = self.presets.get(self.venue.currentText(), {})
            desired = min(len(source), count * max(1, target // 3))
            previous = {song_key(t) for t in self.history.tracks}
            cap = int(load_config().get("selection", {}).get("max_history_repeat_percent", 30))
            fresh = [t for t in source if song_key(t) not in previous]
            old = [t for t in source if song_key(t) in previous]
            candidates = fresh + old[:max(0, desired * cap // 100)]
            source = build_language_balanced_list(
                [], candidates, desired,
                int(preset.get("english_target_percent", 50)),
                int(preset.get("language_tolerance_percent", 10)))
        groups = distribute_blocks(source, count, target)
        if any(not main for main, _ in groups):
            QMessageBox.warning(self, "Недостаточно песен",
                "Не удалось заполнить все блоки. Уменьши длительность или число блоков.")
            return
        scheduled = [t for main, _ in groups for t in main]
        repeat_limit = int(load_config().get("selection", {}).get("max_history_repeat_percent", 30))
        repeats, repeat_pct = repeated_from_history(scheduled, self.history.tracks)
        if self.history.tracks and repeat_pct > repeat_limit:
            QMessageBox.warning(self, "Повторы прошлого выступления",
                f"Повторов {repeats} ({repeat_pct:.0f}%), максимум {repeat_limit}%. "
                "Смягчи фильтры или замени песни.")
            return
        # Repair medium streaks before allocating easy songs to reserves.
        main_keys = {song_key(t) for main, _ in groups for t in main}
        easy_pool = [t for t in self.catalog.tracks
                     if difficulty_level(t) == 1 and song_key(t) not in main_keys]
        from core import track_minutes
        for main, _ in groups:
            index = 2
            while index < len(main):
                if all(difficulty_level(t) == 2 for t in main[index - 2:index + 1]):
                    old = main[index]
                    current_duration = sum(track_minutes(t) or 0 for t in main)
                    suitable = next((t for t in easy_pool
                                     if current_duration - (track_minutes(old) or 0)
                                     + (track_minutes(t) or target + 1) <= target), None)
                    if suitable is not None:
                        main[index] = suitable
                        main_keys.add(song_key(suitable))
                        easy_pool = [t for t in easy_pool if song_key(t) != song_key(suitable)]
                index += 1
        used = {song_key(t) for main, _ in groups for t in main}
        available = [
            t for t in self.catalog.tracks
            if song_key(t) not in used
            and t.status.startswith(("г-1-", "г-2-", "г-3-"))
            and t.difficulty.startswith(("сл-1", "сл-2"))
        ]
        result = []
        for main, _ in groups:
            preferred = "сл-2" if any("сл-3" in t.difficulty or "сл-4" in t.difficulty for t in main) else "сл-1"
            available.sort(key=lambda t: (not t.difficulty.startswith(preferred), t.title.casefold()))
            chosen = available[:self.reserve_count.value()]
            del available[:len(chosen)]
            used.update(song_key(t) for t in chosen)
            available = [t for t in available if song_key(t) not in used]
            result.append((main, chosen))
        # Preserve generated selections for next startup even in catalog mode.
        self.current.set_tracks([song for main, _ in result for song in main])
        self.block_plan = result
        self.render_block_editor()
        self.after_playlist_edit()
        counts = ", ".join(f"{len(main)}+{len(reserve)}" for main, reserve in result)
        self.statusBar().showMessage(f"Блоки (основные+резерв): {counts}", 15000)
        self.statusBar().showMessage("Блоки готовы: " + counts, 12000)

    def render_block_editor(self):
        if self.block_plan is None:
            return
        container = QWidget()
        layout = QVBoxLayout(container)
        self.block_tables = {}
        self.active_block_key = None
        for idx, (main, reserve) in enumerate(self.block_plan):
            for kind, songs in (("block", main), ("reserve", reserve)):
                key = f"{kind}:{idx}"
                minutes, missing = block_duration(songs)
                heading = QLabel(f"{idx + 1} {'блок' if kind == 'block' else 'запас'}"
                                 f" · {int(minutes)}:{int(round(minutes % 1 * 60)):02d}"
                                 + (f" · {missing} без длительности" if missing else ""))
                ratings = [float(display_rating(t.rating).replace(",", "."))
                           for t in songs if display_rating(t.rating) != "—"]
                if ratings and kind == "block":
                    heading.setText(heading.text() + " · ср. рейтинг " + f"{sum(ratings)/len(ratings):.1f}".replace(".", ","))
                heading.setStyleSheet("font-weight:700;font-size:14px;padding-top:9px;")
                layout.addWidget(heading)
                if kind == "block":
                    alerts = vocal_warnings(songs)
                    if alerts:
                        warning = QLabel("⚠ " + " · ".join(alerts[:3]))
                        warning.setWordWrap(True)
                        warning.setStyleSheet("color:#f0bb6b;")
                        layout.addWidget(warning)
                table = TrackTable(key, self)
                table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                table.set_tracks(songs)
                rows_height = sum(table.rowHeight(row) for row in range(table.rowCount()))
                table.setFixedHeight(table.horizontalHeader().height() + rows_height + 2 * table.frameWidth() + 2)
                self.block_tables[key] = table
                table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                table.customContextMenuRequested.connect(lambda pos, t=table: self.open_track_menu(t, pos))
                table.itemSelectionChanged.connect(lambda selected_key=key: self.activate_block_selection(selected_key))
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
        QTimer.singleShot(0, self.render_block_editor)
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        self.statusBar().showMessage("Перенесено в блок; длительность пересчитана.", 5000)

    def save_current_playlist(self):
        if self.block_plan is not None:
            self.export_blocks()
        else:
            self.export_list(self.current)

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
