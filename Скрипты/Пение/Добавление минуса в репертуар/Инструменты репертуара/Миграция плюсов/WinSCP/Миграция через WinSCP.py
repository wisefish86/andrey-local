from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
MIGRATION_DIR = HERE.parent
MIGRATION_SCRIPT = MIGRATION_DIR / "Миграция плюсов на FTP.py"


def load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "andrey_migration_plus_ftp",
        MIGRATION_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Не удалось загрузить {MIGRATION_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MIG = load_migration_module()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Миграция плюсов через WinSCP без FTP-загрузки из Python."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--apply-links", action="store_true")
    parser.add_argument("--open-folder", action="store_true")
    return parser.parse_args()


def cfg_paths(config: dict[str, Any]) -> dict[str, Path]:
    mig_cfg = config.get("migration_plus_links", {})
    winscp_cfg = mig_cfg.get("winscp", {})
    report_dir = MIG.APP_ROOT / Path(
        mig_cfg.get("report_dir", "data/migration_plus_links")
    )
    return {
        "upload_dir": MIG.APP_ROOT
        / Path(
            winscp_cfg.get(
                "upload_dir",
                "data/migration_plus_links/winscp_upload",
            )
        ),
        "manifest": MIG.APP_ROOT
        / Path(
            winscp_cfg.get(
                "manifest_file",
                "data/migration_plus_links/winscp_manifest.json",
            )
        ),
        "reports": MIG.APP_ROOT
        / Path(
            winscp_cfg.get(
                "reports_dir",
                "data/migration_plus_links/winscp_reports",
            )
        ),
        "instruction": report_dir / "WinSCP - КУДА ЗАГРУЖАТЬ.txt",
        "missing": report_dir / "WinSCP - НЕ ЗАГРУЖЕНО.txt",
    }


def http_cached(
    url: str,
    timeout: int,
    cache: dict[str, tuple[bool, str]],
) -> tuple[bool, str]:
    url = MIG.clean(url)
    if not url:
        return False, "пустой URL"
    if url not in cache:
        cache[url] = MIG.http_check(url, timeout)
    return cache[url]


def prepare(config: dict[str, Any], open_folder: bool) -> int:
    mig_cfg = config.get("migration_plus_links", {})
    paths = cfg_paths(config)
    upload_dir = paths["upload_dir"]
    manifest_path = paths["manifest"]
    reports_dir = paths["reports"]
    instruction_path = paths["instruction"]

    library_root = Path(config.get("paths", {}).get("library_root", ""))
    if not library_root.is_dir():
        raise RuntimeError(f"Не найден library_root: {library_root}")

    if upload_dir.exists():
        shutil.rmtree(upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    timeout = int(
        mig_cfg.get(
            "http_check_timeout_seconds",
            config.get("plus_upload", {}).get("http_check_timeout_seconds", 10),
        )
    )
    filter_mode = MIG.clean(mig_cfg.get("default_filter")) or "all"
    items = MIG.scan_library(library_root, config, filter_mode, "")

    http_cache: dict[str, tuple[bool, str]] = {}
    manifest_items: list[dict[str, Any]] = []
    skipped_working_folders = 0
    already_online = 0
    copied = 0
    pending_minuses_total = 0
    working_minuses_total = 0

    for item in items:
        if item.get("status") != "ready":
            continue

        pending_minuses: list[str] = []
        working_minuses: list[dict[str, str]] = []

        for row in item.get("old_woas", []):
            minus_file = str(row.get("file", ""))
            old_url = MIG.clean(row.get("woas"))
            if old_url:
                ok, detail = http_cached(old_url, timeout, http_cache)
                if ok:
                    working_minuses.append(
                        {
                            "file": minus_file,
                            "woas": old_url,
                            "check": detail,
                        }
                    )
                    continue
            pending_minuses.append(minus_file)

        if not pending_minuses:
            skipped_working_folders += 1
            working_minuses_total += len(working_minuses)
            continue

        canonical_url = str(item.get("url", ""))
        canonical_ok, canonical_detail = http_cached(
            canonical_url,
            timeout,
            http_cache,
        )

        plus_path = Path(item["plus"])
        remote_name = str(item["remote_name"])
        upload_needed = not canonical_ok

        if upload_needed:
            shutil.copy2(plus_path, upload_dir / remote_name)
            copied += 1
        else:
            already_online += 1

        pending_minuses_total += len(pending_minuses)
        working_minuses_total += len(working_minuses)

        manifest_items.append(
            {
                "folder": item.get("folder", ""),
                "plus": str(plus_path),
                "remote_name": remote_name,
                "url": canonical_url,
                "local_size": plus_path.stat().st_size,
                "upload_needed": upload_needed,
                "canonical_http_check": canonical_detail,
                "pending_minuses": pending_minuses,
                "working_minuses_preserved": working_minuses,
            }
        )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    payload = {
        "schema_version": 1,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": "andrey-local / WinSCP plus migration",
        "remote_dir": MIG.clean(
            config.get("plus_upload", {}).get("remote_dir")
        ),
        "public_base_url": MIG.clean(
            config.get("plus_upload", {}).get("public_base_url")
        ),
        "upload_dir": str(upload_dir),
        "summary": {
            "manifest_items": len(manifest_items),
            "files_to_upload": copied,
            "canonical_already_online": already_online,
            "folders_skipped_all_woas_working": skipped_working_folders,
            "pending_minuses": pending_minuses_total,
            "working_minuses_preserved": working_minuses_total,
            "ambiguous_plus": sum(
                1 for x in items if x.get("status") == "ambiguous_plus"
            ),
            "no_plus": sum(
                1 for x in items if x.get("status") == "no_plus"
            ),
            "slug_collision": sum(
                1 for x in items if x.get("status") == "slug_collision"
            ),
            "tag_read_error": sum(
                1 for x in items if x.get("status") == "tag_read_error"
            ),
        },
        "items": manifest_items,
    }

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    manifest_path.write_text(text, encoding="utf-8")
    (reports_dir / f"prepare_{stamp}.json").write_text(
        text,
        encoding="utf-8",
    )

    instruction_path.write_text(
        "\n".join(
            [
                "МИГРАЦИЯ ПЛЮСОВ ЧЕРЕЗ WinSCP",
                "",
                "Загрузить содержимое папки:",
                str(upload_dir),
                "",
                "В FTP-папку:",
                payload["remote_dir"],
                "",
                f"Файлов для загрузки: {copied}",
                f"Уже доступны по HTTPS и не копировались: {already_online}",
                "",
                "ВАЖНО: загружать СОДЕРЖИМОЕ папки winscp_upload,",
                "а не саму папку winscp_upload отдельным уровнем.",
                "",
                "После завершения WinSCP запусти:",
                "2. Прописать WOAS после WinSCP.bat",
            ]
        ),
        encoding="utf-8",
    )

    print("Готово: пакет для WinSCP подготовлен.")
    print(f"Файлов для загрузки: {copied}")
    print(f"Уже есть на сайте: {already_online}")
    print(f"Минусовок ждут WOAS: {pending_minuses_total}")
    print(f"Папка: {upload_dir}")
    print(f"FTP-папка назначения: {payload['remote_dir']}")
    print(f"Манифест: {manifest_path}")

    if open_folder and os.name == "nt":
        os.startfile(upload_dir)  # type: ignore[attr-defined]

    return 0


def apply_links(config: dict[str, Any]) -> int:
    mig_cfg = config.get("migration_plus_links", {})
    paths = cfg_paths(config)
    manifest_path = paths["manifest"]
    reports_dir = paths["reports"]
    missing_path = paths["missing"]

    if not manifest_path.is_file():
        raise RuntimeError(
            "Не найден winscp_manifest.json. "
            "Сначала запусти подготовку для WinSCP."
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = list(manifest.get("items", []))
    timeout = int(
        mig_cfg.get(
            "http_check_timeout_seconds",
            config.get("plus_upload", {}).get("http_check_timeout_seconds", 10),
        )
    )

    http_cache: dict[str, tuple[bool, str]] = {}
    results: list[dict[str, Any]] = []
    unavailable: list[dict[str, str]] = []
    updated = 0
    skipped_current_working = 0
    errors = 0

    for index, item in enumerate(items, 1):
        url = MIG.clean(item.get("url"))
        remote_name = str(item.get("remote_name", ""))
        print(f"[{index}/{len(items)}] {remote_name}")

        ok, detail = http_cached(url, timeout, http_cache)
        if not ok:
            unavailable.append(
                {
                    "remote_name": remote_name,
                    "url": url,
                    "check": detail,
                }
            )
            results.append(
                {
                    "remote_name": remote_name,
                    "url": url,
                    "status": "url_unavailable",
                    "http_check": detail,
                }
            )
            print(f"  ! URL недоступен: {detail}")
            continue

        minus_results: list[dict[str, str]] = []
        for minus_text in item.get("pending_minuses", []):
            minus = Path(minus_text)

            if not minus.is_file():
                errors += 1
                minus_results.append(
                    {
                        "file": str(minus),
                        "status": "missing_local_file",
                    }
                )
                print(f"  ! Нет локального файла: {minus}")
                continue

            try:
                tags = MIG.load_tags(minus)
                current_url = MIG.read_url(tags, "WOAS")

                if current_url:
                    current_ok, current_detail = http_cached(
                        current_url,
                        timeout,
                        http_cache,
                    )
                    if current_ok:
                        skipped_current_working += 1
                        minus_results.append(
                            {
                                "file": str(minus),
                                "status": "skipped_working_woas",
                                "old_woas": current_url,
                                "new_woas": current_url,
                                "check": current_detail,
                            }
                        )
                        continue

                state, old = MIG.write_woas(minus, url)
                if state in {"updated", "already_matching"}:
                    updated += 1
                minus_results.append(
                    {
                        "file": str(minus),
                        "status": state,
                        "old_woas": old,
                        "new_woas": url,
                    }
                )

            except Exception as exc:
                errors += 1
                minus_results.append(
                    {
                        "file": str(minus),
                        "status": "error",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

        results.append(
            {
                "remote_name": remote_name,
                "url": url,
                "status": "done",
                "http_check": detail,
                "minus_results": minus_results,
            }
        )
        updated_here = sum(
            1
            for row in minus_results
            if row.get("status") in {"updated", "already_matching"}
        )
        print(f"  ✓ URL работает; WOAS обновлено: {updated_here}")

    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "manifest": str(manifest_path),
        "summary": {
            "manifest_items": len(items),
            "woas_updated": updated,
            "working_woas_preserved": skipped_current_working,
            "urls_unavailable": len(unavailable),
            "errors": errors,
        },
        "results": results,
    }
    report_path = reports_dir / f"apply_{stamp}.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if unavailable:
        lines = [
            "НЕ ЗАГРУЖЕНО ИЛИ ЕЩЁ НЕ ДОСТУПНО ПО HTTPS",
            f"Проверено: {datetime.now().isoformat(timespec='seconds')}",
            "",
        ]
        for row in unavailable:
            lines.append(row["remote_name"])
            lines.append(f"  {row['url']}")
            lines.append(f"  {row['check']}")
            lines.append("")
        missing_path.write_text("\n".join(lines), encoding="utf-8")
    else:
        try:
            missing_path.unlink()
        except FileNotFoundError:
            pass

    print()
    print("Готово.")
    print(f"WOAS обновлено: {updated}")
    print(f"Рабочих WOAS сохранено без изменений: {skipped_current_working}")
    print(f"URL ещё недоступно: {len(unavailable)}")
    print(f"Ошибок записи: {errors}")
    print(f"Отчёт: {report_path}")
    if unavailable:
        print(f"Список незагруженных: {missing_path}")

    if errors:
        return 3
    if unavailable:
        return 2
    return 0


def main() -> int:
    args = parse_args()
    config = MIG.load_config()
    if args.prepare:
        return prepare(config, args.open_folder)
    return apply_links(config)


if __name__ == "__main__":
    raise SystemExit(main())
