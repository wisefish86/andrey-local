from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QSignalBlocker, Signal
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QUrl

PENIE_ROOT = Path(__file__).resolve().parents[2]
if str(PENIE_ROOT) not in sys.path:
    sys.path.insert(0, str(PENIE_ROOT))

from _common.id3_io import clean, load_tags, read_field, read_text, read_url, write_field

APP_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = APP_ROOT / "config.json"
INVALID_WIN_CHARS = re.compile(r'[<>:"/\\|?*]')


class MultiSelectButton(QToolButton):
    changed = Signal()

    def __init__(self, options: list[list[str]], placeholder_value: str = "", parent=None):
        super().__init__(parent)
        self.setPopupMode(QToolButton.InstantPopup)
        self.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._placeholder = placeholder_value
        self._actions: dict[str, QAction] = {}
        self._labels: dict[str, str] = {}
        menu = self.menu() or None
        if menu is None:
            from PySide6.QtWidgets import QMenu
            menu = QMenu(self)
            self.setMenu(menu)
        for value, label in options:
            self._add_option(value, label)
        self._refresh_text()

    def _add_option(self, value: str, label: str, unknown: bool = False):
        if value in self._actions:
            return
        action = QAction(("⚠ " if unknown else "") + label, self)
        action.setCheckable(True)
        action.toggled.connect(lambda checked, v=value: self._on_toggled(v, checked))
        self.menu().addAction(action)
        self._actions[value] = action
        self._labels[value] = label

    def _on_toggled(self, value: str, checked: bool):
        if checked and self._placeholder and value == self._placeholder:
            for v, action in self._actions.items():
                if v != value and action.isChecked():
                    with QSignalBlocker(action):
                        action.setChecked(False)
        elif checked and self._placeholder and value != self._placeholder:
            action = self._actions.get(self._placeholder)
            if action and action.isChecked():
                with QSignalBlocker(action):
                    action.setChecked(False)
        self._refresh_text()
        self.changed.emit()

    def _refresh_text(self):
        values = self.values()
        if not values:
            self.setText("—")
        else:
            self.setText(", ".join(self._labels.get(v, v) for v in values))

    def set_values(self, values: list[str]):
        values = list(dict.fromkeys(values))
        for value in values:
            if value not in self._actions:
                self._add_option(value, value, unknown=True)
        for value, action in self._actions.items():
            with QSignalBlocker(action):
                action.setChecked(value in values)
        self._refresh_text()

    def values(self) -> list[str]:
        return [value for value, action in self._actions.items() if action.isChecked()]


class DropFrame(QFrame):
    fileDropped = Signal(str)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("dropFrame")
        layout = QVBoxLayout(self)
        self.label = QLabel("Перетащи сюда MP3-минусовку")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setObjectName("dropTitle")
        hint = QLabel("или нажми «Выбрать MP3»")
        hint.setAlignment(Qt.AlignCenter)
        hint.setObjectName("muted")
        layout.addWidget(self.label)
        layout.addWidget(hint)

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].toLocalFile().lower().endswith(".mp3"):
            event.acceptProposedAction()

    def dropEvent(self, event):
        path = event.mimeData().urls()[0].toLocalFile()
        self.fileDropped.emit(path)
        event.acceptProposedAction()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        self.current_path: Path | None = None
        self.filename_manual = False
        self.folder_manual = False
        self.title_manual = False
        self.controls: dict[str, QWidget] = {}
        self.field_defs: dict[str, dict[str, Any]] = {f["id"]: f for f in self.config["fields"]}
        self.tit1_unknown: list[str] = []
        self._build_ui()
        self._apply_style()
        self.setWindowTitle("Добавление минуса в репертуар")
        self.resize(1100, 760)

    def _build_ui(self):
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        top = QHBoxLayout()
        self.drop = DropFrame()
        self.drop.setMaximumHeight(78)
        self.drop.fileDropped.connect(self.load_file)
        top.addWidget(self.drop, 1)
        choose = QPushButton("Выбрать MP3")
        choose.clicked.connect(self.choose_file)
        choose.setMinimumWidth(150)
        top.addWidget(choose)
        outer.addLayout(top)

        self.path_label = QLabel("Файл не выбран")
        self.path_label.setObjectName("muted")
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        outer.addWidget(self.path_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setSpacing(12)

        meta = QGroupBox("Песня и название")
        grid = QGridLayout(meta)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(7)

        self.artist = QLineEdit()
        self.clean_title = QLineEdit()
        self.version = QComboBox()
        self.version.setEditable(True)
        for value, label in self.config["filename"].get("version_options", []):
            self.version.addItem(label, value)
        self.version.setInsertPolicy(QComboBox.NoInsert)
        self.display_title = QLineEdit()
        self.filename = QLineEdit()
        self.folder_name = QLineEdit()

        grid.addWidget(QLabel("Исполнитель"), 0, 0)
        grid.addWidget(self.artist, 0, 1, 1, 2)
        grid.addWidget(QLabel("Версия"), 0, 3)
        grid.addWidget(self.version, 0, 4, 1, 2)

        grid.addWidget(QLabel("Название"), 1, 0)
        grid.addWidget(self.clean_title, 1, 1, 1, 5)

        grid.addWidget(QLabel("Название (Title)"), 2, 0)
        grid.addWidget(self.display_title, 2, 1, 1, 4)
        reset_title = QPushButton("По шаблону")
        reset_title.clicked.connect(self.reset_title_template)
        grid.addWidget(reset_title, 2, 5)

        grid.addWidget(QLabel("Новое имя MP3"), 3, 0)
        grid.addWidget(self.filename, 3, 1, 1, 4)
        reset_name = QPushButton("По шаблону")
        reset_name.clicked.connect(self.reset_filename_template)
        grid.addWidget(reset_name, 3, 5)

        grid.addWidget(QLabel("Имя папки"), 4, 0)
        grid.addWidget(self.folder_name, 4, 1, 1, 4)
        reset_folder = QPushButton("По шаблону")
        reset_folder.clicked.connect(self.reset_folder_template)
        grid.addWidget(reset_folder, 4, 5)
        body_layout.addWidget(meta)

        data_box = QGroupBox("Данные минуса")
        data_grid = QGridLayout(data_box)
        data_grid.setHorizontalSpacing(10)
        data_grid.setVerticalSpacing(7)

        self.tone = QComboBox()
        for tone in self.config["filename"].get("tone_options", ["N", "-3", "-2", "-1", "0", "+1", "+2", "+3"]):
            label = "N — неизвестно" if tone == "N" else tone
            self.tone.addItem(label, tone)
        self.year = QLineEdit()
        self.year.setMaximumWidth(110)
        self.source_url = QLineEdit()
        self.source_url.setPlaceholderText("Прямой URL на плюс для сайта")
        self.source_url.setToolTip("Ссылка на плюс (оригинал/вокальная версия), хранится в WOAS.")
        self.version_info = QLineEdit()
        self.version_info.setPlaceholderText("мз, ориг, buy, +click…")

        data_grid.addWidget(QLabel("Тональность"), 0, 0)
        data_grid.addWidget(self.tone, 0, 1)
        data_grid.addWidget(QLabel("Год"), 0, 2)
        data_grid.addWidget(self.year, 0, 3)
        data_grid.addWidget(QLabel("Ссылка на плюс"), 1, 0)
        data_grid.addWidget(self.source_url, 1, 1, 1, 3)
        data_grid.addWidget(QLabel("Примечание"), 2, 0)
        data_grid.addWidget(self.version_info, 2, 1, 1, 2)
        help_btn = QToolButton()
        help_btn.setText("ⓘ")
        help_btn.setToolTip("Обозначения: мз, buy, +click, +Б и другие")
        help_btn.clicked.connect(self.show_help)
        data_grid.addWidget(help_btn, 2, 3)
        body_layout.addWidget(data_box)

        sections = QHBoxLayout()
        perf = QGroupBox("Выступление")
        perf_form = QFormLayout(perf)
        search = QGroupBox("Поиск и сайт")
        search_form = QFormLayout(search)
        extra = QGroupBox("Дополнительно")
        extra_grid = QGridLayout(extra)
        extra_index = 0

        for field in self.config["fields"]:
            control = self._make_field_control(field)
            self.controls[field["id"]] = control
            section = field["section"]
            if section == "performance":
                perf_form.addRow(field["label"], control)
            elif section == "search":
                search_form.addRow(field["label"], control)
            elif section == "extra":
                row = extra_index // 2
                col = (extra_index % 2) * 2
                extra_grid.addWidget(QLabel(field["label"]), row, col)
                extra_grid.addWidget(control, row, col + 1)
                extra_index += 1

        sections.addWidget(perf, 1)
        sections.addWidget(search, 1)
        body_layout.addLayout(sections)
        body_layout.addWidget(extra)

        file_tools = QGroupBox("Файлы песни")
        file_tools_layout = QHBoxLayout(file_tools)
        self.additions_btn = QPushButton("📁 Additi0ns")
        self.additions_btn.setToolTip("Создать/открыть подпапку Additi0ns для дополнительных версий минуса")
        self.additions_btn.clicked.connect(self.create_additions_folder)
        file_tools_layout.addWidget(self.additions_btn)
        self.files_copy_btn = QPushButton("✂ Копия в Files")
        self.files_copy_btn.setToolTip("Создать подпапку Files и скопировать туда текущий MP3, убрав из имени символ ֎")
        self.files_copy_btn.clicked.connect(self.copy_to_files_folder)
        file_tools_layout.addWidget(self.files_copy_btn)
        file_tools_layout.addStretch(1)
        self.additions_btn.setEnabled(False)
        self.files_copy_btn.setEnabled(False)
        body_layout.addWidget(file_tools)

        actions = QGroupBox("Папка и перенос")
        actions_layout = QVBoxLayout(actions)
        self.rename_folder = QCheckBox("Переименовать папку песни по шаблону")
        self.move_folder = QCheckBox("После сохранения перенести папку из «Добавляю в репертуар» в основной репертуар")
        self.target_label = QLabel("")
        self.target_label.setObjectName("muted")
        actions_layout.addWidget(self.rename_folder)
        actions_layout.addWidget(self.move_folder)
        actions_layout.addWidget(self.target_label)
        body_layout.addWidget(actions)

        self.warning_label = QLabel("")
        self.warning_label.setWordWrap(True)
        self.warning_label.setObjectName("warning")
        body_layout.addWidget(self.warning_label)

        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        bottom = QHBoxLayout()
        self.status = QLabel("Готов к загрузке MP3")
        self.status.setObjectName("muted")
        bottom.addWidget(self.status, 1)
        self.open_folder_btn = QPushButton("Открыть папку")
        self.open_folder_btn.clicked.connect(self.open_current_folder)
        self.open_folder_btn.setEnabled(False)
        bottom.addWidget(self.open_folder_btn)
        clear = QPushButton("Следующий")
        clear.clicked.connect(self.clear_form)
        bottom.addWidget(clear)
        self.save_btn = QPushButton("Сохранить теги и файл")
        self.save_btn.setObjectName("primary")
        self.save_btn.clicked.connect(self.save_all)
        self.save_btn.setEnabled(False)
        bottom.addWidget(self.save_btn)
        outer.addLayout(bottom)

        self.setCentralWidget(central)

        for widget in (self.artist, self.clean_title, self.version_info):
            widget.textChanged.connect(self._auto_names_changed)
        self.version.currentTextChanged.connect(self._auto_names_changed)
        self.tone.currentIndexChanged.connect(self._auto_names_changed)
        self.display_title.textEdited.connect(lambda _t: setattr(self, "title_manual", True))
        self.filename.textEdited.connect(lambda _t: setattr(self, "filename_manual", True))
        self.folder_name.textEdited.connect(lambda _t: setattr(self, "folder_manual", True))
        self.year.editingFinished.connect(self._suggest_era)
        self.move_folder.toggled.connect(self._update_target_preview)
        self.rename_folder.toggled.connect(self._update_target_preview)
        language_control = self.controls.get("language")
        if isinstance(language_control, MultiSelectButton):
            language_control.changed.connect(self._language_changed)
        self._reset_controls_to_defaults()
        self._set_tone(self.config["filename"].get("tone_default", "N"))

    def _make_field_control(self, field: dict[str, Any]):
        if field["control"] == "single_select":
            combo = QComboBox()
            combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            for value, label in field.get("options", []):
                combo.addItem(label, value)
            return combo
        if field["control"] == "multi_select":
            return MultiSelectButton(field.get("options", []), field.get("placeholder_value", ""))
        raise ValueError(f"Unsupported control: {field['control']}")

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #15181d; color: #e9edf2; font-size: 13px; }
            QGroupBox { border: 1px solid #353b44; border-radius: 8px; margin-top: 10px; padding: 12px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QLineEdit, QComboBox, QToolButton { background: #20252c; border: 1px solid #3d4652; border-radius: 6px; padding: 7px; min-height: 20px; }
            QPushButton { background: #272d35; border: 1px solid #414a56; border-radius: 6px; padding: 8px 12px; }
            QPushButton:hover, QToolButton:hover { background: #313945; }
            QPushButton#primary { background: #276749; border-color: #3c8a68; font-weight: 700; padding: 10px 18px; }
            QPushButton#primary:hover { background: #32805c; }
            QFrame#dropFrame { border: 2px dashed #536170; border-radius: 10px; padding: 14px; background: #1b2026; }
            QLabel#dropTitle { font-size: 17px; font-weight: 700; }
            QLabel#muted { color: #9ba6b2; }
            QLabel#warning { color: #f0b45d; }
            QScrollArea { border: none; }
        """)

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выбери MP3-минусовку", "", "MP3 (*.mp3)")
        if path:
            self.load_file(path)

    def load_file(self, path_str: str):
        path = Path(path_str)
        if not path.is_file() or path.suffix.lower() != ".mp3":
            QMessageBox.warning(self, "Не MP3", "Нужен существующий MP3-файл.")
            return
        try:
            tags = load_tags(path)
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка чтения", str(exc))
            return

        self.current_path = path
        self.path_label.setText(str(path))
        self.drop.label.setText(path.name)
        self.artist.setText(self._first(read_text(tags, "TPE1")))
        self.clean_title.setText(self._first(read_text(tags, "MVNM")))
        existing_title = self._first(read_text(tags, "TIT2"))
        self.year.setText(self._first(read_text(tags, "TDRC")))
        self.source_url.setText(read_url(tags, "WOAS"))

        inferred = self._parse_filename(path)
        if not self.artist.text().strip():
            self.artist.setText(inferred["artist"])
        if not self.clean_title.text().strip():
            self.clean_title.setText(inferred["clean_title"])
        self._set_version(inferred["version"])
        self._set_tone(inferred["tone"] or self.config["filename"].get("tone_default", "N"))
        self.version_info.setText(inferred["version_info"])

        tit1_values = read_text(tags, "TIT1")
        managed_prefixes = []
        for field in self.config["fields"]:
            control = self.controls[field["id"]]
            storage = field["storage"]
            if storage["kind"] == "tit1_group":
                prefix = storage["prefix"]
                managed_prefixes.append((prefix, bool(storage.get("prefix_casefold"))))
                values = [v for v in tit1_values if self._matches_prefix(v, prefix, storage)]
                self._set_control_values(field, control, values)
            else:
                spec = dict(storage)
                value = read_field(tags, spec)
                values = value if isinstance(value, list) else ([value] if value else [])
                self._set_control_values(field, control, values)

        self.tit1_unknown = [
            v for v in tit1_values
            if not any(self._matches_prefix(v, prefix, {"prefix_casefold": cf}) for prefix, cf in managed_prefixes)
        ]
        self._show_unknown_warning()

        self.title_manual = False
        generated_title = self.generated_title()
        if existing_title:
            self.display_title.setText(existing_title)
            self.title_manual = existing_title != generated_title
        else:
            self.display_title.setText(generated_title)

        self.filename_manual = False
        self.folder_manual = False
        self.reset_filename_template()
        self.reset_folder_template()
        self.rename_folder.setChecked(bool(self.config["folder"].get("rename_default", True)))

        staging = Path(self.config["paths"]["staging_root"])
        in_staging = self._is_under(path.parent, staging) and path.parent != staging
        self.move_folder.setEnabled(in_staging)
        self.move_folder.setChecked(in_staging and bool(self.config["folder"].get("move_from_staging_default", True)))
        if not in_staging:
            self.move_folder.setToolTip("Автоперенос доступен только для песни внутри папки «Добавляю в репертуар».")
        self._update_target_preview()
        self.save_btn.setEnabled(True)
        self.open_folder_btn.setEnabled(True)
        self.additions_btn.setEnabled(True)
        self.files_copy_btn.setEnabled(True)
        self.status.setText("MP3 загружен. Проверь поля и сохрани.")

    def _default_values(self, field) -> list[str]:
        default = field.get("default", field.get("placeholder_value", ""))
        if isinstance(default, list):
            return list(default)
        return [default] if default else []

    def _set_control_values(self, field, control, values: list[str]):
        values = values or self._default_values(field)
        if isinstance(control, QComboBox):
            value = values[0] if values else ""
            idx = control.findData(value)
            if idx < 0 and value:
                control.addItem("⚠ " + value, value)
                idx = control.count() - 1
            control.setCurrentIndex(max(idx, 0))
        else:
            control.set_values(values)

    def _get_control_values(self, field, control) -> list[str]:
        if isinstance(control, QComboBox):
            value = clean(control.currentData())
            return [value] if value else []
        return control.values()

    @staticmethod
    def _first(values: list[str]) -> str:
        return values[0] if values else ""

    @staticmethod
    def _matches_prefix(value: str, prefix: str, storage: dict[str, Any]) -> bool:
        if storage.get("prefix_casefold"):
            return value.casefold().startswith(prefix.casefold())
        return value.startswith(prefix)

    def _show_unknown_warning(self):
        if self.tit1_unknown:
            self.warning_label.setText("Неизвестные/служебные значения TIT1 будут сохранены: " + "; ".join(self.tit1_unknown))
        else:
            self.warning_label.setText("")

    def _parse_filename(self, path: Path) -> dict[str, str]:
        stem = path.stem
        left, sep, info = stem.partition(self.config["filename"].get("info_separator", "֎"))
        version_info = info.strip() if sep else ""
        separator = self.config["filename"].get("separator", "_____")
        title_part, sep2, artist_part = left.partition(separator)
        title_part = title_part.strip()
        artist = artist_part.strip() if sep2 else ""
        tone = ""
        m = re.search(r"\s*\[([^\]]+)\]\s*$", title_part)
        if m:
            tone = m.group(1).strip()
            title_part = title_part[:m.start()].strip()

        version = ""
        vm = re.search(r"\s*\(([^()]+)\)\s*$", title_part)
        if vm:
            candidate = vm.group(1).strip()
            known = {str(v).casefold() for v, _label in self.config["filename"].get("version_options", []) if v}
            if candidate.casefold() in known:
                version = candidate
                title_part = title_part[:vm.start()].strip()

        return {"clean_title": title_part, "artist": artist, "version": version, "tone": tone, "version_info": version_info}

    def _set_version(self, value: str):
        value = clean(value)
        for i in range(self.version.count()):
            if clean(self.version.itemData(i)).casefold() == value.casefold():
                self.version.setCurrentIndex(i)
                return
        if value:
            self.version.setEditText(value)
        else:
            idx = self.version.findData("")
            self.version.setCurrentIndex(max(idx, 0))

    def _version_value(self) -> str:
        data = self.version.currentData()
        if data is not None and clean(self.version.currentText()) == clean(self.version.itemText(self.version.currentIndex())):
            return clean(data)
        text = clean(self.version.currentText())
        if not text or text.casefold() == "обычная":
            return ""
        return text

    def _version_suffix(self) -> str:
        version = self._version_value()
        return f" ({version})" if version else ""

    def _set_tone(self, value: str):
        value = clean(value).strip("[]") or self.config["filename"].get("tone_default", "N")
        idx = self.tone.findData(value)
        if idx < 0:
            self.tone.addItem("⚠ " + value, value)
            idx = self.tone.count() - 1
        self.tone.setCurrentIndex(idx)

    def _tone_suffix(self) -> str:
        tone = clean(self.tone.currentData()) or self.config["filename"].get("tone_default", "N")
        return f" [{tone}]"

    def _info_suffix(self) -> str:
        info = self.version_info.text().strip()
        return f" ֎ {info}" if info else ""

    def _language_values(self) -> list[str]:
        field = self.field_defs.get("language")
        control = self.controls.get("language")
        return self._get_control_values(field, control) if field and control else []

    def _title_symbol(self) -> str:
        values = set(self._language_values())
        has_ru = "Я-рус" in values
        has_foreign = bool(values.intersection({"Я-англ", "Я-ин"}))
        symbols = self.config.get("title", {}).get("symbols", {})
        white = symbols.get("russian", "⚪️")
        red = symbols.get("foreign", "🔴")
        if has_ru and has_foreign:
            return white + red
        if has_ru:
            return white
        if has_foreign:
            return red
        return ""

    def generated_title(self) -> str:
        name = self.clean_title.text().strip()
        symbol = self._title_symbol()
        return f"{symbol} {name}{self._version_suffix()}".strip()

    def reset_title_template(self):
        self.title_manual = False
        self.display_title.setText(self.generated_title())

    def _language_changed(self):
        if not self.title_manual:
            self.display_title.setText(self.generated_title())

    def generated_filename(self) -> str:
        title = self.clean_title.text().strip()
        artist = self.artist.text().strip()
        return f"{title}{self._version_suffix()}{self._tone_suffix()} _____ {artist}{self._info_suffix()}.mp3"

    def generated_folder_name(self) -> str:
        return f"{self.clean_title.text().strip()} _____ {self.artist.text().strip()}"

    def reset_filename_template(self):
        self.filename_manual = False
        self.filename.setText(self.generated_filename())

    def reset_folder_template(self):
        self.folder_manual = False
        self.folder_name.setText(self.generated_folder_name())

    def _auto_names_changed(self):
        if not self.title_manual:
            self.display_title.setText(self.generated_title())
        if not self.filename_manual:
            self.filename.setText(self.generated_filename())
        if not self.folder_manual:
            self.folder_name.setText(self.generated_folder_name())
        self._update_target_preview()

    def _suggest_era(self):
        year = self.year.text().strip()
        control = self.controls.get("era")
        if not isinstance(control, QComboBox) or not year.isdigit():
            return
        current = clean(control.currentData())
        if current not in ("", "э-#"):
            return
        y = int(year)
        mapping = [(2020, "э-20е"), (2010, "э-10е"), (2000, "э-00е"), (1990, "э-90е"), (1980, "э-80е"), (1970, "э-70е"), (1960, "э-60е"), (1950, "э-50е")]
        for start, value in mapping:
            if y >= start:
                idx = control.findData(value)
                if idx >= 0:
                    control.setCurrentIndex(idx)
                break

    def _update_target_preview(self):
        if not self.current_path:
            self.target_label.setText("")
            return
        folder = self.folder_name.text().strip() or self.current_path.parent.name
        if self.move_folder.isChecked():
            target = Path(self.config["paths"]["library_root"]) / folder
            self.target_label.setText(f"Итоговая папка: {target}")
        elif self.rename_folder.isChecked():
            self.target_label.setText(f"Итоговая папка: {self.current_path.parent.parent / folder}")
        else:
            self.target_label.setText(f"Папка останется: {self.current_path.parent}")

    def _is_under(self, child: Path, parent: Path) -> bool:
        try:
            child.resolve().relative_to(parent.resolve())
            return True
        except Exception:
            return False

    def _build_desired_tit1(self) -> list[str]:
        values = list(self.tit1_unknown)
        for field in self.config["fields"]:
            if field["storage"]["kind"] != "tit1_group":
                continue
            values.extend(self._get_control_values(field, self.controls[field["id"]]))
        return list(dict.fromkeys(v for v in values if v))

    def _validate(self) -> tuple[Path, Path | None, Path | None]:
        if not self.current_path or not self.current_path.is_file():
            raise ValueError("Исходный MP3 не найден.")
        if not self.artist.text().strip():
            raise ValueError("Не заполнен исполнитель.")
        if not self.clean_title.text().strip():
            raise ValueError("Не заполнено название.")
        year = self.year.text().strip()
        if year and (not year.isdigit() or not 1900 <= int(year) <= 2100):
            raise ValueError("Год должен быть пустым или числом 1900–2100.")

        filename = self.filename.text().strip()
        if not filename.lower().endswith(".mp3"):
            raise ValueError("Имя файла должно заканчиваться на .mp3")
        if INVALID_WIN_CHARS.search(filename[:-4]) or filename[:-4].endswith((" ", ".")):
            raise ValueError("В имени MP3 есть запрещённые для Windows символы или недопустимое окончание.")
        dest_file = self.current_path.with_name(filename)
        if dest_file != self.current_path and dest_file.exists():
            raise FileExistsError(f"Файл уже существует: {dest_file}")

        current_folder = self.current_path.parent
        folder_target = None
        folder_name = self.folder_name.text().strip()
        if self.rename_folder.isChecked() or self.move_folder.isChecked():
            if not folder_name:
                raise ValueError("Имя папки пустое.")
            if INVALID_WIN_CHARS.search(folder_name) or folder_name.endswith((" ", ".")):
                raise ValueError("В имени папки есть запрещённые для Windows символы.")

        if self.move_folder.isChecked():
            staging = Path(self.config["paths"]["staging_root"])
            if not self._is_under(current_folder, staging) or current_folder == staging:
                raise ValueError("Перенос разрешён только для отдельной папки песни внутри «Добавляю в репертуар».")
            folder_target = Path(self.config["paths"]["library_root"]) / folder_name
        elif self.rename_folder.isChecked():
            folder_target = current_folder.with_name(folder_name)

        if folder_target and folder_target != current_folder and folder_target.exists():
            raise FileExistsError(f"Папка уже существует: {folder_target}")
        return dest_file, folder_target, current_folder

    def _make_plan(self, tags):
        plan = []
        simple = [
            ("Исполнитель", {"kind": "text", "frame": "TPE1"}, self.artist.text().strip()),
            ("Title", {"kind": "text", "frame": "TIT2"}, self.display_title.text().strip()),
            ("Название", {"kind": "text", "frame": "MVNM"}, self.clean_title.text().strip()),
            ("Год", {"kind": "text", "frame": "TDRC"}, self.year.text().strip()),
            ("Ссылка на плюс", {"kind": "url", "frame": "WOAS"}, self.source_url.text().strip()),
            ("Альбом", {"kind": "text", "frame": "TALB"}, self.config["fixed_tags"].get("TALB", "минусы")),
        ]
        for label, spec, desired in simple:
            current = read_field(tags, spec)
            if current != desired:
                plan.append((label, spec, current, desired))

        tit1_desired = self._build_desired_tit1()
        tit1_spec = {"kind": "text", "frame": "TIT1", "multi": True}
        tit1_current = read_field(tags, tit1_spec)
        if tit1_current != tit1_desired:
            plan.append(("Групповые теги", tit1_spec, tit1_current, tit1_desired))

        for field in self.config["fields"]:
            storage = field["storage"]
            if storage["kind"] == "tit1_group":
                continue
            desired_values = self._get_control_values(field, self.controls[field["id"]])
            desired = desired_values if storage.get("multi") else (desired_values[0] if desired_values else "")
            spec = dict(storage)
            current = read_field(tags, spec)
            if current != desired:
                plan.append((field["label"], spec, current, desired))
        return plan

    def _log_operation(self, payload: dict[str, Any]):
        data = APP_ROOT / "data"
        data.mkdir(exist_ok=True)
        path = data / "operations.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")

    def save_all(self):
        if not self.current_path:
            return
        plan = []
        tags_written = False
        original_path = self.current_path
        working_path = original_path
        try:
            dest_file, folder_target, original_folder = self._validate()
            tags = load_tags(original_path)
            plan = self._make_plan(tags)
            self._log_operation({
                "time": datetime.now().isoformat(timespec="seconds"),
                "status": "planned",
                "source": str(original_path),
                "file_target": str(dest_file),
                "folder_target": str(folder_target) if folder_target else "",
                "changes": [{"label": x[0], "old": x[2], "new": x[3]} for x in plan],
            })

            for _label, spec, _old, desired in plan:
                write_field(tags, spec, desired)
            tags.save(original_path, v2_version=4)
            tags_written = True

            verify = load_tags(original_path)
            for label, spec, _old, desired in plan:
                actual = read_field(verify, spec)
                if actual != desired:
                    raise RuntimeError(f"Проверка тега «{label}» не прошла: {actual!r} != {desired!r}")

            if dest_file != original_path:
                working_path = original_path.rename(dest_file)

            if folder_target and folder_target != original_folder:
                moved_folder = Path(shutil.move(str(original_folder), str(folder_target)))
                working_path = moved_folder / working_path.name

            self.current_path = working_path
            self.path_label.setText(str(working_path))
            self.drop.label.setText(working_path.name)
            self._log_operation({
                "time": datetime.now().isoformat(timespec="seconds"),
                "status": "success",
                "result": str(working_path),
            })
            QMessageBox.information(self, "Готово", f"Теги сохранены.\n\n{working_path}")
            self.status.setText("Готово. Файл сохранён и проверен.")
            self.load_file(str(working_path))
        except Exception as exc:
            rollback_note = ""
            if tags_written and plan:
                candidates = [working_path, original_path]
                rollback_path = next((p for p in candidates if p and p.exists()), None)
                if rollback_path:
                    try:
                        rollback_tags = load_tags(rollback_path)
                        for _label, spec, old, _desired in plan:
                            write_field(rollback_tags, spec, old)
                        rollback_tags.save(rollback_path, v2_version=4)
                        rollback_note = "\n\nИсходные управляемые теги восстановлены."
                    except Exception as rollback_exc:
                        rollback_note = f"\n\nНе удалось автоматически откатить теги: {rollback_exc}"
            try:
                self._log_operation({"time": datetime.now().isoformat(timespec="seconds"), "status": "error", "error": str(exc), "file": str(working_path or original_path)})
            except Exception:
                pass
            QMessageBox.critical(self, "Ошибка", str(exc) + rollback_note)
            self.status.setText("Ошибка. Автоматическая обработка остановлена.")

    def create_additions_folder(self):
        if not self.current_path:
            return
        name = self.config.get("file_tools", {}).get("additions_folder", "Additi0ns")
        target = self.current_path.parent / name
        try:
            target.mkdir(exist_ok=True)
            self.status.setText(f"Папка {name} готова.")
            if self.config.get("file_tools", {}).get("open_after_create", True):
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось создать {name}:\n{exc}")

    def copy_to_files_folder(self):
        if not self.current_path:
            return
        folder_name = self.config.get("file_tools", {}).get("files_folder", "Files")
        target_dir = self.current_path.parent / folder_name
        try:
            target_dir.mkdir(exist_ok=True)
            source_name = self.current_path.name
            stem = Path(source_name).stem
            marker = self.config["filename"].get("info_separator", "֎")
            if self.config.get("file_tools", {}).get("files_copy_remove_marker_only", True):
                stem = re.sub(r"\\s*" + re.escape(marker) + r"\\s*", " ", stem).strip()
                stem = re.sub(r"\\s{2,}", " ", stem)
            target = target_dir / f"{stem}.mp3"
            if target.exists():
                raise FileExistsError(f"Файл уже существует:\n{target}")
            shutil.copy2(self.current_path, target)
            self.status.setText(f"Копия создана в {folder_name}.")
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target_dir)))
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось создать копию в {folder_name}:\n{exc}")

    def show_help(self):
        help_name = self.config.get("help", {}).get("file", "СПРАВКА.md")
        help_path = APP_ROOT / help_name
        if not help_path.is_file():
            QMessageBox.warning(self, "Справка", f"Файл справки не найден:\n{help_path}")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Обозначения в примечании")
        dialog.resize(720, 560)
        layout = QVBoxLayout(dialog)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setMarkdown(help_path.read_text(encoding="utf-8"))
        layout.addWidget(browser)
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        dialog.exec()

    def _reset_controls_to_defaults(self):
        for field in self.config["fields"]:
            self._set_control_values(field, self.controls[field["id"]], [])

    def open_current_folder(self):
        if self.current_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current_path.parent)))

    def clear_form(self):
        self.current_path = None
        self.drop.label.setText("Перетащи сюда MP3-минусовку")
        self.path_label.setText("Файл не выбран")
        for edit in (self.artist, self.clean_title, self.display_title, self.year, self.source_url, self.version_info, self.filename, self.folder_name):
            edit.clear()
        self.title_manual = False
        self.filename_manual = False
        self.folder_manual = False
        self._set_version("")
        self._set_tone(self.config["filename"].get("tone_default", "N"))
        self._reset_controls_to_defaults()
        self.rename_folder.setChecked(False)
        self.move_folder.setChecked(False)
        self.move_folder.setEnabled(False)
        self.warning_label.clear()
        self.target_label.clear()
        self.save_btn.setEnabled(False)
        self.open_folder_btn.setEnabled(False)
        self.additions_btn.setEnabled(False)
        self.files_copy_btn.setEnabled(False)
        self.status.setText("Готов к загрузке MP3")


def run():
    app = QApplication(sys.argv)
    app.setApplicationName("Добавление минуса в репертуар")
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())
