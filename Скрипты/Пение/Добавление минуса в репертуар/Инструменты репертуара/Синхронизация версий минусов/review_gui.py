"""Graphical review of repertoire version tags. No MP3 writes without confirmation."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import json
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QComboBox, QLineEdit, QAbstractItemView)

from cover_links import read_links, write_links
from sync_versions import (ROOT, MARKER, SEPARATOR, planned_folders,
    cross_folder_suggestions, apply_changes, legacy_work_tag)


def load_library() -> Path:
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    return Path(config["paths"]["library_root"])


class ReviewWindow(QMainWindow):
    def __init__(self, library: Path, plan: list[dict], proposals: list[dict]):
        super().__init__()
        self.library = library
        self.plan = plan
        self.proposals = proposals
        self.setWindowTitle("Синхронизация версий · Репертуар")
        self.resize(1140, 750)
        self.setStyleSheet("""
            QMainWindow {background:#121923;color:#f0f4fa}
            QWidget {color:#e9edf4;font-size:13px}
            QTableWidget {background:#1a2533;alternate-background-color:#203044;
                          gridline-color:#344356;selection-background-color:#355d7d}
            QLineEdit,QComboBox {background:#1f2c3b;border:1px solid #42546a;
                          padding:6px;border-radius:5px}
            QPushButton {background:#264d6d;border:1px solid #446780;
                         border-radius:6px;padding:8px 14px}
            QPushButton:hover {background:#326486}
            QHeaderView::section {background:#263749;padding:7px;border:0}
        """)
        body = QWidget()
        self.setCentralWidget(body)
        layout = QVBoxLayout(body)
        heading = QLabel("Проверка тегов версий")
        heading.setStyleSheet("font-size:23px;font-weight:700")
        layout.addWidget(heading)
        layout.addWidget(QLabel("Изменения в MP3 будут записаны только после подтверждения. "
                                "Снятая галочка исключает строку из записи."))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Применить", "Папка песни", "Тег в файлах", "Новый тег", "MP3"])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 4)
        for item in plan:
            if item["status"] != "change":
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            checked = QTableWidgetItem()
            checked.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            checked.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(row, 0, checked)
            self.table.setItem(row, 1, QTableWidgetItem(Path(item["folder"]).name))
            before = " → ".join(Path(p).name for p in item["changes"][:2])
            self.table.setItem(row, 2, QTableWidgetItem(before or "—"))
            editor = QLineEdit(item["target"])
            editor.setToolTip("Можно изменить тег перед записью")
            self.table.setCellWidget(row, 3, editor)
            self.table.setItem(row, 4, QTableWidgetItem(str(len(item["changes"]))))
            self.table.item(row, 1).setData(Qt.ItemDataRole.UserRole, item)
        layout.addWidget(QLabel("Каверы: можно вручную вписать полный тег в- без указания оригинала."))
        self.questions = QTableWidget(0, 3)
        self.questions.setHorizontalHeaderLabels(["Кавер / версия", "Связать с произведением", "Тег в- (вручную)"])
        self.questions.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.questions.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.questions, 2)
        self.options = []
        self.saved_links = read_links()
        for proposal in proposals:
            row = self.questions.rowCount()
            self.questions.insertRow(row)
            title = proposal["version"]["title"] + " — " + proposal["version"]["artist"]
            self.questions.setItem(row, 0, QTableWidgetItem(title))
            choice = QComboBox()
            choice.addItem("Пока не связывать", None)
            for candidate in proposal["possible_originals"]:
                choice.addItem(candidate["title"] + " — " + candidate["artist"], candidate["folder"])
            choice.addItem("Указать тег вручную", "manual")
            choice.addItem("Не связывать — запомнить", "ignore")
            tag_field = QLineEdit()
            tag_field.setPlaceholderText("в-Название-произведения")
            self.questions.setCellWidget(row, 2, tag_field)
            def toggle_fields(_index, combo=choice, field=tag_field):
                field.setEnabled(combo.currentData() == "manual")
            choice.currentIndexChanged.connect(toggle_fields)
            saved = self.saved_links.get(proposal["version"]["folder"])
            if isinstance(saved, dict) and saved.get("type") == "manual":
                tag_field.setText(saved.get("tag") or ("в-" + "-".join((saved.get("title", "") + " " + saved.get("artist", "")).split())))
                saved = "manual"
            for index in range(choice.count()):
                if choice.itemData(index) == saved and saved is not None:
                    choice.setCurrentIndex(index)
                    break
            self.questions.setCellWidget(row, 1, choice)
            toggle_fields(0)
            self.options.append((proposal, choice, tag_field))
        self.info = QLabel(f"Папок с изменениями: {self.table.rowCount()} · "
                           f"Вопросов по версиям: {len(proposals)}")
        layout.addWidget(self.info)
        actions = QHBoxLayout()
        layout.addLayout(actions)
        actions.addStretch()
        cancel = QPushButton("Закрыть без изменений")
        cancel.clicked.connect(self.close)
        actions.addWidget(cancel)
        save = QPushButton("Применить выбранное")
        save.clicked.connect(self.apply_selected)
        actions.addWidget(save)
        self.save_button = save

    def apply_selected(self):
        selected = []
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).checkState() != Qt.CheckState.Checked:
                continue
            item = dict(self.table.item(row, 1).data(Qt.ItemDataRole.UserRole))
            desired = self.table.cellWidget(row, 3).text().strip()
            if not desired.startswith("в-") or len(desired) < 3:
                QMessageBox.warning(self, "Недопустимый тег", "Тег должен начинаться с кириллического в-")
                return
            item["target"] = desired
            selected.append(item)
        decisions = {}
        for proposal, combo, tag_field in self.options:
            original_path = combo.currentData()
            cover = proposal["version"]
            if original_path is None:
                continue
            if original_path == "manual":
                target = tag_field.text().strip()
                if not target.startswith("в-") or len(target) < 3 or ";" in target or "\\n" in target:
                    QMessageBox.warning(self, "Тег версии", "Введи тег с префиксом в-, без ; и переносов строк.")
                    return
                decisions[cover["folder"]] = {"type": "manual", "tag": target}
                from sync_versions import current_version
                from mutagen.id3 import ID3
                changes = [p for p in cover["files"]
                           if current_version(ID3(Path(p))) != target or legacy_work_tag(ID3(Path(p)))]
                if changes:
                    selected.append({"folder": cover["folder"], "target": target,
                                     "changes": changes, "status": "change"})
                continue
            decisions[cover["folder"]] = original_path
            if original_path == "ignore":
                continue
            original = next((x for x in proposal["possible_originals"]
                             if x["folder"] == original_path), None)
            if original is None:
                continue
            from sync_versions import current_version, generated_version, duplicate_title_targets
            from mutagen.id3 import ID3
            target = next((x["target"] for x in selected
                           if x["folder"] == original_path), None)
            target = target or duplicate_title_targets(self.library).get(original_path)
            target = target or next((current_version(ID3(Path(p))) for p in original["files"]
                                     if current_version(ID3(Path(p)))), None)
            target = target or generated_version(Path(original_path).name)
            original_changes = [p for p in original["files"]
                                if current_version(ID3(Path(p))) != target or legacy_work_tag(ID3(Path(p)))]
            if original_changes and not any(x["folder"] == original_path for x in selected):
                selected.append({"folder": original_path, "target": target,
                                 "changes": original_changes, "status": "change"})
            changes = [p for p in cover["files"]
                       if current_version(ID3(Path(p))) != target or legacy_work_tag(ID3(Path(p)))]
            if changes:
                selected.append({"folder": cover["folder"], "target": target,
                                 "changes": changes, "status": "change"})
        if not selected and not decisions:
            QMessageBox.information(self, "Нет изменений", "Ничего не выбрано для записи.")
            return
        answer = QMessageBox.question(self, "Подтвердить изменение MP3",
            f"Обновить тег в {sum(len(x['changes']) for x in selected)} MP3? "
            "Перед записью будут созданы резервные копии.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        destination = Path(__file__).with_name("data") / "reports" / ("gui_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
        changed, failures = apply_changes(selected, destination) if selected else (0, [])
        if not failures and decisions:
            stored = read_links()
            stored.update(decisions)
            write_links(stored)
        QMessageBox.information(self, "Результат",
            f"Изменено MP3: {changed}. Ошибок: {len(failures)}. Резервные копии: {destination}")
        self.close()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--silent-when-clean", action="store_true")
    args = parser.parse_args()
    app = QApplication.instance() or QApplication(sys.argv)
    try:
        library = load_library()
        plan = planned_folders(library, MARKER, SEPARATOR)
        proposals = cross_folder_suggestions(library, MARKER, SEPARATOR)
        all_proposals = proposals
        remembered = read_links()
        unresolved = []
        for proposal in proposals:
            cover = proposal["version"]
            choice = remembered.get(cover["folder"])
            if choice is None:
                unresolved.append(proposal)
                continue
            if choice == "ignore":
                continue
            if isinstance(choice, dict) and choice.get("type") == "manual":
                try:
                    target = choice.get("tag") or ("в-" + "-".join((choice.get("title", "") + " " + choice.get("artist", "")).split()))
                    if not target.startswith("в-") or len(target) < 3:
                        raise ValueError("Неверный сохранённый тег")
                    from sync_versions import current_version
                    from mutagen.id3 import ID3
                    changes = [p for p in cover["files"]
                               if current_version(ID3(Path(p))) != target or legacy_work_tag(ID3(Path(p)))]
                    if changes:
                        plan.append({"folder": cover["folder"], "status": "change",
                                     "target": target, "changes": changes})
                except ValueError:
                    unresolved.append(proposal)
                continue
            original = next((x for x in proposal["possible_originals"]
                             if x["folder"] == choice), None)
            if original is None:
                unresolved.append(proposal)
                continue
            from sync_versions import current_version, generated_version, duplicate_title_targets
            from mutagen.id3 import ID3
            target = next((x["target"] for x in plan if x["folder"] == choice
                           and x.get("target")), None)
            target = target or duplicate_title_targets(library).get(choice)
            target = target or next((current_version(ID3(Path(p))) for p in original["files"]
                                     if current_version(ID3(Path(p)))), None)
            target = target or generated_version(Path(choice).name)
            changes = [p for p in cover["files"]
                       if current_version(ID3(Path(p))) != target or legacy_work_tag(ID3(Path(p)))]
            if changes:
                plan.append({"folder": cover["folder"], "status": "change",
                             "target": target, "changes": changes})
        proposals = unresolved
        plan = [x for x in plan if x["status"] != "review" or x["folder"] not in remembered]
        if args.silent_when_clean and not any(x["status"] in ("change", "review", "error") for x in plan) and not proposals:
            return 0
        window = ReviewWindow(library, plan, proposals if args.silent_when_clean else all_proposals)
        window.show()
        return app.exec()
    except Exception as exc:
        QMessageBox.critical(None, "Ошибка проверки репертуара", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
