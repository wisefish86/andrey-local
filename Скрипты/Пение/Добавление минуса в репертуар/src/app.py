from __future__ import annotations

import copy
import ftplib
import logging
import socket
import time
import uuid
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, quote_plus, unquote, urlsplit

from PySide6.QtCore import Qt, QSignalBlocker, Signal, QTimer, QThread
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
    QPlainTextEdit,
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

from _common.id3_io import (
    clean,
    disallowed_tag_keys,
    load_tags,
    prune_tags,
    read_field,
    read_text,
    read_url,
    write_field,
)
from _common.plus_storage import ftp_ensure_dir, slugify_remote_name

APP_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = APP_ROOT / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
_ftp_log = logging.getLogger("repertoire.plus_ftp")
if not _ftp_log.handlers:
    from logging.handlers import RotatingFileHandler
    _handler = RotatingFileHandler(LOG_DIR / "ftp_upload.log", maxBytes=2_000_000,
                                   backupCount=4, encoding="utf-8")
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(threadName)s %(message)s"))
    _ftp_log.addHandler(_handler)
    _ftp_log.setLevel(logging.INFO)

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
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(3)
        self.label = QLabel("Перетащи сюда MP3-минусовку")
        self.label.setMinimumHeight(24)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setObjectName("dropTitle")
        hint = QLabel("или нажми «Выбрать MP3»")
        hint.setMinimumHeight(22)
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
        self.base_title = title
        self.status = "none"
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.header = QToolButton()
        self.header.setCheckable(True)
        self.header.setChecked(expanded)
        self.header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.header.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.header.setObjectName("sectionHeader")
        self.header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.header.toggled.connect(self._toggle)

        self.body = QWidget()
        self.body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(8, 4, 8, 8)
        self.body_layout.setSpacing(10)
        self.body.setVisible(expanded)

        layout.addWidget(self.header)
        layout.addWidget(self.body)
        self.set_status("none")

    def _toggle(self, expanded: bool):
        self.header.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.body.setVisible(expanded)

    def set_status(self, status: str):
        self.status = status
        icons = {
            "none": "",
            "ok": "✓ ",
            "error": "✕ ",
            "warning": "⚠ ",
            "progress": "… ",
        }
        self.header.setText(icons.get(status, "") + self.base_title)
        self.header.setProperty("sectionStatus", status)
        self.header.style().unpolish(self.header)
        self.header.style().polish(self.header)

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



class PlusUploadWorker(QThread):
    """Send a local MP3 through a saved WinSCP session and verify the result."""
    detail = Signal(str)
    completed = Signal(str, str)
    failed = Signal(str)

    def __init__(self, path: Path, settings: dict, password: str = "", parent=None):
        super().__init__(parent)
        self.path = path
        self.settings = dict(settings)
        self.logger = logging.getLogger("repertoire.plus_ftp")

    @staticmethod
    def check_public_file(url: str, expected_size: int) -> str:
        from urllib.error import HTTPError, URLError
        from urllib.request import Request, urlopen
        request = Request(url, method="HEAD", headers={
            "User-Agent": "Andrey-Repertoire-Upload-Check/1.0",
            "Cache-Control": "no-cache",
        })
        try:
            with urlopen(request, timeout=10) as response:
                length = response.headers.get("Content-Length")
                if length is None:
                    return "uncertain"
                return "verified" if int(length) == expected_size else "uncertain"
        except HTTPError as exc:
            return "absent" if exc.code in (404, 410) else "uncertain"
        except (URLError, OSError, ValueError, TimeoutError):
            return "uncertain"

    @staticmethod
    def find_winscp(settings: dict):
        """Use JSON configuration; discover installed WinSCP as a fallback."""
        configured = clean(settings.get("winscp_executable"))
        if configured:
            path = Path(os.path.expandvars(os.path.expanduser(configured)))
            if not path.is_file():
                raise FileNotFoundError(
                    f"WinSCP.com не найден по пути из config.json: {path}")
            return path
        candidates = []
        for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if base:
                candidates.append(Path(base) / "WinSCP" / "WinSCP.com")
        try:
            import winreg
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(
                        hive, r"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\WinSCP.exe"
                    ) as key:
                        candidates.append(Path(winreg.QueryValueEx(key, "")[0]).with_name("WinSCP.com"))
                except OSError:
                    pass
        except ImportError:
            pass
        found = shutil.which("WinSCP.com")
        if found:
            candidates.append(Path(found))
        return next((p for p in candidates if p.is_file()), None)

    def run(self):
        import tempfile
        stage = None
        try:
            if os.name != "nt":
                raise RuntimeError("WinSCP доступен только в Windows.")
            winscp = self.find_winscp(self.settings)
            if not winscp:
                raise FileNotFoundError("WinSCP.com не найден. Проверь установку WinSCP.")
            name = slugify_remote_name(self.path, self.settings.get("slug", {}))
            url = clean(self.settings["public_base_url"]).rstrip("/") + "/" + quote(name)
            size = self.path.stat().st_size
            state = self.check_public_file(url, size)
            if state == "verified":
                self.completed.emit(url, "existing")
                return
            if state != "absent":
                raise RuntimeError("Нельзя подтвердить отсутствие целевого файла на сервере.")
            # Temporary directory prevents clobbering another file next to the MP3.
            stage_dir = Path(tempfile.mkdtemp(prefix="andrey-plus-", dir=str(self.path.parent)))
            stage = stage_dir / name
            shutil.copy2(self.path, stage)
            if stage.stat().st_size != size:
                raise RuntimeError("Временная копия отличается по размеру.")
            session = self.settings.get("winscp_session", "andreway.ru (audio - plus)")
            remote_dir = clean(self.settings["remote_dir"])
            # WinSCP scripting requires its own quoting, not shell quoting.
            def quote_arg(value):
                return '"' + str(value).replace('"', '""') + '"'
            commands = [
                "option batch abort",
                "option confirm off",
                "open " + quote_arg(session),
                "cd " + quote_arg(remote_dir),
                "put -nopreservetime -resumesupport=off " + quote_arg(stage),
                "exit",
            ]
            self.detail.emit("WinSCP: загружаю " + name)
            portable_ini = winscp.with_name("WinSCP.ini")
            ini_args = ["/ini=" + str(portable_ini)] if portable_ini.is_file() else []
            # /command is decoded with the console code page on older WinSCP.
            # A UTF-8 BOM script preserves Cyrillic paths and session names.
            script_path = stage_dir / "winscp-upload.txt"
            script_path.write_text(chr(10).join(commands) + chr(10), encoding="utf-8-sig")
            result = subprocess.run(
                [str(winscp), *ini_args, "/loglevel=0",
                 "/script=" + str(script_path)],
                capture_output=True, text=True, errors="replace",
                timeout=max(90, int(self.settings.get("winscp_timeout_seconds", 300))),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode:
                raise RuntimeError("WinSCP завершился с ошибкой. " + (result.stderr or result.stdout)[-1000:])
            if self.check_public_file(url, size) != "verified":
                raise RuntimeError("WinSCP завершился, но размер файла по HTTP не подтверждён.")
            stage.unlink()
            script_path.unlink()
            stage_dir.rmdir()
            self.completed.emit(url, "uploaded")
        except Exception as exc:
            self.logger.exception("WinSCP upload failed")
            self.failed.emit(f"{type(exc).__name__}: {exc}. Исходный MP3 не затронут; копия сохранена: {stage}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        self.current_path: Path | None = None
        self._has_sylt = False
        self.filename_manual = False
        self.folder_manual = False
        self.title_manual = False
        self._last_version_value = ""
        self.controls: dict[str, QWidget] = {}
        self.field_labels: dict[str, QLabel] = {}
        self.sections: dict[str, CollapsibleSection] = {}
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
        section = CollapsibleSection(
            cfg.get("label", section_id),
            bool(cfg.get("expanded", False)),
        )
        self.sections[section_id] = section
        return section

    def _set_section_status(self, section_id: str, status: str):
        section = self.sections.get(section_id)
        if section is not None:
            section.set_status(status)

    def _build_ui(self):
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(8)

        top = QHBoxLayout()
        self.drop = DropFrame()
        self.drop.setMinimumHeight(78)
        self.drop.setMaximumHeight(92)
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

        language_field = self.field_defs.get("language")
        if language_field is None:
            raise RuntimeError("В config.json отсутствует поле language")
        self.language_control = self._make_field_control(language_field)
        self.language_label = QLabel(language_field["label"])
        self.controls["language"] = self.language_control
        self.field_labels["language"] = self.language_label

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
        self.reset_title_btn = QPushButton("По шаблону")
        reset_title = self.reset_title_btn
        reset_title.clicked.connect(self.reset_title_template)
        # Both Title actions belong to the same cell. The old SYLT button
        # occupied row 3 / column 5, overlapping the trim checkbox spanning
        # columns 4-5; it was painted underneath that checkbox.
        title_actions = QWidget()
        title_actions_layout = QVBoxLayout(title_actions)
        title_actions_layout.setContentsMargins(0, 0, 0, 0)
        title_actions_layout.setSpacing(4)
        title_actions_layout.addWidget(reset_title)
        self.sylt_fix_btn = QPushButton("Исправить знак синхронного текста")
        self.sylt_fix_btn.setVisible(False)
        self.sylt_fix_btn.clicked.connect(self.fix_sylt_marker)
        title_actions_layout.addWidget(self.sylt_fix_btn)
        grid.addWidget(title_actions, 2, 5)

        grid.addWidget(QLabel("Тональность"), 3, 0)
        grid.addWidget(self.tone, 3, 1)
        grid.addWidget(QLabel("F / S"), 3, 2)
        grid.addWidget(self.length_version, 3, 3)

        trim_cfg = self.config.get("title", {}).get("flags", {}).get("trim", {})
        self.trim_needed = QCheckBox(
            f"{clean(trim_cfg.get('symbol')) or '✂️'} {clean(trim_cfg.get('label')) or 'Укоротить'}"
        )
        self.trim_needed.setChecked(bool(trim_cfg.get("default", False)))
        self.trim_needed.setToolTip("Добавить ножницы перед Title, чтобы отметить минус на укорочение")
        grid.addWidget(self.trim_needed, 3, 4, 1, 2)

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

        grid.addWidget(self.language_label, 6, 0)
        grid.addWidget(self.language_control, 6, 1, 1, 2)

        grid.addWidget(QLabel("Файл минуса"), 7, 0)
        grid.addWidget(self.filename, 7, 1, 1, 4)
        reset_name = QPushButton("По шаблону")
        reset_name.clicked.connect(self.reset_filename_template)
        grid.addWidget(reset_name, 7, 5)

        grid.addWidget(QLabel("Папка песни"), 8, 0)
        grid.addWidget(self.folder_name, 8, 1, 1, 4)
        reset_folder = QPushButton("По шаблону")
        reset_folder.clicked.connect(self.reset_folder_template)
        grid.addWidget(reset_folder, 8, 5)

        self.rename_folder = QCheckBox("Переименовать папку песни по шаблону")
        self.move_folder = QCheckBox("Перенести папку песни в основной репертуар")
        grid.addWidget(self.rename_folder, 9, 1, 1, 2)
        grid.addWidget(self.move_folder, 9, 3, 1, 3)

        self.target_label = QLabel("")
        self.target_label.setObjectName("muted")
        grid.addWidget(self.target_label, 10, 1, 1, 5)

        song_section.add_widget(song_widget)
        body_layout.addWidget(song_section)

        # 2. Теги и подбор
        tags_section = self._make_section("tags")
        sections = QHBoxLayout()
        perf = QGroupBox("Выступление")
        perf_form = QFormLayout(perf)
        search = QGroupBox("Поиск и сайт")
        search_form = QFormLayout(search)

        self.album_fixed = QLineEdit(self.config.get("fixed_tags", {}).get("TALB", "минусы"))
        self.album_fixed.setReadOnly(True)
        self.album_fixed.setProperty("fixed", True)
        self.album_fixed.setToolTip("Фиксированный тег ALBUM; меняется только в config.json")
        search_form.addRow("Альбом", self.album_fixed)

        self.year = QLineEdit()
        self.year.setMaximumWidth(120)
        year_row = QHBoxLayout()
        year_row.setContentsMargins(0, 0, 0, 0)
        year_row.setSpacing(7)
        year_row.addWidget(self.year)
        year_search = QPushButton("🔎 Найти год в Google")
        year_search.setToolTip("Искать дату выхода песни по исполнителю и названию")
        year_search.clicked.connect(self.search_year_google)
        year_row.addWidget(year_search)
        year_row.addStretch(1)
        search_form.addRow("Год", year_row)

        for field in self.config["fields"]:
            if field["id"] == "language":
                continue
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

        # 3. Текст песни
        lyrics_section = self._make_section("lyrics")
        lyrics_widget = QWidget()
        lyrics_layout = QVBoxLayout(lyrics_widget)
        lyrics_layout.setContentsMargins(0, 0, 0, 0)
        lyrics_layout.setSpacing(7)

        lyrics_top = QHBoxLayout()
        paste_lyrics_btn = QPushButton("Вставить из буфера")
        paste_lyrics_btn.clicked.connect(self.paste_lyrics)
        clear_lyrics_btn = QPushButton("Очистить")
        clear_lyrics_btn.clicked.connect(self.clear_lyrics)
        self.lyrics_count_label = QLabel("0 строк · 0 символов")
        self.lyrics_count_label.setObjectName("muted")
        lyrics_top.addWidget(paste_lyrics_btn)
        lyrics_top.addWidget(clear_lyrics_btn)
        lyrics_top.addStretch(1)
        lyrics_top.addWidget(self.lyrics_count_label)

        lyrics_cfg = self.config.get("lyrics", {})
        self.lyrics_edit = QPlainTextEdit()
        self.lyrics_edit.setPlaceholderText("Вставь сюда обычный текст песни…")
        self.lyrics_edit.setMinimumHeight(int(lyrics_cfg.get("min_height", 280)))
        self.lyrics_edit.setMaximumHeight(int(lyrics_cfg.get("max_height", 420)))
        self.lyrics_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.lyrics_edit.textChanged.connect(self._lyrics_changed)

        lyrics_hint = QLabel("Обычная лирика USLT — редактируется и сохраняется.")
        lyrics_hint.setObjectName("muted")

        self.sylt_status_label = QLabel("Синхронная лирика: не загружена")
        self.sylt_status_label.setObjectName("muted")
        self.sylt_edit = QPlainTextEdit()
        self.sylt_edit.setReadOnly(True)
        self.sylt_edit.setPlaceholderText("Синхронная лирика отсутствует.")
        self.sylt_edit.setMinimumHeight(int(lyrics_cfg.get("synced_min_height", 220)))
        self.sylt_edit.setMaximumHeight(int(lyrics_cfg.get("synced_max_height", 340)))
        self.sylt_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        sylt_hint = QLabel("SYLT показывается отдельно только для просмотра; программа его не изменяет.")
        sylt_hint.setObjectName("muted")

        lyrics_layout.addLayout(lyrics_top)
        lyrics_layout.addWidget(self.lyrics_edit)
        lyrics_layout.addWidget(lyrics_hint)
        if bool(lyrics_cfg.get("show_synced", True)):
            lyrics_layout.addWidget(self.sylt_status_label)
            lyrics_layout.addWidget(self.sylt_edit)
            lyrics_layout.addWidget(sylt_hint)
        lyrics_section.add_widget(lyrics_widget)
        body_layout.addWidget(lyrics_section)

        # 4. Анализ аудио
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

        # 5. Плюс песни
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
        self.delete_plus_btn = QPushButton("🗑 Удалить с FTP")
        self.delete_plus_btn.setToolTip("Удалить файл, указанный в текущем WOAS, с FTP-сервера")
        self.delete_plus_btn.clicked.connect(self.delete_plus_from_ftp)
        self.delete_plus_btn.setEnabled(False)
        plus_buttons.addWidget(choose_plus)
        plus_buttons.addWidget(self.upload_plus_btn)
        plus_buttons.addWidget(self.delete_plus_btn)
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

        # 6. Файлы песни
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

        # 7. Инструменты репертуара
        tools_section = self._make_section("tools")
        tools_widget = QWidget()
        tools_layout = QGridLayout(tools_widget)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        tools_layout.setHorizontalSpacing(10)
        tools_layout.setVerticalSpacing(8)

        def tool_button(text: str, tooltip: str, callback):
            button = QPushButton(text)
            button.setToolTip(tooltip)
            button.clicked.connect(callback)
            return button

        tools_layout.addWidget(
            tool_button(
                "↻ Пересканировать для Singer Andrey",
                "Перечитать все MP3-минусовки и создать repertoire.json",
                lambda: self.launch_repertoire_tool("site_rescan"),
            ),
            0, 0,
        )
        tools_layout.addWidget(
            tool_button(
                "📄 Открыть repertoire.json",
                "Открыть последний JSON-экспорт репертуара",
                self.open_site_export,
            ),
            0, 1,
        )
        tools_layout.addWidget(
            tool_button(
                "🔎 Миграция плюсов — проверка",
                "Dry-run: ничего не загружает и не меняет",
                lambda: self.launch_repertoire_tool("migrate_plus_check"),
            ),
            1, 0,
        )
        tools_layout.addWidget(
            tool_button(
                "⚠ Проблемные папки",
                "Открыть последний список папок без плюса или с несколькими кандидатами",
                self.open_migration_problems,
            ),
            1, 1,
        )
        tools_layout.addWidget(
            tool_button(
                "⬆ Миграция плюсов — применить",
                "Загрузить однозначные плюсы на FTP и записать WOAS",
                lambda: self.launch_repertoire_tool("migrate_plus_apply"),
            ),
            2, 0,
        )
        tools_layout.addWidget(
            tool_button(
                "🧾 Импорт тегов из CSV",
                "Открыть универсальный импорт тегов",
                lambda: self.launch_repertoire_tool("import_tags"),
            ),
            2, 1,
        )
        tools_layout.addWidget(
            tool_button(
                "📝 Исправление лирики",
                "Открыть инструмент проверки/исправления встроенной лирики",
                lambda: self.launch_repertoire_tool("fix_lyrics"),
            ),
            3, 0,
        )
        tools_layout.addWidget(
            tool_button(
                "📂 Распределение минусов",
                "Запустить распределение минусов по папкам для Syncthing",
                lambda: self.launch_repertoire_tool("distribute_minuses"),
            ),
            3, 1,
        )
        tools_layout.addWidget(
            tool_button(
                "🎵 Подготовить текущий MP3 для фонотеки",
                "Передать текущий MP3 в старый инструмент подготовки фонотеки",
                lambda: self.launch_repertoire_tool("prepare_phonotheque", pass_current_file=True),
            ),
            4, 0,
        )
        tools_layout.addWidget(
            tool_button(
                "📁 Открыть все инструменты",
                "Открыть папку со всеми сервисными утилитами, включая нормализацию аудио/видео",
                self.open_tools_folder,
            ),
            4, 1,
        )
        tools_layout.addWidget(
            tool_button(
                "ⓘ Справка по программе",
                "Открыть встроенную справку основной программы",
                self.show_help,
            ),
            5, 0,
        )
        tools_layout.addWidget(
            tool_button(
                "📖 Справка по инструментам",
                "Открыть README контейнера инструментов",
                lambda: self.open_configured_file("tools_help", "Справка по инструментам"),
            ),
            5, 1,
        )

        tools_layout.addWidget(
            tool_button(
                "🔎 Для телефона — проверка",
                "Показать план копирования песен по ID3-статусам без изменений на диске",
                lambda: self.launch_repertoire_tool("phone_sync_preview"),
            ),
            6, 0,
        )
        tools_layout.addWidget(
            tool_button(
                "📱 Для телефона — обновить",
                "Скопировать плоские папки песен в Syncthing; убрать лишь старые управляемые копии",
                lambda: self.launch_repertoire_tool("phone_sync_apply"),
            ),
            6, 1,
        )

        tools_hint = QLabel(
            "Все редкие операции над минусами собраны здесь и физически лежат "
            "в подпапках «Инструменты репертуара»."
        )
        tools_hint.setWordWrap(True)
        tools_hint.setObjectName("muted")
        tools_layout.addWidget(tools_hint, 7, 0, 1, 2)
        tools_section.add_widget(tools_widget)
        body_layout.addWidget(tools_section)

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
        self.trim_needed.toggled.connect(self._trim_changed)
        self.display_title.textEdited.connect(lambda _t: setattr(self, "title_manual", True))
        self.display_title.textChanged.connect(self._refresh_title_indicators)
        self.filename.textEdited.connect(lambda _t: setattr(self, "filename_manual", True))
        self.folder_name.textEdited.connect(lambda _t: setattr(self, "folder_manual", True))
        self.folder_name.textEdited.connect(lambda _t: self._update_target_preview())
        self.year.editingFinished.connect(self._suggest_era)
        self.move_folder.toggled.connect(self._update_target_preview)
        self.rename_folder.toggled.connect(self._update_target_preview)
        language_control = self.controls.get("language")
        if isinstance(language_control, MultiSelectButton):
            language_control.changed.connect(self._language_changed)
        elif isinstance(language_control, QComboBox):
            language_control.currentIndexChanged.connect(
                lambda _index: self._language_changed()
            )

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
            QLineEdit, QComboBox, QToolButton, QPlainTextEdit { background: #20252c; border: 1px solid #3d4652; border-radius: 6px; padding: 7px; min-height: 20px; }
            QLineEdit[fixed="true"] { color: #8c96a3; background: #191d22; border-color: #303741; }
            QToolButton { text-align: center; }
            QLabel[attention="true"] { color: #f2c94c; }
            QComboBox[invalid="true"], QToolButton[invalid="true"] { border: 2px solid #d85353; background: #342226; }
            QCheckBox { spacing: 8px; }
            QCheckBox::indicator { width: 17px; height: 17px; border: 2px solid #71869d; border-radius: 4px; background: #11161c; }
            QCheckBox::indicator:hover { border-color: #a7c2dc; background: #18212b; }
            QCheckBox::indicator:checked { border-color: #8bc5ff; background: #4b8fce; }
            QCheckBox::indicator:disabled { border-color: #46515d; background: #171b20; }
            QPushButton { background: #272d35; border: 1px solid #414a56; border-radius: 6px; padding: 8px 12px; }
            QPushButton:hover, QToolButton:hover { background: #313945; }
            QPushButton#primary { background: #276749; border-color: #3c8a68; font-weight: 700; padding: 10px 18px; }
            QPushButton#primary:hover { background: #32805c; }
            QFrame#dropFrame, QFrame#plusDropFrame { border: 2px dashed #536170; border-radius: 10px; padding: 8px; background: #1b2026; }
            QToolButton#sectionHeader { background: #20252c; border: 1px solid #353b44; border-radius: 7px; padding: 10px 12px; font-weight: 700; text-align: left; }
            QToolButton#sectionHeader[sectionStatus="ok"] { color: #63d69a; }
            QToolButton#sectionHeader[sectionStatus="error"] { color: #ef6b6b; }
            QToolButton#sectionHeader[sectionStatus="warning"] { color: #f2c94c; }
            QToolButton#sectionHeader[sectionStatus="progress"] { color: #f2c94c; }
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
        self.title_manual = False
        self.display_title.clear()

        existing_artist = self._first(read_text(tags, "TPE1"))
        existing_name = self._first(read_text(tags, "MVNM"))
        existing_title = self._first(read_text(tags, "TIT2"))
        trim_symbol = clean(
            self.config.get("title", {}).get("flags", {}).get("trim", {}).get("symbol")
        ) or "✂️"
        with QSignalBlocker(self.trim_needed):
            self.trim_needed.setChecked(existing_title.lstrip().startswith(trim_symbol))
        inferred = self._parse_filename(path)

        parse_cfg = self.config.get("filename", {}).get("source_parse", {})
        prefer_filename = bool(parse_cfg.get("prefer_filename_artist_title", True))
        if prefer_filename and inferred.get("artist_title_recognized"):
            self.artist.setText(inferred["artist"] or existing_artist)
            self.clean_title.setText(inferred["clean_title"] or existing_name)
        else:
            self.artist.setText(existing_artist or inferred["artist"])
            self.clean_title.setText(existing_name or inferred["clean_title"])

        self.year.setText(self._first(read_text(tags, "TDRC")))
        self.source_url.setText(read_url(tags, "WOAS"))
        self._set_plus_link_status("idle", "— ссылка не проверена")
        self._update_plus_delete_enabled()

        lyrics_spec = dict(self.config.get("lyrics", {}).get(
            "storage",
            {"kind": "lyrics", "frame": "USLT", "language": "eng", "description": ""},
        ))
        with QSignalBlocker(self.lyrics_edit):
            self.lyrics_edit.setPlainText(read_field(tags, lyrics_spec))
        self._load_sylt_view(tags)
        self._update_lyrics_meta()

        self._set_version(inferred["version"] or self._extract_version(existing_title))
        tone_from_title = self._extract_tone(existing_title)
        length_from_title = self._extract_length(existing_title)
        self._set_tone(inferred["tone"] or tone_from_title or self.config["filename"].get("tone_default", ""))
        self._set_length(inferred["length"] or length_from_title)
        self.version_info.setText(inferred["version_info"])

        # TIT1 may contain separate ID3 values or one semicolon-delimited string.
        tit1_values = [
            part.strip()
            for raw in read_text(tags, "TIT1")
            for part in raw.split(";")
            if part.strip()
        ]
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

        self.title_manual = bool(existing_title)
        self.display_title.setText(existing_title if existing_title else self.generated_title())

        self.filename_manual = True
        self.folder_manual = True
        self.filename.setText(path.name)
        self.folder_name.setText(path.parent.name)
        self._refresh_title_indicators()

        library_root = Path(self.config["paths"]["library_root"])
        staging_raw = clean(self.config.get("paths", {}).get("staging_root"))
        staging_root = Path(staging_raw) if staging_raw else None
        current_folder = path.parent
        is_library_root = self._same_path(current_folder, library_root)
        is_staging_root = bool(staging_root and self._same_path(current_folder, staging_root))
        already_final_folder = (
            not is_staging_root
            and not is_library_root
            and self._same_path(current_folder.parent, library_root)
        )

        if is_library_root:
            self.rename_folder.setChecked(False)
            self.rename_folder.setEnabled(False)
            self.rename_folder.setToolTip("Корень основного репертуара нельзя переименовывать.")
            self.move_folder.setChecked(False)
            self.move_folder.setEnabled(False)
            self.move_folder.setToolTip("Корень основного репертуара нельзя переносить.")
        elif is_staging_root:
            self.rename_folder.setChecked(False)
            self.rename_folder.setEnabled(False)
            self.rename_folder.setToolTip(
                "MP3 лежит прямо в служебной папке. Она никогда не переименовывается."
            )
            self.move_folder.setEnabled(True)
            self.move_folder.setChecked(
                bool(self.config["folder"].get("move_to_library_default", True))
            )
            self.move_folder.setToolTip(
                "При переносе будет создана отдельная папка песни; "
                "служебная папка останется на месте."
            )
        else:
            self.rename_folder.setEnabled(True)
            self.rename_folder.setToolTip(
                "Если снять галочку, текущее имя папки будет сохранено."
            )
            self.rename_folder.setChecked(
                bool(self.config["folder"].get("rename_default", True))
            )
            self.move_folder.setEnabled(not already_final_folder)
            self.move_folder.setChecked(
                not already_final_folder
                and bool(self.config["folder"].get("move_to_library_default", True))
            )
            self.move_folder.setToolTip(
                "Если снять галочку, папка останется на текущем месте."
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
            if len(source_values) > 1:
                invalid.append("несколько значений: " + ", ".join(source_values))
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
        if self.tit1_unknown:
            self.warning_label.setStyleSheet("color: #f0b45d;")
            self.warning_label.setText(
                "Лишние значения TIT1 будут удалены при сохранении: "
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

        artist_title_recognized = bool(canonical_sep)
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
                    artist_title_recognized = True
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

        # A source note may have hidden version/tone/F-S immediately before it.
        if not length:
            lm = re.search(r"\s*\[(F|S)\]\s*$", title_part, re.IGNORECASE)
            if lm:
                length = lm.group(1).upper()
                title_part = title_part[:lm.start()].strip()

        if not tone:
            legacy_zero = re.search(r"\s*\[0\]\s*$", title_part)
            if legacy_zero:
                title_part = title_part[:legacy_zero.start()].strip()
            tm = re.search(r"\s*\[(N|[+-]?[1-3])\]\s*$", title_part, re.IGNORECASE)
            if tm:
                tone = tm.group(1).upper() if tm.group(1).upper() == "N" else tm.group(1)
                title_part = title_part[:tm.start()].strip()

        if not version:
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

        return {
            "clean_title": title_part.strip(),
            "artist": artist.strip(),
            "version": version,
            "tone": tone,
            "length": length,
            "version_info": version_info,
            "artist_title_recognized": artist_title_recognized,
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
        if self._last_version_value:
            candidates.add(self._last_version_value)
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
        self._last_version_value = self._version_value()
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

    def _version_changed(self, _text: str = ""):
        self._apply_version_to_name_field()
        self._last_version_value = self._version_value()
        # Version is part of the naming template: rebuild Title immediately.
        self.title_manual = False
        self.display_title.setText(self.generated_title())
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
        language_symbol = self._title_symbol()
        parts = []
        trim_cfg = self.config.get("title", {}).get("flags", {}).get("trim", {})
        if self.trim_needed.isChecked():
            parts.append(clean(trim_cfg.get("symbol")) or "✂️")
        if language_symbol:
            parts.append(language_symbol)
        prefix = " ".join(parts)
        marker = "`" if self._has_sylt else ""
        return f"{prefix} {marker}{name}{self._tone_suffix()}{self._length_suffix()}".strip()

    def _trim_changed(self, _checked: bool):
        self.title_manual = False
        self.display_title.setText(self.generated_title())

    def _sylt_marker_present(self, value: str) -> bool:
        return bool(re.match(r"^.*?[⚪🔴][^\w]*`", value))

    def _refresh_title_indicators(self, *_args):
        if not hasattr(self, "reset_title_btn"):
            return
        current = self.display_title.text()
        different = current != self.generated_title()
        self.reset_title_btn.setStyleSheet("background-color: #8057c8; color: white; font-weight: bold;" if different else "")
        self.reset_title_btn.setToolTip("Название отличается от шаблона" if different else "Название соответствует шаблону")
        mismatch = bool(self.current_path) and (self._sylt_marker_present(current) != self._has_sylt)
        self.sylt_fix_btn.setVisible(mismatch)
        if mismatch:
            self.sylt_fix_btn.setText("⚠ Добавить `" if self._has_sylt else "⚠ Убрать `")
            self.sylt_fix_btn.setStyleSheet("background-color: #a56b16; color: white; font-weight: bold;")

    def fix_sylt_marker(self):
        value = self.display_title.text()
        if self._has_sylt:
            value = re.sub(r"^((?:.*?[⚪🔴])\s*)(?!`)", r"\1`", value, count=1)
        else:
            value = re.sub(r"^((?:.*?[⚪🔴])\s*)`", r"\1", value, count=1)
        self.title_manual = True
        self.display_title.setText(value)

    def reset_title_template(self):
        self.title_manual = False
        self.display_title.setText(self.generated_title())

    def _language_changed(self):
        if not self.title_manual:
            self.display_title.setText(self.generated_title())

    def generated_filename(self) -> str:
        title = self.clean_title.text().strip()
        artist = self.artist.text().strip()
        return (
            f"{title}{self._tone_suffix()}{self._length_suffix()} "
            f"_____ {artist}{self._info_suffix()}.mp3"
        )

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

    def search_year_google(self):
        artist = self.artist.text().strip()
        name = self._strip_version_suffix(self.clean_title.text())
        template = clean(
            self.config.get("search", {}).get(
                "year_google_query",
                "{artist} {name} дата выхода песни год релиза",
            )
        )
        query = template.format(artist=artist, name=name).strip()
        if not query:
            query = f"{artist} {name} дата выхода песни год релиза".strip()
        url = "https://www.google.com/search?q=" + quote_plus(query)
        if not QDesktopServices.openUrl(QUrl(url)):
            QMessageBox.warning(self, "Поиск года", "Не удалось открыть браузер.")

    @staticmethod
    def _same_path(left: Path, right: Path) -> bool:
        try:
            return left.resolve() == right.resolve()
        except Exception:
            return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(
                os.path.abspath(str(right))
            )

    def _folder_action_plan(self) -> dict[str, Any]:
        if not self.current_path:
            return {"mode": "none", "target": None, "source": None}

        current_folder = self.current_path.parent
        library_root = Path(self.config["paths"]["library_root"])
        staging_raw = clean(self.config.get("paths", {}).get("staging_root"))
        staging_root = Path(staging_raw) if staging_raw else None
        rename_requested = self.rename_folder.isChecked()
        move_requested = self.move_folder.isChecked()
        requested_name = self.folder_name.text().strip()

        if self._same_path(current_folder, library_root):
            if rename_requested or move_requested:
                raise ValueError("Корень основного репертуара нельзя переименовывать или переносить.")
            return {"mode": "none", "target": None, "source": current_folder}

        if staging_root and self._same_path(current_folder, staging_root):
            if rename_requested:
                raise ValueError(
                    "Служебную папку «- - Добавляю в репертуар» нельзя переименовывать."
                )
            if not move_requested:
                return {"mode": "none", "target": None, "source": current_folder}
            if not requested_name:
                raise ValueError("Имя папки песни пустое.")
            target = library_root / requested_name
            return {
                "mode": "move_file_from_staging",
                "target": target,
                "source": current_folder,
            }

        if move_requested:
            final_name = requested_name if rename_requested else current_folder.name
            if not final_name:
                raise ValueError("Имя папки песни пустое.")
            target = library_root / final_name
            if self._same_path(target, current_folder):
                return {"mode": "none", "target": None, "source": current_folder}
            return {
                "mode": "move_and_rename_folder" if rename_requested else "move_folder",
                "target": target,
                "source": current_folder,
            }

        if rename_requested:
            if not requested_name:
                raise ValueError("Имя папки песни пустое.")
            target = current_folder.with_name(requested_name)
            if self._same_path(target, current_folder):
                return {"mode": "none", "target": None, "source": current_folder}
            return {
                "mode": "rename_folder",
                "target": target,
                "source": current_folder,
            }

        return {"mode": "none", "target": None, "source": current_folder}

    def _update_target_preview(self):
        if not self.current_path:
            self.target_label.setText("")
            return
        try:
            action = self._folder_action_plan()
        except Exception as exc:
            self.target_label.setText(f"⚠ {exc}")
            return

        mode = action["mode"]
        target = action["target"]
        if mode == "none":
            self.target_label.setText(f"Папка: без изменений · {self.current_path.parent}")
        elif mode == "rename_folder":
            self.target_label.setText(f"Папка: только переименование → {target}")
        elif mode == "move_folder":
            self.target_label.setText(f"Папка: только перенос, имя сохранится → {target}")
        elif mode == "move_and_rename_folder":
            self.target_label.setText(f"Папка: перенос + переименование → {target}")
        elif mode == "move_file_from_staging":
            self.target_label.setText(
                f"Staging останется на месте; текущий MP3 → новая папка {target}"
            )

    def _is_under(self, child: Path, parent: Path) -> bool:
        try:
            child.resolve().relative_to(parent.resolve())
            return True
        except Exception:
            return False

    def _build_desired_tit1(self) -> list[str]:
        values = []
        for field in self.config["fields"]:
            if field["storage"]["kind"] != "tit1_group":
                continue
            values.extend(self._get_control_values(field, self.controls[field["id"]]))
        return list(dict.fromkeys(v for v in values if v))

    def _validate(self) -> tuple[Path, dict[str, Any], Path]:
        if not self.current_path or not self.current_path.is_file():
            raise ValueError("Исходный MP3 не найден.")
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
        action = self._folder_action_plan()
        folder_target = action.get("target")

        if action["mode"] in {
            "rename_folder",
            "move_and_rename_folder",
            "move_file_from_staging",
        }:
            folder_name = self.folder_name.text().strip()
            if INVALID_WIN_CHARS.search(folder_name) or folder_name.endswith((" ", ".")):
                raise ValueError("В имени папки есть запрещённые для Windows символы.")

        if (
            folder_target
            and not self._same_path(folder_target, current_folder)
            and folder_target.exists()
        ):
            raise FileExistsError(f"Папка уже существует: {folder_target}")
        return dest_file, action, current_folder

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

        lyrics_spec = dict(self.config.get("lyrics", {}).get(
            "storage",
            {"kind": "lyrics", "frame": "USLT", "language": "eng", "description": ""},
        ))
        lyrics_desired = self.lyrics_edit.toPlainText().strip()
        lyrics_current = read_field(tags, lyrics_spec)
        if lyrics_current != lyrics_desired:
            plan.append(("Текст песни", lyrics_spec, lyrics_current, lyrics_desired))

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
        removed_frames: list[str] = []
        original_tags_snapshot = None
        original_path = self.current_path
        working_path = original_path

        try:
            dest_file, folder_action, original_folder = self._validate()
            folder_target = folder_action.get("target")
            tags = load_tags(original_path)
            original_tags_snapshot = copy.deepcopy(tags)
            plan = self._make_plan(tags)

            self._log_operation({
                "time": datetime.now().isoformat(timespec="seconds"),
                "status": "planned",
                "source": str(original_path),
                "file_target": str(dest_file),
                "folder_target": str(folder_target) if folder_target else "",
                "folder_action": folder_action.get("mode", "none"),
                "rename_folder_checked": self.rename_folder.isChecked(),
                "move_folder_checked": self.move_folder.isChecked(),
                "changes": [{"label": x[0], "old": x[2], "new": x[3]} for x in plan],
            })

            for _label, spec, _old, desired in plan:
                write_field(tags, spec, desired)

            cleanup_cfg = dict(self.config.get("id3_cleanup", {}))
            if cleanup_cfg.get("enabled", False):
                removed_frames = prune_tags(tags, cleanup_cfg)

            tags.save(original_path, v2_version=4)
            tags_written = True

            verify = load_tags(original_path)
            for label, spec, _old, desired in plan:
                actual = read_field(verify, spec)
                if actual != desired:
                    raise RuntimeError(
                        f"Проверка тега «{label}» не прошла: {actual!r} != {desired!r}"
                    )

            if cleanup_cfg.get("enabled", False):
                unexpected = disallowed_tag_keys(verify, cleanup_cfg)
                if unexpected:
                    raise RuntimeError(
                        "После очистки остались запрещённые ID3-кадры: "
                        + ", ".join(unexpected)
                    )

            if dest_file != original_path:
                working_path = original_path.rename(dest_file)

            folder_mode = folder_action.get("mode", "none")
            if folder_mode == "move_file_from_staging":
                folder_target.mkdir(parents=False, exist_ok=False)
                target_file = folder_target / working_path.name
                working_path = Path(shutil.move(str(working_path), str(target_file)))
            elif (
                folder_mode in {"rename_folder", "move_folder", "move_and_rename_folder"}
                and folder_target
                and not self._same_path(folder_target, original_folder)
            ):
                moved_folder = Path(shutil.move(str(original_folder), str(folder_target)))
                working_path = moved_folder / working_path.name

            self.current_path = working_path
            self.path_label.setText(str(working_path))
            self.drop.label.setText(working_path.name)
            self._log_operation({
                "time": datetime.now().isoformat(timespec="seconds"),
                "status": "success",
                "result": str(working_path),
                "removed_id3_frames": removed_frames,
            })

            cleanup_text = (
                f"\nУдалено лишних ID3-кадров: {len(removed_frames)}."
                if removed_frames
                else ""
            )
            QMessageBox.information(
                self,
                "Готово",
                f"Теги сохранены и проверены.{cleanup_text}\n\n{working_path}",
            )
            self.status.setText("Готово. Файл сохранён, проверен и очищен.")
            self.load_file(str(working_path))

        except Exception as exc:
            rollback_note = ""
            if tags_written and original_tags_snapshot is not None:
                candidates = [working_path, original_path]
                rollback_path = next((p for p in candidates if p and p.exists()), None)
                if rollback_path:
                    try:
                        original_tags_snapshot.save(rollback_path, v2_version=4)
                        rollback_note = (
                            "\n\nИсходный полный набор ID3-тегов восстановлен."
                        )
                    except Exception as rollback_exc:
                        rollback_note = (
                            "\n\nНе удалось автоматически восстановить исходные ID3: "
                            f"{rollback_exc}"
                        )

            try:
                self._log_operation({
                    "time": datetime.now().isoformat(timespec="seconds"),
                    "status": "error",
                    "error": str(exc),
                    "file": str(working_path or original_path),
                    "removed_id3_frames": removed_frames,
                })
            except Exception:
                pass

            QMessageBox.critical(self, "Ошибка", str(exc) + rollback_note)
            self.status.setText("Ошибка. Автоматическая обработка остановлена.")

    @staticmethod
    def _format_sylt_timestamp(value: int, time_format: int = 2) -> str:
        if int(time_format) == 1:
            return f"[frame {max(0, int(value))}]"
        total = max(0, int(value))
        minutes, rest = divmod(total, 60000)
        seconds, millis = divmod(rest, 1000)
        return f"[{minutes:02d}:{seconds:02d}.{millis:03d}]"

    def _load_sylt_view(self, tags):
        frames = list(tags.getall("SYLT")) if hasattr(tags, "getall") else []
        self._has_sylt = bool(frames)

        if not frames:
            self.sylt_status_label.setText("Синхронная лирика: отсутствует")
            self.sylt_edit.setPlainText("Синхронная лирика отсутствует.")
            self._refresh_title_indicators()
            return

        blocks = []
        total_lines = 0
        for index, frame in enumerate(frames, start=1):
            rows = []
            for item in getattr(frame, "text", []) or []:
                try:
                    lyric_text, timestamp = item
                except Exception:
                    continue
                rows.append(
                    (
                        f"{self._format_sylt_timestamp(timestamp, getattr(frame, 'format', 2))} "
                        f"{str(lyric_text).strip()}"
                    ).rstrip()
                )
            total_lines += len(rows)
            if len(frames) > 1:
                lang = clean(getattr(frame, "lang", ""))
                desc = clean(getattr(frame, "desc", ""))
                meta = " · ".join(x for x in (lang, desc) if x)
                blocks.append(
                    f"--- SYLT {index}{' · ' + meta if meta else ''} ---"
                )
            blocks.extend(rows)
            if index < len(frames):
                blocks.append("")

        self.sylt_status_label.setText(
            f"Синхронная лирика: {len(frames)} дорожка(и) · {total_lines} строк"
        )
        self.sylt_edit.setPlainText("\n".join(blocks).strip())
        self._refresh_title_indicators()

    def paste_lyrics(self):
        text = QApplication.clipboard().text()
        if text:
            self.lyrics_edit.setPlainText(text)

    def clear_lyrics(self):
        self.lyrics_edit.clear()

    def _lyrics_changed(self):
        self._update_lyrics_meta()

    def _update_lyrics_meta(self):
        text = self.lyrics_edit.toPlainText()
        stripped = text.strip()
        lines = len(text.splitlines()) if stripped else 0
        chars = len(text)
        self.lyrics_count_label.setText(f"{lines} строк · {chars} символов")
        self._set_section_status(
            "lyrics",
            "ok" if stripped or bool(getattr(self, "_has_sylt", False)) else "none",
        )

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

        analysis_cfg = self.config.get("audio_analysis", {})
        program_id = clean(analysis_cfg.get("program_id")) or "foobar2000"
        program_cfg = self.config.get("programs", {}).get(program_id, {})
        label = clean(program_cfg.get("label")) or program_id
        exe = Path(clean(program_cfg.get("path")))

        if not clean(program_cfg.get("path")) or not exe.is_file():
            QMessageBox.critical(
                self,
                f"{label} не найден",
                "Не найден внешний анализатор по адресу:\n"
                f"{exe if clean(program_cfg.get('path')) else 'путь не задан'}\n\n"
                f"Измени config.json → programs.{program_id}.path.",
            )
            return

        try:
            subprocess.Popen([str(exe), str(self.current_path)])
            self.status.setText(f"Текущий минус открыт в {label}.")
        except Exception as exc:
            QMessageBox.critical(self, label, f"Не удалось открыть файл:\n{exc}")

    def refresh_audio_analysis(self, show_message: bool = False):
        if not self.current_path or not self.current_path.is_file():
            self._set_section_status("audio_analysis", "none")
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

            self._set_section_status(
                "audio_analysis",
                "ok" if bpm and gain and peak else "none",
            )

            if show_message:
                self.status.setText("BPM и ReplayGain перечитаны из MP3.")
        except Exception as exc:
            self._set_section_status("audio_analysis", "error")
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
        ftp_ensure_dir(ftp, remote_dir)

    def _slugify_remote_name(self, path: Path) -> str:
        cfg = self.config.get("plus_upload", {}).get("slug", {})
        return slugify_remote_name(path, cfg)

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
            QMessageBox.warning(self, "Минус не выбран", "Сначала выбери MP3-минус.")
            return
        if not self.plus_path or not self.plus_path.is_file():
            QMessageBox.warning(self, "Плюс не выбран", "Сначала выбери MP3-плюс.")
            return
        cfg = self.config.get("plus_upload", {})
        if not cfg.get("enabled") or not clean(cfg.get("public_base_url")):
            QMessageBox.warning(self, "FTP", "Не настроен URL загрузки плюсов.")
            return
        self._plus_upload_in_progress = True
        self._upload_target_mp3 = self.current_path
        self._upload_target_plus = self.plus_path
        self._plus_worker = PlusUploadWorker(self.plus_path, cfg, parent=self)
        self._plus_worker.detail.connect(self._on_plus_upload_detail)
        self._plus_worker.completed.connect(self._on_plus_upload_completed)
        self._plus_worker.failed.connect(self._on_plus_upload_failed)
        self._plus_worker.finished.connect(self._on_plus_upload_finished)
        self.upload_plus_btn.setEnabled(False)
        self.plus_drop.label.setText("Загружаю через WinSCP…")
        self._plus_worker.start()

    def _on_plus_upload_progress(self, sent: int, total: int):
        percent = round(sent * 100 / max(total, 1))
        self.plus_drop.label.setText(f"⬆ FTP: {percent}% ({sent:,}/{total:,} байт)")
        self.status.setText(f"Загрузка плюса: {percent}%")

    def _on_plus_upload_detail(self, message: str):
        self.status.setText(message)

    def _on_plus_upload_completed(self, url: str, outcome: str):
        # UI state can change during a background transfer. Never write WOAS to another song.
        if (self.current_path != self._upload_target_mp3
                or self.plus_path != self._upload_target_plus):
            self.status.setText("FTP завершён, но выбран другой минус. WOAS не изменён.")
            return
        try:
            self._save_plus_url_to_current_mp3(url)
        except Exception as exc:
            logging.getLogger("repertoire.plus_ftp").exception("WOAS save failed")
            self._on_plus_upload_failed(f"FTP успешен, но WOAS не записан: {exc}")
            return
        self.source_url.setText(url)
        self._update_plus_delete_enabled()
        self.plus_drop.label.setText("✓ Плюс на FTP · WOAS сохранён")
        self.status.setText("Плюс уже был на FTP; WOAS сохранён." if outcome == "existing"
                            else "Плюс загружен; WOAS сохранён. Проверяю ссылку…")
        self.check_plus_url(True)
        if self.config.get("plus_upload", {}).get("open_public_url_after_upload"):
            QDesktopServices.openUrl(QUrl(url))

    def _on_plus_upload_failed(self, message: str):
        self.plus_drop.label.setText("✕ FTP: ошибка (подробности в логе)")
        self.status.setText("FTP-загрузка не завершена")
        QMessageBox.critical(self, "FTP-загрузка", message)

    def _on_plus_upload_finished(self):
        self._plus_upload_in_progress = False
        self.upload_plus_btn.setEnabled(bool(
            self.current_path and self.current_path.is_file()
            and self.plus_path and self.plus_path.is_file()))
        self._plus_worker = None

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
        section_state = {
            "idle": "none",
            "checking": "progress",
            "ok": "ok",
            "error": "error",
        }.get(state, "none")
        self._set_section_status("plus", section_state)

    def _update_plus_delete_enabled(self):
        enabled = bool(
            self.config.get("plus_upload", {}).get("allow_delete", False)
            and self.current_path
            and self.current_path.is_file()
            and self.source_url.text().strip()
        )
        self.delete_plus_btn.setEnabled(enabled)

    def _mark_plus_url_dirty(self):
        self._set_plus_link_status("idle", "— ссылка не проверена")
        self._update_plus_delete_enabled()

    def _remote_name_from_public_url(self, url: str) -> str:
        cfg = self.config.get("plus_upload", {})
        public_base = clean(cfg.get("public_base_url")).rstrip("/")
        if not public_base:
            raise ValueError("Не задан public_base_url в config.json.")

        base = urlsplit(public_base)
        target = urlsplit(url)
        if target.scheme.casefold() != base.scheme.casefold() or target.netloc.casefold() != base.netloc.casefold():
            raise ValueError("Ссылка ведёт не на настроенный сервер плюсов.")

        base_path = base.path.rstrip("/") + "/"
        if not target.path.startswith(base_path):
            raise ValueError("Ссылка находится вне настроенного каталога плюсов.")

        remote_name = unquote(target.path[len(base_path):]).strip()
        if not remote_name or "/" in remote_name or "\\" in remote_name or remote_name in {".", ".."}:
            raise ValueError("Не удалось безопасно определить имя файла на FTP.")
        return remote_name

    def delete_plus_from_ftp(self):
        if not self.current_path or not self.current_path.is_file():
            QMessageBox.warning(self, "Плюс песни", "Сначала выбери основной MP3-минус.")
            return

        url = self.source_url.text().strip()
        if not url:
            QMessageBox.warning(self, "Плюс песни", "В WOAS нет ссылки на плюс.")
            return

        try:
            remote_name = self._remote_name_from_public_url(url)
        except Exception as exc:
            QMessageBox.critical(self, "Удаление с FTP", str(exc))
            return

        answer = QMessageBox.question(
            self,
            "Удалить плюс с FTP?",
            f"Файл будет удалён без корзины:\n\n{remote_name}\n\n{url}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        cfg = self.config.get("plus_upload", {})
        password = self._ftp_password()
        if not password:
            return

        ftp = ftplib.FTP()
        stage = "подключение к FTP"
        remote_deleted = False
        QApplication.setOverrideCursor(Qt.WaitCursor)

        try:
            stage = "подключение к FTP"
            ftp.connect(
                clean(cfg.get("server")),
                int(cfg.get("port", 21)),
                timeout=int(cfg.get("timeout_seconds", 60)),
            )

            stage = "вход на FTP"
            ftp.login(clean(cfg.get("username")), password)
            ftp.set_pasv(bool(cfg.get("passive", True)))

            stage = "переход в каталог плюсов"
            self._ftp_ensure_dir(ftp, clean(cfg.get("remote_dir")))

            stage = "удаление файла"
            ftp.delete(remote_name)
            remote_deleted = True

            stage = "очистка WOAS"
            self._save_plus_url_to_current_mp3("")
            self.source_url.clear()
            self._update_plus_delete_enabled()
            self._set_plus_link_status("idle", "— файл удалён с FTP")
            self.plus_drop.label.setText(
                f"{remote_name} · удалён с FTP"
                if not self.plus_path
                else f"{self.plus_path.name} · локальный файл выбран"
            )
            self.status.setText("Плюс удалён с FTP; WOAS очищен.")
            QMessageBox.information(
                self,
                "Плюс удалён",
                "Файл удалён с FTP, ссылка очищена в текущем MP3.",
            )

        except Exception as exc:
            extra = (
                "\n\nФайл уже удалён с FTP, но не удалось очистить WOAS."
                if remote_deleted
                else ""
            )
            QMessageBox.critical(
                self,
                "Удаление с FTP",
                f"Этап: {stage}\n\n{type(exc).__name__}: {exc}{extra}",
            )
        finally:
            try:
                ftp.close()
            except Exception:
                pass
            QApplication.restoreOverrideCursor()

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

        try:
            self._remote_name_from_public_url(url)
        except ValueError as exc:
            self._set_plus_link_status("error", "✕ ссылка не на сервере плюсов")
            self.status.setText("Ссылка на плюс не прошла проверку.")
            if show_dialog:
                QMessageBox.warning(self, "Проверка ссылки", str(exc))
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

        try:
            self._remote_name_from_public_url(url)
            destination_ok = True
        except ValueError:
            destination_ok = False

        if destination_ok and error == QNetworkReply.NetworkError.NoError and status is not None and 200 <= int(status) < 300:
            self._set_plus_link_status("ok", f"✓ ссылка работает · HTTP {int(status)}")
            self.status.setText("Ссылка на плюс работает.")
            if show_dialog:
                QMessageBox.information(
                    self,
                    "Проверка ссылки",
                    f"Ссылка работает.\nHTTP {int(status)}\n\n{url}",
                )
        else:
            if not destination_ok:
                reason = "ссылка не на сервере плюсов"
            elif error == QNetworkReply.NetworkError.OperationCanceledError:
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

    def launch_repertoire_tool(self, tool_id: str, pass_current_file: bool = False):
        rel = clean(self.config.get("tools", {}).get(tool_id))
        if not rel:
            QMessageBox.warning(
                self,
                "Инструменты репертуара",
                f"Для {tool_id} не задан путь в config.json → tools.",
            )
            return

        path = APP_ROOT / Path(rel)
        if not path.is_file():
            QMessageBox.critical(
                self,
                "Инструменты репертуара",
                f"Инструмент не найден:\n{path}",
            )
            return

        if pass_current_file and (not self.current_path or not self.current_path.is_file()):
            QMessageBox.warning(
                self,
                "Инструменты репертуара",
                "Сначала выбери текущий MP3.",
            )
            return

        try:
            if os.name == "nt":
                if pass_current_file:
                    subprocess.Popen(
                        ["cmd.exe", "/c", str(path), str(self.current_path)],
                        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
                    )
                else:
                    os.startfile(str(path))
            else:
                args = [str(path)]
                if pass_current_file:
                    args.append(str(self.current_path))
                subprocess.Popen(args)
            self.status.setText(f"Запущено: {path.name}")
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Инструменты репертуара",
                f"Не удалось запустить {path.name}:\n{exc}",
            )

    def open_configured_file(self, tool_id: str, title: str):
        rel = clean(self.config.get("tools", {}).get(tool_id))
        path = APP_ROOT / Path(rel) if rel else None
        if not path or not path.is_file():
            QMessageBox.information(
                self,
                title,
                f"Файл ещё не создан или не найден:\n{path or rel}",
            )
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.warning(self, title, f"Не удалось открыть:\n{path}")

    def open_migration_problems(self):
        self.open_configured_file("migration_problems", "Проблемные папки")

    def open_tools_folder(self):
        path = APP_ROOT / "Инструменты репертуара"
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.warning(
                self,
                "Инструменты репертуара",
                f"Не удалось открыть:\n{path}",
            )

    def open_site_export(self):
        rel = clean(
            self.config.get("site_export", {}).get(
                "output_file",
                "data/site/repertoire.json",
            )
        )
        path = APP_ROOT / Path(rel)
        if not path.is_file():
            QMessageBox.information(
                self,
                "repertoire.json",
                "Экспорт ещё не создан. Сначала нажми "
                "«Пересканировать для Singer Andrey».",
            )
            return

        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        except Exception as exc:
            QMessageBox.critical(
                self,
                "repertoire.json",
                f"Не удалось открыть файл:\n{exc}",
            )

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
                stem = re.sub(r"\s*" + re.escape(marker) + r"\s*", " ", stem).strip()
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
        self.lyrics_edit.clear()
        self._has_sylt = False
        self.sylt_status_label.setText("Синхронная лирика: не загружена")
        self.sylt_fix_btn.setVisible(False)
        self.sylt_edit.clear()
        self._set_section_status("lyrics", "none")
        with QSignalBlocker(self.trim_needed):
            self.trim_needed.setChecked(
                bool(self.config.get("title", {}).get("flags", {}).get("trim", {}).get("default", False))
            )
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
        self._set_section_status("audio_analysis", "none")
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
        self.delete_plus_btn.setEnabled(False)
        self._set_plus_link_status("idle", "— ссылка не проверена")
        self.status.setText("Готов к загрузке MP3")


def run():
    app = QApplication(sys.argv)
    app.setApplicationName("Добавление минуса в репертуар")
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())
