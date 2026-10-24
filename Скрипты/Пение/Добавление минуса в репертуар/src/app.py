from __future__ import annotations

import ftplib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from PySide6.QtCore import Qt, QSignalBlocker, Signal, QTimer
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QInputDialog,
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
        self.setMinimumHeight(36)
        self._placeholder = placeholder_value
        self._actions: dict[str, QAction] = {}
        self._labels: dict[str, str] = {}
        self._known_values: set[str] = set()
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
        if not unknown:
            self._known_values.add(value)

    def clear_dynamic_options(self):
        for value in list(self._actions):
            if value in self._known_values:
                continue
            action = self._actions.pop(value)
            self._labels.pop(value, None)
            self.menu().removeAction(action)
            action.deleteLater()
        self._refresh_text()

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



class CollapsibleSection(QWidget):
    def __init__(self, title: str, expanded: bool = False, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.header = QToolButton()
        self.header.setCheckable(True)
        self.header.setChecked(expanded)
        self.header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.header.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.header.setText(title)
        self.header.setObjectName("sectionHeader")
        self.header.toggled.connect(self._toggle)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(8, 4, 8, 8)
        self.body_layout.setSpacing(10)
        self.body.setVisible(expanded)

        layout.addWidget(self.header)
        layout.addWidget(self.body)

    def _toggle(self, expanded: bool):
        self.header.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.body.setVisible(expanded)

    def add_widget(self, widget: QWidget):
        self.body_layout.addWidget(widget)

    def add_layout(self, layout):
        self.body_layout.addLayout(layout)


class PlusDropFrame(QFrame):
    fileDropped = Signal(str)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("plusDropFrame")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        self.label = QLabel("Перетащи сюда плюс (MP3)")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setObjectName("dropTitle")
        hint = QLabel("Перетащи MP3 — загрузка на FTP начнётся автоматически")
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
        self.field_labels: dict[str, QLabel] = {}
        self.field_defs: dict[str, dict[str, Any]] = {f["id"]: f for f in self.config["fields"]}
        self.tit1_unknown: list[str] = []
        self.unmapped_structured_tags: list[str] = []
        self.invalid_fields: dict[str, list[str]] = {}
        self.plus_path: Path | None = None
        self._plus_upload_in_progress = False
        self.network_manager = QNetworkAccessManager(self)
        self._link_check_reply: QNetworkReply | None = None
        self._build_ui()
        self._apply_style()
        app = QApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(self._application_state_changed)
        self.setWindowTitle("Добавление минуса в репертуар")
        self.resize(1100, 760)

    def _section_setting(self, section_id: str) -> dict[str, Any]:
        for item in self.config.get("ui", {}).get("sections", []):
            if item.get("id") == section_id:
                return item
        return {"id": section_id, "label": section_id, "expanded": False}

    def _make_section(self, section_id: str) -> CollapsibleSection:
        cfg = self._section_setting(section_id)
        return CollapsibleSection(cfg.get("label", section_id), bool(cfg.get("expanded", False)))

    def _build_ui(self):
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(8)

        top = QHBoxLayout()
        self.drop = DropFrame()
        self.drop.setMaximumHeight(72)
        self.drop.fileDropped.connect(self.load_file)
        top.addWidget(self.drop, 1)
        choose = QPushButton("Выбрать MP3")
        choose.clicked.connect(self.choose_file)
        choose.setMinimumWidth(140)
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
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(7)

        # 1. Песня и файл
        song_section = self._make_section("song_file")
        song_widget = QWidget()
        grid = QGridLayout(song_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(9)
        grid.setVerticalSpacing(6)

        self.artist = QLineEdit()
        self.clean_title = QLineEdit()
        self.version = QComboBox()
        self.version.setEditable(True)
        for value, label in self.config["filename"].get("version_options", []):
            self.version.addItem(label, value)
        self.version.setInsertPolicy(QComboBox.NoInsert)
        self.display_title = QLineEdit()
        self.tone = QComboBox()
        tone_options = self.config["filename"].get(
            "tone_options",
            [["", "—"], ["N", "N — неизвестно"], ["-3", "-3"], ["-2", "-2"], ["-1", "-1"], ["0", "0"], ["+1", "+1"], ["+2", "+2"], ["+3", "+3"]],
        )
        for item in tone_options:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                value, label = item
            else:
                value = str(item)
                label = "N — неизвестно" if value == "N" else value
            self.tone.addItem(label, value)

        self.length_version = QComboBox()
        for value, label in self.config["filename"].get("length_options", [["", "—"], ["F", "F — полная"], ["S", "S — сокращённая"]]):
            self.length_version.addItem(label, value)

        self.version_info = QLineEdit()
        self.version_info.setPlaceholderText("Свободный текст или быстрые чипы ниже")
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

        grid.addWidget(QLabel("Тональность"), 3, 0)
        grid.addWidget(self.tone, 3, 1)
        grid.addWidget(QLabel("F / S"), 3, 2)
        grid.addWidget(self.length_version, 3, 3)

        grid.addWidget(QLabel("Примечание"), 4, 0)
        grid.addWidget(self.version_info, 4, 1, 1, 4)
        help_btn = QToolButton()
        help_btn.setText("ⓘ")
        help_btn.setToolTip("Справка по обозначениям")
        help_btn.clicked.connect(self.show_help)
        grid.addWidget(help_btn, 4, 5)

        chips = QHBoxLayout()
        chips.setSpacing(5)
        for value, tooltip in self.config.get("note_chips", []):
            chip = QPushButton(value)
            chip.setProperty("chip", True)
            chip.setToolTip(tooltip)
            chip.clicked.connect(lambda _checked=False, v=value: self._append_note_chip(v))
            chips.addWidget(chip)
        chips.addStretch(1)
        grid.addLayout(chips, 5, 1, 1, 5)

        grid.addWidget(QLabel("Файл минуса"), 6, 0)
        grid.addWidget(self.filename, 6, 1, 1, 4)
        reset_name = QPushButton("По шаблону")
        reset_name.clicked.connect(self.reset_filename_template)
        grid.addWidget(reset_name, 6, 5)

        grid.addWidget(QLabel("Папка песни"), 7, 0)
        grid.addWidget(self.folder_name, 7, 1, 1, 4)
        reset_folder = QPushButton("По шаблону")
        reset_folder.clicked.connect(self.reset_folder_template)
        grid.addWidget(reset_folder, 7, 5)

        self.rename_folder = QCheckBox("Переименовать папку песни по шаблону")
        self.move_folder = QCheckBox("Перенести папку песни в основной репертуар")
        grid.addWidget(self.rename_folder, 8, 1, 1, 2)
        grid.addWidget(self.move_folder, 8, 3, 1, 3)

        self.target_label = QLabel("")
        self.target_label.setObjectName("muted")
        grid.addWidget(self.target_label, 9, 1, 1, 5)

        song_section.add_widget(song_widget)
        body_layout.addWidget(song_section)

        # 2. Теги и подбор
        tags_section = self._make_section("tags")
        sections = QHBoxLayout()
        perf = QGroupBox("Выступление")
        perf_form = QFormLayout(perf)
        search = QGroupBox("Поиск и сайт")
        search_form = QFormLayout(search)

        self.year = QLineEdit()
        self.year.setMaximumWidth(120)
        search_form.addRow("Год", self.year)

        for field in self.config["fields"]:
            control = self._make_field_control(field)
            field_label = QLabel(field["label"])
            self.controls[field["id"]] = control
            self.field_labels[field["id"]] = field_label
            section = field["section"]
            if section == "performance":
                perf_form.addRow(field_label, control)
            elif section == "search":
                search_form.addRow(field_label, control)

        sections.addWidget(perf, 1)
        sections.addWidget(search, 1)
        tags_section.add_layout(sections)
        body_layout.addWidget(tags_section)

        # 3. Анализ аудио
        analysis_section = self._make_section("audio_analysis")
        analysis_widget = QWidget()
        analysis_layout = QGridLayout(analysis_widget)
        analysis_layout.setContentsMargins(0, 0, 0, 0)
        analysis_layout.setHorizontalSpacing(10)
        analysis_layout.setVerticalSpacing(8)

        self.foobar_btn = QPushButton("♫ Открыть минус в foobar2000")
        self.foobar_btn.setToolTip("Открыть текущий MP3 в foobar2000 для анализа BPM и ReplayGain")
        self.foobar_btn.clicked.connect(self.open_in_foobar)
        self.foobar_btn.setEnabled(False)

        self.refresh_analysis_btn = QPushButton("↻ Проверить BPM / ReplayGain")
        self.refresh_analysis_btn.setToolTip("Перечитать только BPM и ReplayGain из текущего MP3")
        self.refresh_analysis_btn.clicked.connect(lambda: self.refresh_audio_analysis(True))
        self.refresh_analysis_btn.setEnabled(False)

        self.bpm_status_label = QLabel("— BPM не проверен")
        self.replaygain_status_label = QLabel("— ReplayGain не проверен")
        self.bpm_status_label.setObjectName("muted")
        self.replaygain_status_label.setObjectName("muted")

        analysis_hint = QLabel(
            "В foobar2000 выполни анализ BPM и ReplayGain через контекстное меню, "
            "затем вернись в программу — статусы обновятся автоматически."
        )
        analysis_hint.setWordWrap(True)
        analysis_hint.setObjectName("muted")

        analysis_layout.addWidget(self.foobar_btn, 0, 0)
        analysis_layout.addWidget(self.refresh_analysis_btn, 0, 1)
        analysis_layout.addWidget(QLabel("BPM"), 1, 0)
        analysis_layout.addWidget(self.bpm_status_label, 1, 1)
        analysis_layout.addWidget(QLabel("ReplayGain"), 2, 0)
        analysis_layout.addWidget(self.replaygain_status_label, 2, 1)
        analysis_layout.addWidget(analysis_hint, 3, 0, 1, 2)

        analysis_section.add_widget(analysis_widget)
        body_layout.addWidget(analysis_section)

        # 4. Плюс песни
        plus_section = self._make_section("plus")
        plus_top = QHBoxLayout()
        self.plus_drop = PlusDropFrame()
        self.plus_drop.fileDropped.connect(self.set_plus_file)
        self.plus_drop.setMaximumHeight(82)
        plus_top.addWidget(self.plus_drop, 1)

        plus_buttons = QVBoxLayout()
        choose_plus = QPushButton("Выбрать плюс")
        choose_plus.clicked.connect(self.choose_plus_file)
        self.upload_plus_btn = QPushButton("⬆ Загрузить на FTP")
        self.upload_plus_btn.clicked.connect(self.upload_plus)
        plus_buttons.addWidget(choose_plus)
        plus_buttons.addWidget(self.upload_plus_btn)
        plus_top.addLayout(plus_buttons)
        plus_section.add_layout(plus_top)

        plus_form_widget = QWidget()
        plus_form = QFormLayout(plus_form_widget)
        plus_form.setContentsMargins(0, 0, 0, 0)
        self.plus_path_label = QLabel("Плюс не выбран")
        self.plus_path_label.setObjectName("muted")
        self.plus_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.source_url = QLineEdit()
        self.source_url.setPlaceholderText("После FTP-загрузки ссылка появится здесь автоматически")
        self.source_url.textEdited.connect(self._mark_plus_url_dirty)

        self.check_plus_btn = QToolButton()
        self.check_plus_btn.setText("✓")
        self.check_plus_btn.setToolTip("Проверить, что ссылка действительно открывается")
        self.check_plus_btn.clicked.connect(lambda: self.check_plus_url(True))

        self.open_plus_btn = QToolButton()
        self.open_plus_btn.setText("▶")
        self.open_plus_btn.setToolTip("Открыть / проиграть плюс по публичной ссылке")
        self.open_plus_btn.clicked.connect(self.open_plus_url)

        url_row = QHBoxLayout()
        url_row.addWidget(self.source_url, 1)
        url_row.addWidget(self.check_plus_btn)
        url_row.addWidget(self.open_plus_btn)

        self.plus_link_status = QLabel("— ссылка не проверена")
        self.plus_link_status.setObjectName("muted")

        plus_form.addRow("Файл плюса", self.plus_path_label)
        plus_form.addRow("Ссылка на плюс", url_row)
        plus_form.addRow("Проверка", self.plus_link_status)
        plus_section.add_widget(plus_form_widget)
        body_layout.addWidget(plus_section)

        # 5. Файлы песни
        file_tools_section = self._make_section("file_tools")
        file_tools_layout = QHBoxLayout()
        self.additions_btn = QPushButton("📁 Additi0ns")
        self.additions_btn.setToolTip("Создать/открыть подпапку Additi0ns для дополнительных версий минуса")
        self.additions_btn.clicked.connect(self.create_additions_folder)
        file_tools_layout.addWidget(self.additions_btn)
        self.files_copy_btn = QPushButton("✂ Копия в Files")
        self.files_copy_btn.setToolTip("Создать подпапку Files и скопировать туда текущий MP3, убрав из имени символ ֎")
        self.files_copy_btn.clicked.connect(self.copy_to_files_folder)
        file_tools_layout.addWidget(self.files_copy_btn)
        file_tools_layout.addStretch(1)
        file_tools_section.add_layout(file_tools_layout)
        body_layout.addWidget(file_tools_section)

        self.warning_label = QLabel("")
        self.warning_label.setWordWrap(True)
        self.warning_label.setObjectName("warning")
        body_layout.addWidget(self.warning_label)
        body_layout.addStretch(1)

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
        self.version.currentTextChanged.connect(self._version_changed)
        self.tone.currentIndexChanged.connect(self._auto_names_changed)
        self.length_version.currentIndexChanged.connect(self._auto_names_changed)
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
        self._set_version("")
        self._set_tone(self.config["filename"].get("tone_default", ""))
        self._set_length(self.config["filename"].get("length_default", ""))
        self.additions_btn.setEnabled(False)
        self.files_copy_btn.setEnabled(False)
        self.upload_plus_btn.setEnabled(False)

    def _make_field_control(self, field: dict[str, Any]):
        if field["control"] == "single_select":
            combo = QComboBox()
            combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            for value, label in field.get("options", []):
                combo.addItem(label, value)
            combo.currentIndexChanged.connect(
                lambda _index, f=field, control=combo: self._revalidate_control(f, control)
            )
            return combo
        if field["control"] == "multi_select":
            button = MultiSelectButton(field.get("options", []), field.get("placeholder_value", ""))
            button.changed.connect(
                lambda f=field, control=button: self._revalidate_control(f, control)
            )
            return button
        raise ValueError(f"Unsupported control: {field['control']}")

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #15181d; color: #e9edf2; font-size: 13px; }
            QGroupBox { border: 1px solid #353b44; border-radius: 8px; margin-top: 10px; padding: 12px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QLineEdit, QComboBox, QToolButton { background: #20252c; border: 1px solid #3d4652; border-radius: 6px; padding: 7px; min-height: 20px; }
            QToolButton { text-align: center; }
            QLabel[attention="true"] { color: #f2c94c; }
            QComboBox[invalid="true"], QToolButton[invalid="true"] { border: 2px solid #d85353; background: #342226; }
            QPushButton { background: #272d35; border: 1px solid #414a56; border-radius: 6px; padding: 8px 12px; }
            QPushButton:hover, QToolButton:hover { background: #313945; }
            QPushButton#primary { background: #276749; border-color: #3c8a68; font-weight: 700; padding: 10px 18px; }
            QPushButton#primary:hover { background: #32805c; }
            QFrame#dropFrame, QFrame#plusDropFrame { border: 2px dashed #536170; border-radius: 10px; padding: 8px; background: #1b2026; }
            QToolButton#sectionHeader { background: #20252c; border: 1px solid #353b44; border-radius: 7px; padding: 8px 10px; font-weight: 700; text-align: left; }
            QPushButton[chip="true"] { padding: 4px 8px; border-radius: 10px; min-height: 18px; }
            QLabel#dropTitle { font-size: 16px; font-weight: 700; }
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

        existing_artist = self._first(read_text(tags, "TPE1"))
        existing_name = self._first(read_text(tags, "MVNM"))
        existing_title = self._first(read_text(tags, "TIT2"))
        inferred = self._parse_filename(path)

        parse_cfg = self.config.get("filename", {}).get("source_parse", {})
        prefer_filename = bool(parse_cfg.get("prefer_filename_artist_title", True))
        if prefer_filename:
            self.artist.setText(inferred["artist"] or existing_artist)
            self.clean_title.setText(inferred["clean_title"] or existing_name)
        else:
            self.artist.setText(existing_artist or inferred["artist"])
            self.clean_title.setText(existing_name or inferred["clean_title"])

        self.year.setText(self._first(read_text(tags, "TDRC")))
        self.source_url.setText(read_url(tags, "WOAS"))
        self._set_plus_link_status("idle", "— ссылка не проверена")

        self._set_version(inferred["version"] or self._extract_version(existing_title))
        tone_from_title = self._extract_tone(existing_title)
        length_from_title = self._extract_length(existing_title)
        self._set_tone(inferred["tone"] or tone_from_title or self.config["filename"].get("tone_default", ""))
        self._set_length(inferred["length"] or length_from_title)
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
        self.unmapped_structured_tags = [
            value for value in self.tit1_unknown
            if re.match(r"^[^\s;]{1,8}-", value)
        ]
        self._show_unknown_warning()

        self.title_manual = False
        self.display_title.setText(self.generated_title())

        self.filename_manual = False
        self.folder_manual = False
        self.reset_filename_template()
        self.reset_folder_template()
        self.rename_folder.setChecked(bool(self.config["folder"].get("rename_default", True)))

        library_root = Path(self.config["paths"]["library_root"])
        current_folder = path.parent
        already_in_library = current_folder.parent.resolve() == library_root.resolve()
        self.move_folder.setEnabled(current_folder.resolve() != library_root.resolve())
        self.move_folder.setChecked(not already_in_library and bool(self.config["folder"].get("move_to_library_default", True)))
        self.move_folder.setToolTip(
            "Можно перенести текущую папку песни в основной репертуар независимо от её исходного расположения."
        )
        self._update_target_preview()
        self.save_btn.setEnabled(True)
        self.open_folder_btn.setEnabled(True)
        self.additions_btn.setEnabled(True)
        self.files_copy_btn.setEnabled(True)
        self.foobar_btn.setEnabled(True)
        self.refresh_analysis_btn.setEnabled(True)
        self.refresh_audio_analysis(False)
        self.upload_plus_btn.setEnabled(bool(self.plus_path and self.plus_path.is_file()))
        self.status.setText("MP3 загружен. Проверь поля и сохрани.")
        if self.source_url.text().strip():
            QTimer.singleShot(250, lambda: self.check_plus_url(False))

    def _default_values(self, field) -> list[str]:
        default = field.get("default", field.get("placeholder_value", ""))
        if isinstance(default, list):
            return list(default)
        return [default] if default else []

    def _allowed_values(self, field) -> list[str]:
        return [clean(value) for value, _label in field.get("options", [])]

    def _canonicalize_values(self, field, values: list[str]) -> list[str]:
        allowed = self._allowed_values(field)
        storage = field.get("storage", {})
        casefold = bool(storage.get("prefix_casefold"))
        result = []
        for raw in values:
            value = clean(raw)
            if not value:
                continue
            if value in allowed:
                result.append(value)
                continue
            if casefold:
                matched = next((a for a in allowed if a.casefold() == value.casefold()), None)
                if matched:
                    result.append(matched)
                    continue
            result.append(value)
        return list(dict.fromkeys(result))

    def _set_invalid_state(self, field, control, invalid_values: list[str]):
        field_id = field["id"]
        if invalid_values:
            self.invalid_fields[field_id] = invalid_values
            control.setProperty("invalid", True)
            control.setToolTip(
                "Значение есть в MP3, но отсутствует в текущей схеме: "
                + ", ".join(invalid_values)
                + "\nВыбери актуальное значение перед сохранением."
            )
        else:
            self.invalid_fields.pop(field_id, None)
            control.setProperty("invalid", False)
            control.setToolTip("")
        control.style().unpolish(control)
        control.style().polish(control)

    def _clear_dynamic_values(self, field, control):
        allowed = set(self._allowed_values(field))
        if isinstance(control, QComboBox):
            for index in range(control.count() - 1, -1, -1):
                value = clean(control.itemData(index))
                if value and value not in allowed:
                    control.removeItem(index)
        else:
            control.clear_dynamic_options()

    def _set_control_values(self, field, control, values: list[str]):
        self._clear_dynamic_values(field, control)
        source_values = self._canonicalize_values(field, values)
        values_to_show = source_values or self._default_values(field)
        allowed = set(self._allowed_values(field))
        invalid = [value for value in source_values if value not in allowed]

        if isinstance(control, QComboBox):
            value = values_to_show[0] if values_to_show else ""
            idx = control.findData(value)
            if idx < 0 and value:
                control.addItem("⚠ " + value, value)
                idx = control.count() - 1
            with QSignalBlocker(control):
                control.setCurrentIndex(max(idx, 0))
        else:
            control.set_values(values_to_show)

        self._set_invalid_state(field, control, invalid)
        self._update_attention_label(field, control)

    def _revalidate_control(self, field, control):
        values = self._canonicalize_values(field, self._get_control_values(field, control))
        allowed = set(self._allowed_values(field))
        invalid = [value for value in values if value not in allowed]
        self._set_invalid_state(field, control, invalid)
        self._update_attention_label(field, control)

    def _update_attention_label(self, field, control):
        label = self.field_labels.get(field["id"])
        if label is None:
            return

        needs_attention = False
        if field.get("attention_required"):
            values = self._canonicalize_values(field, self._get_control_values(field, control))
            placeholder = clean(field.get("placeholder_value"))
            mode = field.get("attention_mode", "placeholder")
            if mode == "placeholder":
                needs_attention = bool(placeholder and placeholder in values)
            elif mode == "empty_or_placeholder":
                needs_attention = (not values) or bool(placeholder and placeholder in values)

        label.setProperty("attention", needs_attention)
        font = label.font()
        font.setUnderline(needs_attention)
        label.setFont(font)
        label.style().unpolish(label)
        label.style().polish(label)

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
        if self.unmapped_structured_tags:
            self.warning_label.setStyleSheet("color: #ef6b6b; font-weight: 600;")
            self.warning_label.setText(
                "⚠ Теги не входят в текущую схему и требуют исправления: "
                + "; ".join(self.unmapped_structured_tags)
            )
        elif self.tit1_unknown:
            self.warning_label.setStyleSheet("color: #f0b45d;")
            self.warning_label.setText(
                "Неуправляемые значения TIT1 будут сохранены: "
                + "; ".join(self.tit1_unknown)
            )
        else:
            self.warning_label.setStyleSheet("")
            self.warning_label.setText("")

    def _parse_filename(self, path: Path) -> dict[str, str]:
        stem = path.stem
        filename_cfg = self.config.get("filename", {})
        parse_cfg = filename_cfg.get("source_parse", {})
        info_separator = filename_cfg.get("info_separator", "֎")

        left, sep, info = stem.partition(info_separator)
        version_info = info.strip() if sep else ""
        left = left.strip()

        separator = filename_cfg.get("separator", "_____")
        title_part, canonical_sep, artist_part = left.partition(separator)

        if canonical_sep:
            # Current canonical format: Название _____ Исполнитель
            title_part = title_part.strip()
            artist = artist_part.strip()
        else:
            # Ordinary source file: Исполнитель - Название
            artist = ""
            title_part = left
            for source_sep in parse_cfg.get(
                "artist_title_separators",
                [" - ", " – ", " — "],
            ):
                before, found, after = left.partition(source_sep)
                if found and before.strip() and after.strip():
                    artist = before.strip()
                    title_part = after.strip()
                    break

        length = ""
        lm = re.search(r"\s*\[(F|S)\]\s*$", title_part, re.IGNORECASE)
        if lm:
            length = lm.group(1).upper()
            title_part = title_part[:lm.start()].strip()

        tone = ""
        legacy_zero = re.search(r"\s*\[0\]\s*$", title_part)
        if legacy_zero:
            title_part = title_part[:legacy_zero.start()].strip()

        tm = re.search(r"\s*\[(N|[+-]?[1-3])\]\s*$", title_part, re.IGNORECASE)
        if tm:
            tone = tm.group(1).upper() if tm.group(1).upper() == "N" else tm.group(1)
            title_part = title_part[:tm.start()].strip()

        version = ""
        vm = re.search(r"\s*\(([^()]+)\)\s*$", title_part)
        if vm:
            candidate = vm.group(1).strip()
            known = {
                str(v).casefold(): str(v)
                for v, _label in filename_cfg.get("version_options", [])
                if v
            }
            matched = known.get(candidate.casefold())
            if matched:
                version = matched
                title_part = title_part[:vm.start()].strip()

        # Legacy/source bracket note, e.g. [мастер запись].
        if parse_cfg.get("trailing_bracket_to_note", True):
            note_match = re.search(r"\s*\[([^\]]+)\]\s*$", title_part)
            if note_match:
                raw_note = note_match.group(1).strip()
                aliases = {
                    clean(k).casefold(): clean(v)
                    for k, v in parse_cfg.get("note_aliases", {}).items()
                }
                note_value = aliases.get(raw_note.casefold(), raw_note)
                if note_value:
                    current = [p.strip() for p in version_info.split(",") if p.strip()]
                    if note_value not in current:
                        current.append(note_value)
                    version_info = ", ".join(current)
                title_part = title_part[:note_match.start()].strip()

        return {
            "clean_title": title_part.strip(),
            "artist": artist.strip(),
            "version": version,
            "tone": tone,
            "length": length,
            "version_info": version_info,
        }

    def _extract_version(self, text: str) -> str:
        match = re.search(r"\(([^()]+)\)", clean(text))
        if not match:
            return ""
        candidate = match.group(1).strip()
        known = {
            clean(value).casefold(): clean(value)
            for value, _label in self.config["filename"].get("version_options", [])
            if clean(value)
        }
        return known.get(candidate.casefold(), "")

    @staticmethod
    def _extract_length(text: str) -> str:
        match = re.search(r"\[(F|S)\]", clean(text), re.IGNORECASE)
        return match.group(1).upper() if match else ""

    @staticmethod
    def _extract_tone(text: str) -> str:
        matches = re.findall(r"\[(N|[+-]?[1-3])\]", clean(text), re.IGNORECASE)
        for value in matches:
            if value.upper() in {"F", "S"}:
                continue
            return value.upper() if value.upper() == "N" else value
        return ""

    def _set_length(self, value: str):
        value = clean(value).upper()
        idx = self.length_version.findData(value)
        if idx < 0:
            idx = self.length_version.findData("")
        self.length_version.setCurrentIndex(max(idx, 0))

    def _length_suffix(self) -> str:
        value = clean(self.length_version.currentData()).upper()
        return f" [{value}]" if value in {"F", "S"} else ""

    def _known_version_values(self) -> list[str]:
        return [
            clean(value)
            for value, _label in self.config.get("filename", {}).get("version_options", [])
            if clean(value)
        ]

    def _strip_version_suffix(self, title: str) -> str:
        result = clean(title)
        candidates = set(self._known_version_values())
        current = self._version_value() if hasattr(self, "version") else ""
        if current:
            candidates.add(current)
        for candidate in sorted(candidates, key=len, reverse=True):
            suffix = f" ({candidate})"
            if result.casefold().endswith(suffix.casefold()):
                return result[:-len(suffix)].rstrip()
        return result

    def _set_version(self, value: str):
        value = clean(value)
        matched_index = -1
        for i in range(self.version.count()):
            data = clean(self.version.itemData(i))
            if data.casefold() == value.casefold():
                matched_index = i
                break

        with QSignalBlocker(self.version):
            if matched_index >= 0:
                self.version.setCurrentIndex(matched_index)
            elif value:
                self.version.setEditText(value)
            else:
                idx = self.version.findData("")
                self.version.setCurrentIndex(max(idx, 0))

        self._apply_version_to_name_field()
        self._auto_names_changed()

    def _version_value(self) -> str:
        data = self.version.currentData()
        if (
            data is not None
            and clean(self.version.currentText())
            == clean(self.version.itemText(self.version.currentIndex()))
        ):
            return clean(data)
        text = clean(self.version.currentText())
        if not text or text == "—":
            return ""
        return text

    def _version_suffix(self) -> str:
        version = self._version_value()
        return f" ({version})" if version else ""

    def _apply_version_to_name_field(self):
        if not self.config.get("filename", {}).get("version_in_name_field", True):
            return
        if not hasattr(self, "clean_title"):
            return

        base = self._strip_version_suffix(self.clean_title.text())
        version = self._version_value()
        desired = f"{base} ({version})" if base and version else base

        if self.clean_title.text().strip() != desired:
            with QSignalBlocker(self.clean_title):
                self.clean_title.setText(desired)

    def _version_changed(self):
        self._apply_version_to_name_field()
        self._auto_names_changed()

    def _set_tone(self, value: str):
        value = clean(value).strip("[]") or clean(self.config["filename"].get("tone_default", ""))
        idx = self.tone.findData(value)
        if idx < 0:
            self.tone.addItem("⚠ " + value, value)
            idx = self.tone.count() - 1
        self.tone.setCurrentIndex(idx)

    def _tone_suffix(self) -> str:
        tone = clean(self.tone.currentData()) or clean(self.config["filename"].get("tone_default", ""))
        return f" [{tone}]" if tone else ""

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
        return f"{symbol} {name}{self._tone_suffix()}{self._length_suffix()}".strip()

    def reset_title_template(self):
        self.title_manual = False
        self.display_title.setText(self.generated_title())

    def _language_changed(self):
        if not self.title_manual:
            self.display_title.setText(self.generated_title())

    def generated_filename(self) -> str:
        title = self.clean_title.text().strip()
        artist = self.artist.text().strip()
        return f"{title}{self._tone_suffix()}{self._length_suffix()} _____ {artist}{self._info_suffix()}.mp3"

    def generated_folder_name(self) -> str:
        base_name = self._strip_version_suffix(self.clean_title.text())
        return f"{base_name} _____ {self.artist.text().strip()}"

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
        if self.unmapped_structured_tags:
            raise ValueError(
                "В TIT1 есть теги, которых нет в текущей схеме:\n"
                + "; ".join(self.unmapped_structured_tags)
                + "\n\nИсправь их перед сохранением."
            )
        if self.invalid_fields:
            details = []
            for field_id, values in self.invalid_fields.items():
                label = self.field_defs.get(field_id, {}).get("label", field_id)
                details.append(f"{label}: {', '.join(values)}")
            raise ValueError(
                "В MP3 есть значения, которых нет в текущей схеме тегов:\n"
                + "\n".join(details)
                + "\n\nИсправь красные поля перед сохранением."
            )
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
            library_root = Path(self.config["paths"]["library_root"])
            if current_folder.resolve() == library_root.resolve():
                raise ValueError("Нельзя переносить корень основного репертуара как папку песни.")
            folder_target = library_root / folder_name
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

    def _application_state_changed(self, state):
        if state == Qt.ApplicationState.ApplicationActive and self.current_path:
            QTimer.singleShot(200, lambda: self.refresh_audio_analysis(False))

    @staticmethod
    def _set_analysis_status(label: QLabel, state: str, text: str):
        colors = {
            "idle": "#9ba6b2",
            "ok": "#63d69a",
            "warning": "#f2c94c",
            "error": "#ef6b6b",
        }
        label.setText(text)
        label.setStyleSheet(f"color: {colors.get(state, '#9ba6b2')};")

    def open_in_foobar(self):
        if not self.current_path or not self.current_path.is_file():
            QMessageBox.warning(self, "foobar2000", "Сначала перетащи MP3-минус.")
            return

        exe = Path(
            self.config.get("audio_analysis", {}).get(
                "foobar_path",
                r"C:\Program Files\foobar2000\foobar2000.exe",
            )
        )
        if not exe.is_file():
            QMessageBox.critical(
                self,
                "foobar2000 не найден",
                "Не найден foobar2000 по адресу:\n"
                f"{exe}\n\n"
                "Путь можно изменить в config.json → audio_analysis.foobar_path.",
            )
            return

        try:
            subprocess.Popen([str(exe), str(self.current_path)])
            self.status.setText("Текущий минус открыт в foobar2000.")
        except Exception as exc:
            QMessageBox.critical(self, "foobar2000", f"Не удалось открыть файл:\n{exc}")

    def refresh_audio_analysis(self, show_message: bool = False):
        if not self.current_path or not self.current_path.is_file():
            self._set_analysis_status(self.bpm_status_label, "idle", "— BPM не проверен")
            self._set_analysis_status(
                self.replaygain_status_label,
                "idle",
                "— ReplayGain не проверен",
            )
            return

        cfg = self.config.get("audio_analysis", {})
        bpm_frame = clean(cfg.get("bpm_frame")) or "TBPM"
        gain_frame = clean(cfg.get("replaygain_gain_frame")) or "TXXX:replaygain_track_gain"
        peak_frame = clean(cfg.get("replaygain_peak_frame")) or "TXXX:replaygain_track_peak"

        try:
            tags = load_tags(self.current_path)
            bpm = read_field(tags, {"kind": "text", "frame": bpm_frame})
            gain = read_field(tags, {"kind": "txxx", "frame": gain_frame})
            peak = read_field(tags, {"kind": "txxx", "frame": peak_frame})

            if bpm:
                self._set_analysis_status(self.bpm_status_label, "ok", f"✓ {bpm} BPM")
            else:
                self._set_analysis_status(self.bpm_status_label, "warning", "— BPM не рассчитан")

            if gain and peak:
                self._set_analysis_status(
                    self.replaygain_status_label,
                    "ok",
                    f"✓ gain {gain} · peak {peak}",
                )
            elif gain or peak:
                parts = []
                if gain:
                    parts.append(f"gain {gain}")
                if peak:
                    parts.append(f"peak {peak}")
                self._set_analysis_status(
                    self.replaygain_status_label,
                    "warning",
                    "⚠ ReplayGain неполный · " + " · ".join(parts),
                )
            else:
                self._set_analysis_status(
                    self.replaygain_status_label,
                    "warning",
                    "— ReplayGain не рассчитан",
                )

            if show_message:
                self.status.setText("BPM и ReplayGain перечитаны из MP3.")
        except Exception as exc:
            self._set_analysis_status(self.bpm_status_label, "error", "✕ ошибка чтения")
            self._set_analysis_status(
                self.replaygain_status_label,
                "error",
                "✕ ошибка чтения",
            )
            if show_message:
                QMessageBox.critical(
                    self,
                    "Анализ аудио",
                    f"Не удалось прочитать BPM / ReplayGain:\n{exc}",
                )

    def _append_note_chip(self, value: str):
        current = [part.strip() for part in self.version_info.text().split(",") if part.strip()]
        if value not in current:
            current.append(value)
            self.version_info.setText(", ".join(current))

    def choose_plus_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выбери плюс песни", "", "MP3 (*.mp3)")
        if path:
            self.set_plus_file(path)

    def set_plus_file(self, path_str: str):
        path = Path(path_str)
        if not path.is_file() or path.suffix.lower() != ".mp3":
            QMessageBox.warning(self, "Не MP3", "Для плюса сейчас поддерживается MP3.")
            return
        self.plus_path = path
        self.plus_path_label.setText(str(path))
        self.plus_drop.label.setText(f"{path.name} · готовлю загрузку…")
        can_upload = bool(self.current_path and self.current_path.is_file())
        self.upload_plus_btn.setEnabled(can_upload)

        if self.config.get("plus_upload", {}).get("auto_upload_on_select", True):
            if can_upload:
                self.status.setText("Плюс выбран. Запускаю FTP-загрузку…")
                QTimer.singleShot(0, self.upload_plus)
            else:
                self.plus_drop.label.setText(f"{path.name} · сначала выбери минус")
                QMessageBox.warning(
                    self,
                    "Минус не выбран",
                    "Плюс выбран, но основной MP3-минус ещё не загружен. "
                    "Сначала перетащи минус, затем повтори плюс.",
                )

    def _ftp_password(self) -> str:
        cfg = self.config.get("plus_upload", {})
        secret_path = APP_ROOT / cfg.get("secret_file", "secrets.local.json")
        key = cfg.get("password_key", "ftp_password")
        if secret_path.is_file():
            try:
                value = clean(json.loads(secret_path.read_text(encoding="utf-8")).get(key))
                if value:
                    return value
            except Exception:
                pass

        password, ok = QInputDialog.getText(
            self,
            "FTP-пароль",
            "Пароль FTP для загрузки плюса:",
            QLineEdit.Password,
        )
        if not ok or not password:
            return ""

        remember = QMessageBox.question(
            self,
            "Запомнить пароль?",
            "Сохранить пароль только на этом компьютере в secrets.local.json?\n"
            "Файл исключён из Git.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if remember == QMessageBox.Yes:
            secret_path.write_text(
                json.dumps({key: password}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return password

    @staticmethod
    def _ftp_ensure_dir(ftp: ftplib.FTP, remote_dir: str):
        ftp.cwd("/")
        for part in [p for p in remote_dir.strip("/").split("/") if p]:
            try:
                ftp.cwd(part)
            except ftplib.error_perm:
                ftp.mkd(part)
                ftp.cwd(part)

    @staticmethod
    def _ftp_remote_exists(ftp: ftplib.FTP, remote_name: str):
        """Return True/False when the server can answer on the control channel, else None."""
        try:
            ftp.sendcmd(f"MLST {remote_name}")
            return True
        except ftplib.error_perm as exc:
            code = str(exc)[:3]
            if code == "550":
                return False
            if code in {"500", "501", "502", "504"}:
                pass
            else:
                raise

        try:
            ftp.voidcmd("TYPE I")
            size = ftp.size(remote_name)
            return size is not None
        except ftplib.error_perm as exc:
            code = str(exc)[:3]
            if code == "550":
                return False
            if code in {"500", "501", "502", "504"}:
                return None
            raise
        except Exception:
            return None

    @staticmethod
    def _ftp_remote_size(ftp: ftplib.FTP, remote_name: str):
        try:
            ftp.voidcmd("TYPE I")
            return ftp.size(remote_name)
        except ftplib.error_perm as exc:
            code = str(exc)[:3]
            if code in {"500", "501", "502", "504", "550"}:
                return None
            raise

    def upload_plus(self):
        if self._plus_upload_in_progress:
            return
        if not self.current_path or not self.current_path.is_file():
            QMessageBox.warning(
                self,
                "Минус не выбран",
                "Сначала перетащи основной MP3-минус. После загрузки плюса ссылка должна сразу записаться в его WOAS.",
            )
            return
        if not self.plus_path or not self.plus_path.is_file():
            QMessageBox.warning(self, "Плюс песни", "Сначала перетащи или выбери MP3-плюс.")
            return

        cfg = self.config.get("plus_upload", {})
        if not cfg.get("enabled"):
            QMessageBox.warning(self, "FTP", "FTP-загрузка выключена в config.json.")
            return

        password = self._ftp_password()
        if not password:
            return

        server = clean(cfg.get("server"))
        username = clean(cfg.get("username"))
        remote_dir = clean(cfg.get("remote_dir"))
        public_base = clean(cfg.get("public_base_url")).rstrip("/")
        port = int(cfg.get("port", 21))
        timeout = int(cfg.get("timeout_seconds", 60))
        passive = bool(cfg.get("passive", True))

        if not all([server, username, remote_dir, public_base]):
            QMessageBox.critical(self, "FTP", "Не заполнены FTP-настройки в config.json.")
            return

        remote_name = self.plus_path.name
        temp_name = f".__uploading__{remote_name}"
        ftp = ftplib.FTP()
        stage = "подключение к FTP"

        self._plus_upload_in_progress = True
        self.upload_plus_btn.setEnabled(False)
        self.plus_drop.label.setText(f"⏳ {remote_name} · загрузка…")
        self.status.setText("Подключаюсь к FTP…")
        QApplication.setOverrideCursor(Qt.WaitCursor)

        try:
            stage = "подключение к FTP"
            ftp.connect(server, port, timeout=timeout)

            stage = "вход на FTP"
            ftp.login(username, password)
            ftp.set_pasv(passive)

            stage = "переход в каталог плюсов"
            self._ftp_ensure_dir(ftp, remote_dir)

            stage = "проверка существующего файла"
            exists = self._ftp_remote_exists(ftp, remote_name)
            if exists is True:
                answer = QMessageBox.question(
                    self,
                    "Файл уже есть",
                    f"{remote_name}\n\nФайл уже существует на FTP. Перезаписать?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer != QMessageBox.Yes:
                    self.status.setText("FTP-загрузка отменена.")
                    return
            elif exists is None:
                answer = QMessageBox.question(
                    self,
                    "Не удалось проверить файл",
                    "FTP-сервер не смог надёжно проверить, существует ли файл с таким именем.\n\n"
                    "Продолжить? При совпадении имени существующий файл может быть заменён.",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer != QMessageBox.Yes:
                    self.status.setText("FTP-загрузка отменена.")
                    return

            # Clean up a stale temporary upload if one is left from an interrupted run.
            try:
                ftp.delete(temp_name)
            except ftplib.error_perm:
                pass

            stage = "загрузка файла"
            self.status.setText("Загружаю плюс на FTP…")
            with self.plus_path.open("rb") as source:
                ftp.storbinary(f"STOR {temp_name}", source, blocksize=256 * 1024)

            stage = "проверка размера загруженного файла"
            remote_size = self._ftp_remote_size(ftp, temp_name)
            local_size = self.plus_path.stat().st_size
            if remote_size is not None and remote_size != local_size:
                raise RuntimeError(
                    f"Размер временного файла на FTP не совпал: {remote_size} != {local_size}"
                )

            stage = "замена итогового файла"
            if exists is True:
                try:
                    ftp.delete(remote_name)
                except ftplib.error_perm as exc:
                    if str(exc)[:3] != "550":
                        raise

            try:
                ftp.rename(temp_name, remote_name)
            except ftplib.error_perm:
                # Some FTP servers do not allow RNTO over an existing target.
                if exists is None:
                    try:
                        ftp.delete(remote_name)
                        ftp.rename(temp_name, remote_name)
                    except Exception:
                        raise
                else:
                    raise

            stage = "финальная проверка"
            final_size = self._ftp_remote_size(ftp, remote_name)
            if final_size is not None and final_size != local_size:
                raise RuntimeError(
                    f"Размер итогового файла на FTP не совпал: {final_size} != {local_size}"
                )

            url = public_base + "/" + quote(remote_name)
            self.source_url.setText(url)

            stage = "запись ссылки в WOAS"
            self._save_plus_url_to_current_mp3(url)

            self.plus_drop.label.setText(f"✓ {remote_name} · загружен")
            self.status.setText("Плюс загружен; ссылка сразу сохранена в WOAS. Проверяю URL…")
            self.check_plus_url(True)

            if cfg.get("open_public_url_after_upload"):
                QDesktopServices.openUrl(QUrl(url))

        except Exception as exc:
            message = f"Этап: {stage}\n\n{type(exc).__name__}: {exc}"
            if "timed out" in str(exc).lower():
                message += (
                    "\n\nFTP-соединение оборвалось по таймауту. "
                    "Повторно использованное соединение после таймаута теперь не применяется."
                )
            self.plus_drop.label.setText(f"✕ {remote_name} · ошибка")
            QMessageBox.critical(self, "FTP-загрузка", message)
            self.status.setText(f"Ошибка FTP: {stage}.")
            try:
                if ftp.sock is not None:
                    ftp.delete(temp_name)
            except Exception:
                pass
        finally:
            self._plus_upload_in_progress = False
            try:
                ftp.close()
            except Exception:
                pass
            QApplication.restoreOverrideCursor()
            self.upload_plus_btn.setEnabled(
                bool(
                    self.current_path
                    and self.current_path.is_file()
                    and self.plus_path
                    and self.plus_path.is_file()
                )
            )

    def _save_plus_url_to_current_mp3(self, url: str):
        if not self.current_path or not self.current_path.is_file():
            raise RuntimeError("Текущий MP3-минус не найден для записи WOAS.")

        spec = {"kind": "url", "frame": "WOAS"}
        tags = load_tags(self.current_path)
        old = read_field(tags, spec)
        if old == url:
            return

        try:
            write_field(tags, spec, url)
            tags.save(self.current_path, v2_version=4)
            verify = load_tags(self.current_path)
            actual = read_field(verify, spec)
            if actual != url:
                raise RuntimeError(f"WOAS после записи отличается: {actual!r} != {url!r}")
            self._log_operation({
                "time": datetime.now().isoformat(timespec="seconds"),
                "status": "woas_saved_immediately",
                "file": str(self.current_path),
                "old": old,
                "new": url,
            })
        except Exception:
            try:
                rollback = load_tags(self.current_path)
                write_field(rollback, spec, old)
                rollback.save(self.current_path, v2_version=4)
            except Exception:
                pass
            raise

    def _set_plus_link_status(self, state: str, text: str):
        colors = {
            "idle": "#9ba6b2",
            "checking": "#f2c94c",
            "ok": "#63d69a",
            "error": "#ef6b6b",
        }
        self.plus_link_status.setText(text)
        self.plus_link_status.setStyleSheet(f"color: {colors.get(state, '#9ba6b2')};")

    def _mark_plus_url_dirty(self):
        self._set_plus_link_status("idle", "— ссылка не проверена")

    def check_plus_url(self, show_dialog: bool = True):
        url = self.source_url.text().strip()
        if not url:
            self._set_plus_link_status("error", "✕ ссылка не заполнена")
            if show_dialog:
                QMessageBox.warning(self, "Проверка ссылки", "Ссылка на плюс не заполнена.")
            return

        qurl = QUrl(url)
        if not qurl.isValid() or qurl.scheme().lower() not in {"http", "https"}:
            self._set_plus_link_status("error", "✕ некорректный URL")
            if show_dialog:
                QMessageBox.warning(self, "Проверка ссылки", f"Некорректный URL:\n{url}")
            return

        if self._link_check_reply is not None and self._link_check_reply.isRunning():
            self._link_check_reply.abort()

        request = QNetworkRequest(qurl)
        request.setRawHeader(b"User-Agent", b"Andrey-Repertoire-Link-Check/1.0")
        self._set_plus_link_status("checking", "… проверяю ссылку")

        reply = self.network_manager.head(request)
        self._link_check_reply = reply

        timeout_ms = int(self.config.get("plus_upload", {}).get("http_check_timeout_seconds", 10)) * 1000
        QTimer.singleShot(
            timeout_ms,
            lambda r=reply: r.abort() if r.isRunning() else None,
        )
        reply.finished.connect(
            lambda r=reply, dialog=show_dialog: self._finish_plus_url_check(r, dialog)
        )

    def _finish_plus_url_check(self, reply: QNetworkReply, show_dialog: bool):
        if reply is not self._link_check_reply:
            reply.deleteLater()
            return

        self._link_check_reply = None
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        error = reply.error()
        url = reply.url().toString()

        if error == QNetworkReply.NetworkError.NoError and status is not None and 200 <= int(status) < 400:
            self._set_plus_link_status("ok", f"✓ ссылка работает · HTTP {int(status)}")
            self.status.setText("Ссылка на плюс работает.")
            if show_dialog:
                QMessageBox.information(
                    self,
                    "Проверка ссылки",
                    f"Ссылка работает.\nHTTP {int(status)}\n\n{url}",
                )
        else:
            if error == QNetworkReply.NetworkError.OperationCanceledError:
                reason = "таймаут проверки"
            else:
                reason = reply.errorString() or "неизвестная ошибка"
            status_text = f"HTTP {int(status)} · " if status is not None else ""
            self._set_plus_link_status("error", f"✕ {status_text}{reason}")
            self.status.setText("Ссылка на плюс не прошла проверку.")
            if show_dialog:
                QMessageBox.critical(
                    self,
                    "Ссылка на плюс не работает",
                    f"{status_text}{reason}\n\n{url}",
                )

        reply.deleteLater()

    def open_plus_url(self):
        url = self.source_url.text().strip()
        if not url:
            QMessageBox.warning(self, "Ссылка на плюс", "Ссылка не заполнена.")
            return
        if not QDesktopServices.openUrl(QUrl(url)):
            QMessageBox.warning(self, "Ссылка на плюс", f"Не удалось открыть:\n{url}")

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
        self._set_tone(self.config["filename"].get("tone_default", ""))
        self._set_length(self.config["filename"].get("length_default", ""))
        self.invalid_fields.clear()
        self.unmapped_structured_tags.clear()
        self.tit1_unknown.clear()
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
        self.foobar_btn.setEnabled(False)
        self.refresh_analysis_btn.setEnabled(False)
        self._set_analysis_status(self.bpm_status_label, "idle", "— BPM не проверен")
        self._set_analysis_status(
            self.replaygain_status_label,
            "idle",
            "— ReplayGain не проверен",
        )
        self.plus_path = None
        self._plus_upload_in_progress = False
        self.plus_path_label.setText("Плюс не выбран")
        self.plus_drop.label.setText("Перетащи сюда плюс (MP3)")
        self.upload_plus_btn.setEnabled(False)
        self._set_plus_link_status("idle", "— ссылка не проверена")
        self.status.setText("Готов к загрузке MP3")


def run():
    app = QApplication(sys.argv)
    app.setApplicationName("Добавление минуса в репертуар")
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())
