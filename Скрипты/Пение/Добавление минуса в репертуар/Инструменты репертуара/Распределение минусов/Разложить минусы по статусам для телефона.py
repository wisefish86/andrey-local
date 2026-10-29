"""Копирование репертуара по ID3-статусам в плоские папки для Syncthing.

Источники никогда не перемещаются и не изменяются. Удаляются только ранее
скопированные этим инструментом файлы, если их не меняли после копирования.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_ROOT = ROOT.parents[1]
sys.path.insert(0, str(APP_ROOT.parent))
from _common.id3_io import clean, load_tags, read_txxx

DEFAULT_TARGET = Path(r"D:\Sync\Syncthing\С ПК на телефон\Минусы по категориям")
STATE_FILE = ROOT / "data" / "syncthing_manifest.json"
STATUS_DIRS = {
    "г-1-база": "01 База",
    "г-2-рабочие": "02 Рабочие",
    "г-3-тестирую": "03 Тестирую",
    "г-4-повторить": "04 Повторить",
    "г-5-выучить": "05 Выучить",
}
EXCLUDED_STATUSES = {"г-6-запас", "г-7-версии"}
EXCLUDED_FOLDERS = {
    "files", "additi0ns", "additions", "editions", "- - добавляю в репертуар"
}


def metadata(path: Path) -> dict[str, int]:
    st = path.stat()
    return {"size": st.st_size, "mtime_ns": st.st_mtime_ns}


def unchanged(path: Path, saved: dict) -> bool:
    return path.is_file() and not path.is_symlink() and metadata(path) == {
        "size": saved.get("size"), "mtime_ns": saved.get("mtime_ns")
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def identical(a: Path, b: Path) -> bool:
    if metadata(a)["size"] != metadata(b)["size"]:
        return False
    if metadata(a) == metadata(b):
        return True
    return sha256(a) == sha256(b)


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        raise RuntimeError("Неверный формат реестра Syncthing: " + str(STATE_FILE))
    return data["files"]


def status_of(path: Path) -> str:
    values = read_txxx(load_tags(path), "TXXX:OCCASION")
    return (clean(values[0]) if values else "").casefold()


def build_plan(source: Path, excluded: set[str], marker: str):
    plan: dict[str, Path] = {}
    origins: dict[str, str] = {}
    errors: list[str] = []
    stats = Counter()
    for current, dirs, files in os.walk(source, followlinks=False):
        dirs[:] = [name for name in dirs if name.casefold() not in excluded
                  and not (Path(current) / name).is_symlink()]
        folder = Path(current)
        if folder == source:
            continue
        paths = [folder / name for name in files if not (folder / name).is_symlink()]
        tagged = [p for p in paths if p.suffix.casefold() == ".mp3" and marker in p.name]
        if not tagged:
            continue
        statuses: dict[Path, str] = {}
        try:
            for p in paths:
                if p.suffix.casefold() == ".mp3":
                    statuses[p] = status_of(p)
        except Exception as exc:
            errors.append(f"Ошибка чтения ID3 в {folder}: {exc}")
            continue
        allowed = {statuses[p] for p in tagged if statuses[p] in STATUS_DIRS}
        for p in tagged:
            if statuses[p] not in STATUS_DIRS and statuses[p] not in EXCLUDED_STATUSES:
                stats["unknown_status_mp3"] += 1
        for status in sorted(allowed):
            category = STATUS_DIRS[status]
            stats["song_folders"] += 1
            for path in paths:
                if not path.is_file():
                    continue
                if path.suffix.casefold() == ".mp3":
                    st = statuses[path]
                    if st in EXCLUDED_STATUSES:
                        continue
                    if marker in path.name:
                        if st != status:
                            continue
                    elif st in STATUS_DIRS and st != status:
                        continue
                rel = (Path(category) / folder.name / path.name).as_posix()
                folded = rel.casefold()
                if folded in origins and origins[folded] != str(path):
                    errors.append("Коллизия имён: " + rel + " (" + origins[folded] + " / " + str(path) + ")")
                    continue
                origins[folded] = str(path)
                plan[rel] = path
                stats["planned_files"] += 1
    return plan, errors, stats


def safe_destination(target: Path, relative: str) -> Path:
    path = target / Path(relative)
    if not path.resolve(strict=False).is_relative_to(target.resolve()):
        raise RuntimeError("Выход за пределы целевого каталога: " + relative)
    if path.is_symlink() or path.parent.is_symlink():
        raise RuntimeError("Символическая ссылка в назначении: " + relative)
    return path


def examine(target: Path, plan: dict[str, Path], previous: dict):
    actions = []
    problems = []
    for rel, source in plan.items():
        try:
            dest = safe_destination(target, rel)
            if not dest.exists():
                action = "copy"
            elif not dest.is_file():
                raise RuntimeError("Ожидался файл, найдена папка")
            elif rel in previous and not unchanged(dest, previous[rel]["dest"]):
                raise RuntimeError("Файл назначения изменён вне скрипта")
            elif rel not in previous and not identical(source, dest):
                raise RuntimeError("Существующий файл не принадлежит скрипту")
            elif identical(source, dest):
                action = "keep"
            else:
                action = "update"
            actions.append((action, rel, source))
        except Exception as exc:
            problems.append(rel + ": " + str(exc))
    for rel, record in previous.items():
        if rel in plan:
            continue
        try:
            dest = safe_destination(target, rel)
            if not dest.exists():
                continue
            if not unchanged(dest, record["dest"]):
                raise RuntimeError("Старая копия была изменена; не удаляем")
            actions.append(("delete", rel, None))
        except Exception as exc:
            problems.append(rel + ": " + str(exc))
    return actions, problems


def atomic_copy(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_name(dest.name + ".sync-" + uuid.uuid4().hex + ".tmp")
    try:
        shutil.copy2(source, temp)
        os.replace(temp, dest)
    finally:
        if temp.exists():
            temp.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description="Распределить копии песен по категориям для телефона")
    parser.add_argument("--apply", action="store_true", help="Копировать и убирать устаревшие управляемые копии")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--source", type=Path, help="Для теста: другой корень фонотеки")
    args = parser.parse_args()

    config = json.loads((APP_ROOT / "config.json").read_text(encoding="utf-8"))
    source = (args.source or Path(config["paths"]["library_root"])).resolve()
    target = args.target.resolve()
    if not source.is_dir():
        parser.error("Источник не найден: " + str(source))
    if source == target or source.is_relative_to(target) or target.is_relative_to(source):
        parser.error("Источник и назначение не должны пересекаться")
    if target.exists() and not target.is_dir():
        parser.error("Назначение не является папкой")
    excluded = EXCLUDED_FOLDERS | {
        str(x).casefold() for x in config.get("site_export", {}).get("exclude_dirs", [])
    }
    marker = clean(config.get("site_export", {}).get("marker")) or "֎"
    previous = load_state()
    plan, errors, counts = build_plan(source, excluded, marker)
    if not plan:
        errors.append("Не найдено ни одного подходящего файла: синхронизация отменена.")
    actions, conflicts = examine(target, plan, previous)
    errors.extend(conflicts)
    report = {
        "mode": "apply" if args.apply else "preview",
        "source": str(source), "target": str(target),
        "counts": dict(counts),
        "actions": dict(Counter(a[0] for a in actions)),
        "details": [{"action": action, "target": rel,
                     "source": str(path.relative_to(source)) if path else ""}
                    for action, rel, path in actions],
        "errors": errors,
    }
    if args.apply and not errors:
        state = {}
        try:
            for action, rel, path in actions:
                dest = safe_destination(target, rel)
                if action in ("copy", "update"):
                    atomic_copy(path, dest)
                elif action == "delete":
                    if dest.exists():
                        dest.unlink()
                    continue
                state[rel] = {"source": str(path.relative_to(source)), "dest": metadata(dest)}
            for category in STATUS_DIRS.values():
                group = target / category
                if group.is_dir():
                    for child in group.iterdir():
                        if child.is_dir() and not child.is_symlink():
                            try:
                                child.rmdir()
                            except OSError:
                                pass
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            temp = STATE_FILE.with_suffix(".tmp")
            temp.write_text(json.dumps({"version": 1, "files": state},
                                       ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp, STATE_FILE)
        except Exception as exc:
            errors.append("Ошибка копирования; повторите запуск: " + repr(exc))
        report["errors"] = errors
    report_dir = ROOT / "data" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / ("sync_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json")
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Режим:", "КОПИРОВАНИЕ" if args.apply else "ПРЕДПРОСМОТР")
    print("Папок с песнями по статусам:", counts["song_folders"])
    print("Файлов для раскладки:", len(plan))
    for kind, count in sorted(Counter(a[0] for a in actions).items()):
        print(kind, count)
    print("MP3 с неопределённым статусом:", counts["unknown_status_mp3"])
    print("Ошибок:", len(errors))
    for message in errors[:10]:
        print("ОШИБКА:", message)
    print("Отчёт:", report_file)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
