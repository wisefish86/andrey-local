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

CONFIG_FILE = ROOT / "config.json"
LEGACY_STATE_FILE = ROOT / "data" / "syncthing_manifest.json"
MANIFEST_DIR = ROOT / "data" / "manifests"
# Historical root is only used to safely adopt manifests created before v2.
LEGACY_V1_TARGET = Path(r"D:\Sync\Syncthing\С ПК на телефон\Минусы по категориям")


def safe_folder_name(value: str) -> bool:
    """One Windows directory component; no path traversal or special devices."""
    reserved = {"CON", "PRN", "AUX", "NUL"}
    reserved.update(f"COM{i}" for i in range(1, 10))
    reserved.update(f"LPT{i}" for i in range(1, 10))
    if not value or value in (".", "..") or value.rstrip(" .") != value:
        return False
    if any(c in value for c in '<>:"/\\|?*') or any(ord(c) < 32 for c in value):
        return False
    return value.split(".")[0].upper() not in reserved


def load_settings(file: Path) -> dict:
    if not file.is_file():
        raise ValueError("Не найден конфиг инструмента: " + str(file))
    cfg = json.loads(file.read_text(encoding="utf-8-sig"))
    if not isinstance(cfg, dict):
        raise ValueError("Корень config.json должен быть объектом")
    for key in ("source_root", "target_root"):
        value = cfg.get(key)
        if not isinstance(value, str) or not value.strip() or not Path(value).is_absolute():
            raise ValueError(f"Поле {key} должно содержать абсолютный путь к папке")
    marker = cfg.get("filename_marker")
    if not isinstance(marker, str) or not marker.strip() or len(marker) > 16:
        raise ValueError("filename_marker должен быть непустой короткой строкой")
    folders = cfg.get("excluded_folders")
    if not isinstance(folders, list) or not all(isinstance(x, str) and safe_folder_name(x) for x in folders):
        raise ValueError("excluded_folders должен быть массивом имён папок без путей")
    mapping = cfg.get("status_directories")
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError("status_directories должен быть непустым объектом")
    if not all(isinstance(k, str) and k.strip() and isinstance(v, str) and safe_folder_name(v) for k, v in mapping.items()):
        raise ValueError("Некорректные статусы или имена папок в status_directories")
    status_dirs = {k.strip().casefold(): v for k, v in mapping.items()}
    if len(status_dirs) != len(mapping) or len({x.casefold() for x in status_dirs.values()}) != len(status_dirs):
        raise ValueError("Дублирующиеся статусы или названия выходных папок")
    skip = cfg.get("excluded_statuses")
    if not isinstance(skip, list) or not all(isinstance(x, str) and x.strip() for x in skip):
        raise ValueError("excluded_statuses должен быть массивом названий статусов")
    excluded_statuses = {x.strip().casefold() for x in skip}
    if set(status_dirs) & excluded_statuses:
        raise ValueError("Один статус не может одновременно копироваться и исключаться")
    return {
        "source": Path(cfg["source_root"]).resolve(),
        "target": Path(cfg["target_root"]).resolve(),
        "marker": marker,
        "excluded_folders": {x.casefold() for x in folders},
        "status_directories": status_dirs,
        "excluded_statuses": excluded_statuses,
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


def manifest_path(target: Path) -> Path:
    """Each destination owns an independent manifest; new paths cannot delete old ones."""
    key = os.path.normcase(str(target.resolve())).casefold()
    name = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20] + ".json"
    return MANIFEST_DIR / name


def load_state(target: Path, file: Path) -> dict:
    if file.exists():
        origin = file
    elif LEGACY_STATE_FILE.exists() and os.path.normcase(str(target)) == os.path.normcase(str(LEGACY_V1_TARGET.resolve())):
        origin = LEGACY_STATE_FILE
    else:
        return {}
    data = json.loads(origin.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        raise RuntimeError("Неверный формат реестра Syncthing: " + str(origin))
    bound = data.get("target_root")
    if isinstance(bound, str) and bound:
        if os.path.normcase(str(Path(bound).resolve())) != os.path.normcase(str(target)):
            raise RuntimeError("Целевая папка изменилась, но реестр привязан к другой папке: " + bound +
                               ". Нельзя использовать старый реестр для удаления в новой папке.")
    elif data.get("version") == 1:
        if os.path.normcase(str(target)) != os.path.normcase(str(LEGACY_V1_TARGET.resolve())):
            raise RuntimeError("Старый реестр без пути назначения: сначала обновите его на исходной папке Syncthing, " +
                               "затем изменяйте target_root в config.json.")
    else:
        raise RuntimeError("Реестр без привязки к папке назначения. Операция отменена.")
    return data["files"]


def status_of(path: Path) -> str:
    values = read_txxx(load_tags(path), "TXXX:OCCASION")
    return (clean(values[0]) if values else "").casefold()


def build_plan(source: Path, excluded: set[str], marker: str,
               status_dirs: dict[str, str], excluded_statuses: set[str]):
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
        allowed = {statuses[p] for p in tagged if statuses[p] in status_dirs}
        for p in tagged:
            if statuses[p] not in status_dirs and statuses[p] not in excluded_statuses:
                stats["unknown_status_mp3"] += 1
        for status in sorted(allowed):
            category = status_dirs[status]
            stats["song_folders"] += 1
            for path in paths:
                if not path.is_file():
                    continue
                if path.suffix.casefold() == ".mp3":
                    st = statuses[path]
                    if st in excluded_statuses:
                        continue
                    if marker in path.name:
                        if st != status:
                            continue
                    elif st in status_dirs and st != status:
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


def folders_to_cleanup(previous: dict, plan: dict[str, Path]) -> list[str]:
    """Only song folders previously owned by this tool, no category roots."""
    old = {Path(rel).parent.as_posix() for rel in previous}
    active = {Path(rel).parent.as_posix() for rel in plan}
    return sorted(old - active, key=lambda name: (-name.count("/"), name.casefold()))


def cleanup_empty_folders(target: Path, candidates: list[str]) -> tuple[list[str], list[str]]:
    removed: list[str] = []
    kept: list[str] = []
    for rel in candidates:
        folder = safe_destination(target, rel)
        if not folder.exists():
            continue
        if not folder.is_dir():
            raise RuntimeError("Ожидалась папка песни: " + rel)
        try:
            folder.rmdir()  # Only succeeds if all contents have gone.
            removed.append(rel)
        except OSError:
            # Never delete a non-empty directory or manually added files.
            kept.append(rel)
    return removed, kept


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
    parser.add_argument("--config", type=Path, default=CONFIG_FILE, help="JSON настроек этого инструмента")
    parser.add_argument("--target", type=Path, help="Переопределить target_root из JSON")
    parser.add_argument("--source", type=Path, help="Переопределить source_root из JSON")
    args = parser.parse_args()

    try:
        settings = load_settings(args.config.resolve())
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error("Ошибка config.json: " + str(exc))
    if args.apply and ((args.source is None) != (args.target is None)):
        parser.error("Для тестового --apply указывайте одновременно --source и --target")
    source = (args.source or settings["source"]).resolve()
    target = (args.target or settings["target"]).resolve()
    if not source.is_dir():
        parser.error("Источник не найден: " + str(source))
    if source == target or source.is_relative_to(target) or target.is_relative_to(source):
        parser.error("Источник и назначение не должны пересекаться")
    if target.exists() and not target.is_dir():
        parser.error("Назначение не является папкой")
    excluded = settings["excluded_folders"]
    marker = settings["marker"]
    state_file = manifest_path(target)
    previous = load_state(target, state_file)
    plan, errors, counts = build_plan(
        source, excluded, marker, settings["status_directories"], settings["excluded_statuses"]
    )
    if not plan:
        errors.append("Не найдено ни одного подходящего файла: синхронизация отменена.")
    actions, conflicts = examine(target, plan, previous)
    errors.extend(conflicts)
    folders = folders_to_cleanup(previous, plan)
    report = {
        "mode": "apply" if args.apply else "preview",
        "source": str(source), "target": str(target),
        "counts": dict(counts),
        "actions": dict(Counter(a[0] for a in actions)),
        "details": [{"action": action, "target": rel,
                     "source": str(path.relative_to(source)) if path else ""}
                    for action, rel, path in actions],
        "folders_to_cleanup_if_empty": folders,
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
            removed_folders, kept_folders = cleanup_empty_folders(target, folders)
            report["removed_folders"] = removed_folders
            report["nonempty_folders_kept"] = kept_folders
            state_file.parent.mkdir(parents=True, exist_ok=True)
            temp = state_file.with_suffix(".tmp")
            temp.write_text(json.dumps({"version": 2, "target_root": str(target), "files": state},
                                       ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp, state_file)
        except Exception as exc:
            errors.append("Ошибка копирования; повторите запуск: " + repr(exc))
        report["errors"] = errors
    report_dir = ROOT / "data" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / ("sync_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json")
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Настройки:", args.config.resolve())
    print("Реестр этой папки назначения:", state_file)
    print("Режим:", "КОПИРОВАНИЕ" if args.apply else "ПРЕДПРОСМОТР")
    print("Папок с песнями по статусам:", counts["song_folders"])
    print("Файлов для раскладки:", len(plan))
    for kind, count in sorted(Counter(a[0] for a in actions).items()):
        print(kind, count)
    print("Папок старых категорий для проверки на пустоту:", len(folders))
    if args.apply and not errors:
        print("Удалено пустых папок песен:", len(report.get("removed_folders", [])))
        print("Оставлено непустых папок:", len(report.get("nonempty_folders_kept", [])))
    print("MP3 с неопределённым статусом:", counts["unknown_status_mp3"])
    print("Ошибок:", len(errors))
    for message in errors[:10]:
        print("ОШИБКА:", message)
    print("Отчёт:", report_file)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
