"""Синхронизация общего тега в- у прямых MP3-версий одной папки.

По умолчанию только проверка. Запись возможна лишь с --apply.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
PENIE = ROOT.parent
sys.path.insert(0, str(PENIE / "_common"))
from id3_io import read_text, split_multi  # noqa: E402
from mutagen.id3 import ID3, TIT1  # noqa: E402

VERSION_PREFIX = "в-"
MARKER = "֎"
SEPARATOR = "_____"


def current_version(tags: ID3) -> str:
    values = [p.strip() for txt in read_text(tags, "TIT1")
              for p in split_multi(txt) if p.strip().casefold().startswith(VERSION_PREFIX)]
    return values[0] if values else ""


def generated_version(folder_name: str, separator: str = SEPARATOR) -> str:
    if separator not in folder_name:
        raise ValueError("В имени папки отсутствует разделитель: " + folder_name)
    title = folder_name.split(separator, 1)[0].strip()
    if not title:
        raise ValueError("Не удалось выделить название песни из папки: " + folder_name)
    return VERSION_PREFIX + "-".join(title.split())



# Only explicit version labels are stripped. Similar titles alone aren't proof.
VARIANT_LABELS = ("acoustic", "acoustics", "акустика", "remix", "mix", "cover",
                  "кавер", "ремикс", "live", "slow ver.", "slow version",
                  "instrumental", "инструментал", "unplugged")


def song_folder_info(folder: Path, separator: str = SEPARATOR):
    """Return (title, artist, base_title, explicit_variant), or None."""
    if separator not in folder.name:
        return None
    title, artist = [part.strip() for part in folder.name.split(separator, 1)]
    if not title or not artist:
        return None
    found = re.search(r"\s*\(([^()]*)\)\s*$", title)
    variant = bool(found and found.group(1).strip().casefold() in VARIANT_LABELS)
    base = title[:found.start()].strip() if variant else title
    return title, artist, base, variant


def cross_folder_suggestions(library: Path, marker: str = MARKER,
                             separator: str = SEPARATOR) -> list[dict]:
    """Report candidates only. Never use fuzzy matches to rewrite ID3."""
    from collections import defaultdict
    groups = defaultdict(list)
    for folder in sorted((p for p in library.iterdir() if p.is_dir()),
                         key=lambda p: (p.name.casefold(), p.name)):
        info = song_folder_info(folder, separator)
        if info is None:
            continue
        files = sorted((p for p in folder.iterdir() if p.is_file()
                        and p.suffix.casefold() == ".mp3" and marker in p.name),
                       key=lambda p: (p.name.casefold(), p.name))
        if not files:
            continue
        title, artist, base, variant = info
        groups[base.casefold()].append({"folder": str(folder), "title": title,
                                        "artist": artist, "variant": variant,
                                        "files": [str(p) for p in files]})
    proposals = []
    for base, items in sorted(groups.items()):
        if len(items) < 2 or not any(x["variant"] for x in items):
            continue
        originals = [x for x in items if not x["variant"]]
        versions = [x for x in items if x["variant"]]
        # Same-artist versions: likely match. Different performers: ask the user.
        for item in versions:
            matching = [x for x in originals if x["artist"].casefold() == item["artist"].casefold()]
            if len(matching) == 1:
                status, choices = "likely", matching
            elif len(originals) == 1:
                status, choices = "review", originals
            else:
                status, choices = "ambiguous", originals
            proposals.append({"title": base, "version": item, "status": status,
                              "possible_originals": choices,
                              "action": "review_only"})
    return proposals


def duplicate_title_targets(library: Path, marker: str = MARKER,
                            separator: str = SEPARATOR) -> dict[str, str]:
    """Distinguish unqualified originals sharing a title across performers."""
    from collections import defaultdict
    groups = defaultdict(list)
    for folder in library.iterdir():
        if not folder.is_dir():
            continue
        info = song_folder_info(folder, separator)
        if info is None:
            continue
        _, artist, base, variant = info
        if variant:
            continue
        if any(p.is_file() and p.suffix.casefold() == ".mp3" and marker in p.name
               for p in folder.iterdir()):
            groups[base.casefold()].append((folder, base, artist))
    targets = {}
    for originals in groups.values():
        if len({a.casefold() for _, _, a in originals}) > 1:
            for folder, base, artist in originals:
                targets[str(folder)] = VERSION_PREFIX + "-".join((base + " " + artist).split())
    return targets


def planned_folders(library: Path, marker: str = MARKER, separator: str = SEPARATOR):
    """Сканирование только: корень/папка песни/MP3; подпапки не трогаем."""
    result = []
    duplicate_targets = duplicate_title_targets(library, marker, separator)
    for folder in sorted((p for p in library.iterdir() if p.is_dir()), key=lambda p: (p.name.casefold(), p.name)):
        files = sorted((p for p in folder.iterdir()
                        if p.is_file() and p.suffix.casefold() == ".mp3" and marker in p.name),
                       key=lambda p: (p.name.casefold(), p.name))
        if len(files) < 2:
            continue
        try:
            entries = [(p, ID3(p)) for p in files]
            existing = [(p, current_version(tags)) for p, tags in entries]
            # Первый файл с заполненным значением задаёт его для всей папки.
            # Если ни у одного нет значения, формируем из названия папки.
            selected = next((value for _, value in existing if value), "")
            target = selected or duplicate_targets.get(str(folder)) or generated_version(folder.name, separator)
            changes = [str(p) for p, value in existing if value != target]
            result.append({"folder": str(folder), "target": target, "files": [str(p) for p in files],
                           "changes": changes, "source": "existing" if selected else "folder",
                           "status": "change" if changes else "ok"})
        except Exception as exc:
            result.append({"folder": str(folder), "status": "error", "error": str(exc), "changes": []})
    return result


def apply_changes(plan: list[dict], backup_root: Path) -> tuple[int, list[dict]]:
    changed = 0
    failures = []
    for item in plan:
        if item["status"] != "change":
            continue
        paths = [Path(p) for p in item["changes"]]
        try:
            # Уникальный каталог на каждую папку; копии всех изменяемых MP3 до первой записи.
            dest = backup_root / f"{len(failures):03d}_{Path(item['folder']).name}"
            if dest.exists():
                dest = backup_root / f"{len(failures):03d}_{Path(item['folder']).name}_{len(list(backup_root.iterdir()))}"
            dest.mkdir(parents=True, exist_ok=False)
            for p in paths:
                shutil.copy2(p, dest / p.name)
            for p in paths:
                tags = ID3(p)
                parts = [v for txt in read_text(tags, "TIT1") for v in split_multi(txt)]
                parts = [v for v in parts if not v.strip().casefold().startswith(VERSION_PREFIX)]
                parts.append(item["target"])
                tags.delall("TIT1")
                tags.add(TIT1(encoding=3, text=["; ".join(parts)]))
                tags.save(p)
                changed += 1
        except Exception as exc:
            failures.append({"folder": item["folder"], "error": str(exc)})
    return changed, failures


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Проверка и синхронизация тегов в-")
    parser.add_argument("--apply", action="store_true", help="Применить изменения после создания резервных копий")
    parser.add_argument("--root", type=Path, help="Переопределить каталог минусов (для тестов)")
    parser.add_argument("--report-dir", type=Path, help="Каталог отчётов")
    args = parser.parse_args(argv)
    try:
        config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        library = args.root or Path(config["paths"]["library_root"])
        if not library.is_dir():
            raise FileNotFoundError(f"Не найдена фонотека: {library}")
        separator = config["filename"]["separator"]
        marker = config["filename"]["info_separator"]
        plan = planned_folders(library, marker, separator)
        report_dir = args.report_dir or Path(__file__).with_name("data") / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        changed, errors = (0, [])
        if args.apply:
            changed, errors = apply_changes(plan, report_dir / f"backup_{stamp}")
        suggestions = cross_folder_suggestions(library, marker, separator)
        summary = dict(cross_folder_suggestions=suggestions,
                       mode="apply" if args.apply else "preview", library=str(library),
                       folders=len(plan), pending_files=sum(len(v["changes"]) for v in plan),
                       written_files=changed, errors=errors, plan=plan)
        destination = report_dir / f"{summary['mode']}_{stamp}.json"
        destination.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for entry in plan:
            print(f"{entry['status'].upper()}: {Path(entry['folder']).name} | {entry.get('target', entry.get('error', ''))} | исправить {len(entry['changes'])}")
        print(f"Папок: {len(plan)}; нужно исправить MP3: {summary['pending_files']}; записано: {changed}; ошибок: {len(errors) + sum(e['status'] == 'error' for e in plan)}")
        print(f"Предложений по разным папкам: {len(suggestions)} (только в отчёте; без записи).")
        print("Отчёт:", destination)
        return 1 if errors or any(e["status"] == "error" for e in plan) else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("ОШИБКА:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
