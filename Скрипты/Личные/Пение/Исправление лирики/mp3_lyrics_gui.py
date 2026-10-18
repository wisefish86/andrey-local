from __future__ import annotations

import re
import subprocess
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from mutagen.id3 import ID3, ID3NoHeaderError, SYLT, USLT
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QComboBox, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QSplitter, QStyle, QVBoxLayout, QWidget,
)


DEFAULT_ROOT = r"D:\YandexDisk\Проекты\Пение\Минусы\1. Основной репертуар"
MARK = "֎"
LRC_RE = re.compile(r"^\s*\[(\d+):(\d{1,2})(?:[.:](\d{1,3}))?]\s*(.*)$")


@dataclass
class Entry:
    path: Path
    status: str
    detail: str = ""
    sylt_frames: list = field(default_factory=list)
    uslt_frames: list = field(default_factory=list)
    sylt_lines: list[tuple[int, str]] | None = None
    uslt_lines: list[tuple[int, str]] | None = None


def normalized(lines):
    return [(int(ms), text.replace("\r", "").strip()) for ms, text in lines]


def sylt_lines(frame: SYLT):
    return normalized([(stamp, text) for text, stamp in frame.text])


def parse_lrc(text: str):
    result, bad_nonempty = [], False
    for raw in text.replace("\r", "").split("\n"):
        if not raw.strip():
            continue
        m = LRC_RE.match(raw)
        if not m:
            bad_nonempty = True
            continue
        minute, second, fraction, lyric = m.groups()
        if int(second) > 59:
            bad_nonempty = True
            continue
        if fraction is None:
            millis = 0
        elif len(fraction) == 1:
            millis = int(fraction) * 100
        elif len(fraction) == 2:
            millis = int(fraction) * 10
        else:
            millis = int(fraction)
        result.append((int(minute) * 60000 + int(second) * 1000 + millis, lyric.strip()))
    return normalized(result) if result and not bad_nonempty else None


def has_lrc_timestamps(text: str):
    """Есть ли хотя бы одна поддерживаемая временная метка в квадратных скобках."""
    for raw in text.replace("\r", "").split("\n"):
        m = LRC_RE.match(raw)
        if m and int(m.group(2)) <= 59:
            return True
    return False


def has_duplicate_empty_zero(lines):
    """Две и более пустые метки [00:00.000] считаются ошибочной заглушкой."""
    return bool(lines) and sum(1 for ms, text in lines if ms == 0 and not text.strip()) >= 2


def to_lrc(lines):
    out = []
    for ms, text in lines:
        minute, rest = divmod(int(ms), 60000)
        second, milli = divmod(rest, 1000)
        out.append(f"[{minute:02d}:{second:02d}.{milli:03d}]{text}")
    return "\n".join(out)


def unique_nonempty(values):
    unique = []
    for value in values:
        if value and value not in unique:
            unique.append(value)
    return unique


def inspect_file(path: Path):
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        return Entry(path, "Нет SYLT", "В файле нет ID3")
    sylts = tags.getall("SYLT")
    uslts = [x for x in tags.getall("USLT") if x.text.strip()]
    if not sylts:
        timed_uslts = [x for x in uslts if has_lrc_timestamps(x.text)]
        if not timed_uslts:
            detail = "Обычная лирика без таймкодов — это нормально" if uslts else "Лирики нет"
            return Entry(path, "Нет SYLT", detail, sylts, uslts)
        parsed = unique_nonempty([parse_lrc(x.text) for x in timed_uslts])
        invalid = any(parse_lrc(x.text) is None for x in timed_uslts)
        if any(has_duplicate_empty_zero(parse_lrc(x.text)) for x in timed_uslts):
            shown = parsed[0] if len(parsed) == 1 else None
            return Entry(path, "Конфликт", "USLT содержит повторяющуюся пустую метку [00:00.000]", sylts, uslts, None, shown)
        if invalid or len(parsed) != 1:
            return Entry(path, "Конфликт", "В USLT есть таймкоды, но LRC неоднозначен или содержит ошибки; SYLT отсутствует", sylts, uslts)
        return Entry(path, "Конфликт", "В USLT есть валидные таймкоды, но SYLT отсутствует", sylts, uslts, None, parsed[0])

    s_values = unique_nonempty([sylt_lines(x) for x in sylts if x.text])
    u_values = unique_nonempty([parse_lrc(x.text) for x in uslts])
    invalid_uslt = any(parse_lrc(x.text) is None for x in uslts)
    bad_sylt_zero = any(has_duplicate_empty_zero(sylt_lines(x)) for x in sylts if x.text)
    bad_uslt_zero = any(has_duplicate_empty_zero(parse_lrc(x.text)) for x in uslts)
    if bad_sylt_zero or bad_uslt_zero:
        sides = " и ".join(name for name, bad in (("SYLT", bad_sylt_zero), ("USLT", bad_uslt_zero)) if bad)
        return Entry(
            path, "Конфликт", f"{sides} содержит повторяющуюся пустую метку [00:00.000]",
            sylts, uslts,
            s_values[0] if len(s_values) == 1 else None,
            u_values[0] if len(u_values) == 1 else None,
        )
    if len(s_values) != 1:
        return Entry(path, "Конфликт", "Несколько разных или пустых SYLT", sylts, uslts)
    s = s_values[0]
    if not uslts:
        return Entry(path, "Без USLT", "Можно исправить автоматически", sylts, uslts, s, None)
    if invalid_uslt:
        return Entry(path, "Конфликт", "USLT не является валидным LRC", sylts, uslts, s, None)
    if len(u_values) != 1:
        return Entry(path, "Конфликт", "Несколько разных USLT", sylts, uslts, s, None)
    u = u_values[0]
    if s == u:
        return Entry(path, "Совпадает", sylt_frames=sylts, uslt_frames=uslts, sylt_lines=s, uslt_lines=u)
    text_diff = [x[1] for x in s] != [x[1] for x in u]
    time_diff = [x[0] for x in s] != [x[0] for x in u]
    kinds = " и ".join(x for x, yes in (("текст", text_diff), ("тайминг", time_diff)) if yes)
    return Entry(path, "Конфликт", f"Различается: {kinds}", sylts, uslts, s, u)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Проверка лирики MP3 — SYLT ↔ USLT")
        self.resize(1250, 820)
        self.entries = []
        self.current = None

        root = QWidget(); self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        row = QHBoxLayout()
        self.root_edit = QPlainTextEdit(DEFAULT_ROOT); self.root_edit.setFixedHeight(42)
        choose = QPushButton("Выбрать папку…"); choose.clicked.connect(self.choose_root)
        scan = QPushButton("Сканировать"); scan.clicked.connect(self.scan)
        self.only_mark = QCheckBox(f"Только MP3 с {MARK}"); self.only_mark.setChecked(True)
        row.addWidget(QLabel("Папка:")); row.addWidget(self.root_edit, 1); row.addWidget(choose); row.addWidget(scan); row.addWidget(self.only_mark)
        outer.addLayout(row)

        self.summary = QLabel("Файлы ещё не проверены"); outer.addWidget(self.summary)

        tools = QHBoxLayout()
        tools.addWidget(QLabel("Показать:"))
        self.status_filter = QComboBox()
        for title, value in (("Все", ""), ("Конфликты", "Конфликт"), ("Без USLT", "Без USLT"),
                             ("Нет SYLT", "Нет SYLT"), ("Совпадает", "Совпадает"), ("Ошибки чтения", "Ошибка")):
            self.status_filter.addItem(title, value)
        self.status_filter.currentIndexChanged.connect(self.refresh_list)
        self.search_edit = QLineEdit(); self.search_edit.setPlaceholderText("Поиск по имени или пути…")
        self.search_edit.textChanged.connect(self.refresh_list)
        tools.addWidget(self.status_filter); tools.addWidget(self.search_edit, 1)
        tools.addWidget(QLabel("Сортировка: по типу ошибки → имени файла"))
        outer.addLayout(tools)

        split = QSplitter(Qt.Horizontal)
        self.list = QListWidget(); self.list.currentItemChanged.connect(self.select_item)
        self.list.itemDoubleClicked.connect(lambda _item: self.open_folder()); split.addWidget(self.list)
        right = QWidget(); rv = QVBoxLayout(right)
        self.file_label = QLabel("Выберите результат"); self.file_label.setWordWrap(True); rv.addWidget(self.file_label)
        panels = QSplitter(Qt.Horizontal)
        self.sylt_view = QPlainTextEdit(); self.sylt_view.setPlaceholderText("SYLT в формате LRC — поле можно редактировать")
        self.uslt_view = QPlainTextEdit(); self.uslt_view.setPlaceholderText("USLT / LRC — поле можно редактировать")
        panels.addWidget(self.wrap_with_actions(
            "Оставить SYLT", self.keep_sylt, "Сохранить только SYLT", lambda: self.save_edited_tag("sylt"),
            self.sylt_view, "#1976d2", "#1565c0", "sylt"))
        panels.addWidget(self.wrap_with_actions(
            "Оставить USLT", self.keep_uslt, "Сохранить только USLT", lambda: self.save_edited_tag("uslt"),
            self.uslt_view, "#00897b", "#00796b", "uslt"))
        self.sylt_view.textChanged.connect(self.update_action_buttons)
        self.uslt_view.textChanged.connect(self.update_action_buttons)
        self.update_action_buttons()
        rv.addWidget(panels, 1)
        actions = QHBoxLayout()
        for title, fn in (("Открыть папку", self.open_folder), ("Пропустить", self.next_conflict), ("Следующий конфликт", self.next_conflict), ("Исправить безопасные случаи", self.fix_safe)):
            b = QPushButton(title); b.clicked.connect(fn); actions.addWidget(b)
        rv.addLayout(actions); split.addWidget(right); split.setSizes([390, 850]); outer.addWidget(split, 1)
        outer.addWidget(QLabel("Журнал:")); self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumHeight(150); outer.addWidget(self.log)

    def wrap_with_actions(self, title, action, save_title, save_action, widget, color, hover_color, side):
        w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(0, 0, 0, 0)
        button = QPushButton(title)
        button.setMinimumHeight(36)
        button.setStyleSheet(
            f"QPushButton {{ background-color: {color}; color: white; font-weight: 600; "
            "border: none; border-radius: 5px; padding: 7px 16px; } "
            f"QPushButton:hover {{ background-color: {hover_color}; }} "
            f"QPushButton:pressed {{ background-color: {hover_color}; }} "
            "QPushButton:disabled { background-color: #bdbdbd; color: #eeeeee; }"
        )
        button.clicked.connect(action)
        save_button = QPushButton(save_title)
        save_button.setText("")
        save_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        save_button.setToolTip(save_title)
        save_button.setFixedSize(38, 36)
        save_button.clicked.connect(save_action)
        setattr(self, f"keep_{side}_button", button)
        setattr(self, f"save_{side}_button", save_button)
        buttons = QHBoxLayout(); buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addWidget(button); buttons.addWidget(save_button)
        l.addLayout(buttons); l.addWidget(widget)
        return w

    def update_action_buttons(self):
        if hasattr(self, "keep_sylt_button"):
            self.keep_sylt_button.setEnabled(bool(self.sylt_view.toPlainText().strip()))
        if hasattr(self, "keep_uslt_button"):
            self.keep_uslt_button.setEnabled(bool(self.uslt_view.toPlainText().strip()))

    def choose_root(self):
        p = QFileDialog.getExistingDirectory(self, "Выберите корневую папку", self.root_edit.toPlainText().strip())
        if p: self.root_edit.setPlainText(p)

    def add_log(self, text):
        self.log.appendPlainText(f"{datetime.now():%H:%M:%S}  {text}")

    def scan(self):
        root = Path(self.root_edit.toPlainText().strip())
        if not root.is_dir():
            QMessageBox.warning(self, "Ошибка", "Указанная папка не существует."); return
        self.entries.clear(); self.list.clear(); self.current = None
        files = sorted(root.rglob("*.mp3"))
        if self.only_mark.isChecked(): files = [p for p in files if MARK in p.name]
        self.add_log(f"Начато сканирование: {len(files)} файлов")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for p in files:
                try: self.entries.append(inspect_file(p))
                except Exception as exc:
                    self.entries.append(Entry(p, "Ошибка", str(exc))); self.add_log(f"ОШИБКА {p}: {exc}")
                QApplication.processEvents()
        finally: QApplication.restoreOverrideCursor()
        self.refresh_list(); self.add_log("Сканирование завершено")

    def refresh_list(self, select_path=None):
        self.list.clear(); counts = {}
        for e in self.entries:
            counts[e.status] = counts.get(e.status, 0) + 1
        status_order = {"Конфликт": 0, "Ошибка": 1, "Без USLT": 2, "Нет SYLT": 3, "Совпадает": 4}
        selected_status = self.status_filter.currentData() if hasattr(self, "status_filter") else ""
        query = self.search_edit.text().strip().casefold() if hasattr(self, "search_edit") else ""
        visible = [e for e in self.entries
                   if (not selected_status or e.status == selected_status)
                   and (not query or query in str(e.path).casefold())]
        visible.sort(key=lambda e: (status_order.get(e.status, 99), e.detail.casefold(), e.path.name.casefold(), str(e.path).casefold()))
        for e in visible:
            item = QListWidgetItem(f"[{e.status}] {e.path.name}"); item.setData(Qt.UserRole, e)
            if e.status in ("Конфликт", "Ошибка"): item.setForeground(QColor("#c62828"))
            elif e.status == "Без USLT": item.setForeground(QColor("#b26a00"))
            self.list.addItem(item)
            if select_path == e.path: self.list.setCurrentItem(item)
        order = ("Совпадает", "Без USLT", "Конфликт", "Нет SYLT", "Ошибка")
        shown = f"   Показано: {len(visible)}" if len(visible) != len(self.entries) else ""
        self.summary.setText("Проверено: " + str(len(self.entries)) + shown + "   " + "   ".join(f"{k}: {counts.get(k, 0)}" for k in order))

    def select_item(self, item, _old=None):
        if not item: return
        e = item.data(Qt.UserRole); self.current = e
        self.file_label.setText(f"{e.path}\nСтатус: {e.status}. {e.detail}")
        self.sylt_view.setPlainText(to_lrc(e.sylt_lines) if e.sylt_lines else self.raw_sylts(e))
        self.uslt_view.setPlainText(to_lrc(e.uslt_lines) if e.uslt_lines else self.raw_uslts(e))
        self.highlight(e)

    def raw_sylts(self, e):
        return "\n\n--- SYLT ---\n".join(to_lrc(sylt_lines(x)) for x in e.sylt_frames)

    def raw_uslts(self, e):
        return "\n\n--- USLT ---\n".join(x.text for x in e.uslt_frames)

    def highlight(self, e):
        if e.sylt_lines is None or e.uslt_lines is None: return
        text_color = QColor("#ffb8b8")
        time_color = QColor("#ffe69a")
        max_len = max(len(e.sylt_lines), len(e.uslt_lines))
        for i in range(max_len):
            if i >= len(e.sylt_lines):
                self.mark_range(self.uslt_view, i, 0, -1, text_color); continue
            if i >= len(e.uslt_lines):
                self.mark_range(self.sylt_view, i, 0, -1, text_color); continue
            s_time, s_text = e.sylt_lines[i]
            u_time, u_text = e.uslt_lines[i]
            s_line = self.sylt_view.document().findBlockByNumber(i).text()
            u_line = self.uslt_view.document().findBlockByNumber(i).text()
            s_text_start = s_line.find("]") + 1
            u_text_start = u_line.find("]") + 1
            if s_time != u_time:
                self.mark_range(self.sylt_view, i, 0, s_text_start, time_color)
                self.mark_range(self.uslt_view, i, 0, u_text_start, time_color)
            if s_text != u_text:
                matcher = SequenceMatcher(None, s_text, u_text)
                for operation, a1, a2, b1, b2 in matcher.get_opcodes():
                    if operation == "equal": continue
                    if a2 > a1:
                        self.mark_range(self.sylt_view, i, s_text_start + a1, a2 - a1, text_color)
                    if b2 > b1:
                        self.mark_range(self.uslt_view, i, u_text_start + b1, b2 - b1, text_color)

    @staticmethod
    def mark_range(view, line_number, start, length, color):
        block = view.document().findBlockByNumber(line_number)
        if not block.isValid(): return
        available = len(block.text())
        if length < 0: length = available - start
        if length <= 0: return
        cursor = QTextCursor(block)
        cursor.setPosition(block.position() + min(start, available))
        cursor.setPosition(block.position() + min(start + length, available), QTextCursor.KeepAnchor)
        fmt = QTextCharFormat(); fmt.setBackground(color)
        cursor.mergeCharFormat(fmt)

    def write_choice(self, mode, use_editor=True):
        e = self.current
        if not e: QMessageBox.information(self, "Нет файла", "Сначала выберите файл."); return False
        if use_editor:
            source_text = self.sylt_view.toPlainText() if mode == "sylt" else self.uslt_view.toPlainText()
            source_lines = parse_lrc(source_text)
        else:
            source_lines = e.sylt_lines if mode == "sylt" else e.uslt_lines
        if not source_lines or has_duplicate_empty_zero(source_lines):
            side = "левом поле SYLT" if mode == "sylt" else "правом поле USLT"
            extra = "\nДве пустые метки [00:00.000] также считаются ошибкой." if source_lines else ""
            QMessageBox.warning(
                self, "Некорректные таймкоды",
                f"В {side} должен быть непустой корректный LRC.\n"
                f"Поддерживаются метки [m:ss], [mm:ss.xx] и [m:ss.xxx].{extra}"
            ); return False
        try:
            tags = ID3(e.path)
            if mode == "sylt":
                # Редактируемая левая панель становится источником для обоих кадров.
                tags.delall("SYLT")
                tags.delall("USLT")
                tags.add(SYLT(encoding=3, lang="eng", format=2, type=1, desc="Edited lyrics", text=[(text, ms) for ms, text in source_lines]))
                tags.add(USLT(encoding=3, lang="eng", desc="LRC from SYLT", text=to_lrc(source_lines)))
            else:
                # Редактируемая правая панель становится источником для обоих кадров.
                tags.delall("SYLT")
                tags.delall("USLT")
                tags.add(SYLT(encoding=3, lang="eng", format=2, type=1, desc="Lyrics from USLT", text=[(text, ms) for ms, text in source_lines]))
                tags.add(USLT(encoding=3, lang="eng", desc="Edited LRC", text=to_lrc(source_lines)))
            tags.save(e.path, v2_version=3)
            self.add_log(f"Записано: {e.path}")
            replacement = inspect_file(e.path)
            self.entries[self.entries.index(e)] = replacement; self.current = replacement
            if self.status_filter.currentData() not in ("", replacement.status):
                self.status_filter.setCurrentIndex(0)
            self.refresh_list(replacement.path)
            return True
        except Exception as exc:
            self.add_log(f"ОШИБКА ЗАПИСИ {e.path}: {exc}\n{traceback.format_exc()}")
            QMessageBox.critical(self, "Ошибка записи", str(exc)); return False

    def keep_sylt(self):
        if self.write_choice("sylt"):
            self.next_conflict()

    def keep_uslt(self):
        if self.write_choice("uslt"):
            self.next_conflict()

    def save_edited_tag(self, mode):
        """Сохраняет только одну редактируемую сторону и затем повторно сравнивает файл."""
        e = self.current
        if not e:
            QMessageBox.information(self, "Нет файла", "Сначала выберите файл."); return
        editor = self.sylt_view if mode == "sylt" else self.uslt_view
        edited_text = editor.toPlainText().replace("\r", "")
        parsed = parse_lrc(edited_text)
        if mode == "sylt" and (not parsed or has_duplicate_empty_zero(parsed)):
            QMessageBox.warning(
                self, "Некорректный SYLT",
                "SYLT должен содержать непустой корректный LRC без повторяющихся пустых меток [00:00.000]."
            ); return
        if mode == "uslt" and has_lrc_timestamps(edited_text):
            if not parsed or has_duplicate_empty_zero(parsed):
                QMessageBox.warning(
                    self, "Некорректный USLT",
                    "В USLT обнаружены таймкоды, но LRC содержит ошибки или повторяющиеся пустые метки [00:00.000]."
                ); return
        try:
            tags = ID3(e.path)
            if mode == "sylt":
                tags.delall("SYLT")
                tags.add(SYLT(
                    encoding=3, lang="eng", format=2, type=1, desc="Edited lyrics",
                    text=[(text, ms) for ms, text in parsed],
                ))
            else:
                tags.delall("USLT")
                if edited_text.strip():
                    tags.add(USLT(encoding=3, lang="eng", desc="Edited lyrics", text=edited_text))
            tags.save(e.path, v2_version=3)
            side = "SYLT" if mode == "sylt" else "USLT"
            self.add_log(f"Сохранён только {side}: {e.path}")
            replacement = inspect_file(e.path)
            self.entries[self.entries.index(e)] = replacement
            self.current = replacement
            if self.status_filter.currentData() not in ("", replacement.status):
                self.status_filter.setCurrentIndex(0)
            self.refresh_list(replacement.path)
            if replacement.status != "Конфликт":
                self.next_conflict()
        except Exception as exc:
            self.add_log(f"ОШИБКА ЗАПИСИ {e.path}: {exc}\n{traceback.format_exc()}")
            QMessageBox.critical(self, "Ошибка записи", str(exc))

    def open_folder(self):
        if not self.current:
            QMessageBox.information(self, "Нет файла", "Сначала выберите файл."); return
        try:
            subprocess.Popen(["explorer.exe", str(self.current.path.parent)])
        except Exception as exc:
            self.add_log(f"Не удалось открыть папку: {exc}")
            QMessageBox.warning(self, "Ошибка", f"Не удалось открыть папку:\n{exc}")

    def next_conflict(self):
        start = self.list.currentRow() + 1
        for offset in range(self.list.count()):
            i = (start + offset) % self.list.count()
            if self.list.item(i).data(Qt.UserRole).status == "Конфликт":
                self.list.setCurrentRow(i); return
        if any(e.status == "Конфликт" for e in self.entries):
            self.search_edit.clear()
            index = self.status_filter.findData("Конфликт")
            self.status_filter.setCurrentIndex(index)
            if self.list.count(): self.list.setCurrentRow(0)
            return
        QMessageBox.information(self, "Готово", "Конфликтов больше нет.")

    def fix_safe(self):
        safe = [e for e in self.entries if e.status == "Без USLT"]
        if not safe: QMessageBox.information(self, "Готово", "Безопасных случаев нет."); return
        if QMessageBox.question(self, "Подтверждение", f"Создать USLT из SYLT для {len(safe)} файлов?") != QMessageBox.Yes: return
        ok = 0
        for e in list(safe):
            self.current = e
            if self.write_choice("sylt", use_editor=False): ok += 1
            QApplication.processEvents()
        self.add_log(f"Безопасные случаи: исправлено {ok} из {len(safe)}")
        QMessageBox.information(self, "Готово", f"Исправлено: {ok} из {len(safe)}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow(); window.show()
    sys.exit(app.exec())
