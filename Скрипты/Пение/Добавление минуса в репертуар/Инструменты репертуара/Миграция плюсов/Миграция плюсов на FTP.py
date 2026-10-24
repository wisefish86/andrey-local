from __future__ import annotations

import argparse
import copy
import csv
import ftplib
import getpass
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

def find_app_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "config.json").is_file() and (candidate / "src").is_dir():
            return candidate
    raise RuntimeError("Не найден корень программы с config.json")


APP_ROOT = find_app_root(Path(__file__).resolve().parent)
PENIE_ROOT = APP_ROOT.parent
if str(PENIE_ROOT) not in sys.path:
    sys.path.insert(0, str(PENIE_ROOT))

from _common.id3_io import clean, load_tags, read_url, write_field
from _common.plus_storage import (
    ftp_ensure_dir,
    ftp_remote_exists,
    ftp_remote_size,
    slugify_remote_name,
)

CONFIG_PATH = APP_ROOT / "config.json"
WOAS_SPEC = {"kind": "url", "frame": "WOAS"}
CYRILLIC_CHARS = set("абвгдеёжзийклмнопрстуфхцчшщъыьэюя")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Пакетная миграция плюсов: MP3 без ֎ рядом с минусовками ֎ "
            "загружается на FTP, затем URL записывается в WOAS минусовок."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Реально загружать файлы и менять WOAS. Без флага выполняется только dry-run.",
    )
    parser.add_argument(
        "--filter",
        choices=("all", "cyrillic", "latin"),
        default=None,
        help="Ограничить проход: все / имя плюса содержит кириллицу / без кириллицы.",
    )
    parser.add_argument(
        "--folder",
        default="",
        help="Для теста: обрабатывать только папки, путь которых содержит эту строку.",
    )
    parser.add_argument(
        "--root",
        default="",
        help="Переопределить корень репертуара. По умолчанию paths.library_root из config.json.",
    )
    parser.add_argument(
        "--overwrite-remote",
        action="store_true",
        help="Разрешить заменить удалённый файл, если имя совпало, а размер отличается.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Не спрашивать финальное подтверждение APPLY.",
    )
    return parser.parse_args()


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def contains_cyrillic(text: str) -> bool:
    return any(ch.casefold() in CYRILLIC_CHARS for ch in text)


def matches_filter(path: Path, mode: str) -> bool:
    if mode == "all":
        return True
    has_cyr = contains_cyrillic(path.stem)
    return has_cyr if mode == "cyrillic" else not has_cyr


def read_minus_woas(paths: list[Path]) -> tuple[list[dict[str, str]], str]:
    rows: list[dict[str, str]] = []
    errors: list[str] = []
    for path in paths:
        try:
            tags = load_tags(path)
            rows.append({"file": str(path), "woas": read_url(tags, "WOAS")})
        except Exception as exc:
            errors.append(f"{path.name}: {type(exc).__name__}: {exc}")
    return rows, "; ".join(errors)


def scan_library(
    root: Path,
    config: dict[str, Any],
    filter_mode: str,
    folder_filter: str,
) -> list[dict[str, Any]]:
    mig = config.get("migration_plus_links", {})
    marker = clean(mig.get("minus_marker")) or "֎"
    excluded = {
        clean(name).casefold()
        for name in mig.get("exclude_dirs", [])
        if clean(name)
    }

    result: list[dict[str, Any]] = []
    remote_to_items: dict[str, list[dict[str, Any]]] = defaultdict(list)
    slug_cfg = config.get("plus_upload", {}).get("slug", {})
    public_base = clean(config.get("plus_upload", {}).get("public_base_url")).rstrip("/")

    for current, dirs, files in os.walk(root):
        current_path = Path(current)

        dirs[:] = [
            d for d in dirs
            if d.casefold() not in excluded
        ]

        if folder_filter and folder_filter.casefold() not in str(current_path).casefold():
            continue

        mp3s = sorted(
            [
                current_path / name
                for name in files
                if Path(name).suffix.lower() == ".mp3"
            ],
            key=lambda p: p.name.casefold(),
        )
        if not mp3s:
            continue

        minuses = [p for p in mp3s if marker in p.name]
        if not minuses:
            continue

        pluses = [p for p in mp3s if marker not in p.name]
        item: dict[str, Any] = {
            "folder": str(current_path),
            "status": "",
            "plus": "",
            "remote_name": "",
            "url": "",
            "minuses": [str(p) for p in minuses],
            "minus_count": len(minuses),
            "plus_candidates": [str(p) for p in pluses],
            "old_woas": [],
            "note": "",
        }

        if len(pluses) == 0:
            item["status"] = "no_plus"
            item["note"] = "Рядом с минусовками нет MP3 без ֎."
            result.append(item)
            continue

        if len(pluses) > 1:
            item["status"] = "ambiguous_plus"
            item["note"] = "Рядом несколько MP3 без ֎; автоматический выбор запрещён."
            result.append(item)
            continue

        plus = pluses[0]
        item["plus"] = str(plus)

        if not matches_filter(plus, filter_mode):
            item["status"] = "filtered_out"
            result.append(item)
            continue

        remote_name = slugify_remote_name(plus, slug_cfg)
        item["remote_name"] = remote_name
        item["url"] = public_base + "/" + quote(remote_name)

        old_woas, tag_error = read_minus_woas(minuses)
        item["old_woas"] = old_woas
        if tag_error:
            item["status"] = "tag_read_error"
            item["note"] = tag_error
            result.append(item)
            continue

        item["status"] = "ready"
        result.append(item)
        remote_to_items[remote_name].append(item)

    for remote_name, items in remote_to_items.items():
        distinct_pluses = {item["plus"] for item in items}
        if len(distinct_pluses) > 1:
            for item in items:
                item["status"] = "slug_collision"
                item["note"] = (
                    f"Одинаковое FTP-имя {remote_name!r} получилось "
                    f"для {len(distinct_pluses)} разных плюсов."
                )

    return result


def summary(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for item in items:
        counts[item["status"]] += 1
        counts["minuses_total"] += int(item.get("minus_count", 0))
        if item["status"] == "ready":
            counts["ready_minuses"] += int(item.get("minus_count", 0))
    return dict(sorted(counts.items()))


def write_report(
    items: list[dict[str, Any]],
    config: dict[str, Any],
    mode: str,
    filter_mode: str,
) -> tuple[Path, Path]:
    report_rel = Path(
        config.get("migration_plus_links", {}).get(
            "report_dir",
            "data/migration_plus_links",
        )
    )
    report_dir = APP_ROOT / report_rel
    report_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"{mode}_{filter_mode}_{stamp}"
    json_path = report_dir / f"{stem}.json"
    csv_path = report_dir / f"{stem}.csv"

    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "filter": filter_mode,
        "summary": summary(items),
        "items": items,
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "status",
                "folder",
                "plus",
                "remote_name",
                "url",
                "minus_count",
                "minuses",
                "old_woas",
                "note",
            ],
            delimiter=";",
        )
        writer.writeheader()
        for item in items:
            writer.writerow(
                {
                    "status": item.get("status", ""),
                    "folder": item.get("folder", ""),
                    "plus": item.get("plus", ""),
                    "remote_name": item.get("remote_name", ""),
                    "url": item.get("url", ""),
                    "minus_count": item.get("minus_count", 0),
                    "minuses": "\n".join(item.get("minuses", [])),
                    "old_woas": "\n".join(
                        f"{x.get('file', '')} => {x.get('woas', '')}"
                        for x in item.get("old_woas", [])
                    ),
                    "note": item.get("note", ""),
                }
            )

    return json_path, csv_path


def write_problem_report(
    items: list[dict[str, Any]],
    config: dict[str, Any],
) -> Path:
    report_rel = Path(
        config.get("migration_plus_links", {}).get(
            "report_dir",
            "data/migration_plus_links",
        )
    )
    report_dir = APP_ROOT / report_rel
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / "ПРОБЛЕМНЫЕ ПАПКИ.txt"

    problem_statuses = {"no_plus", "ambiguous_plus", "slug_collision", "tag_read_error"}
    problems = [item for item in items if item.get("status") in problem_statuses]

    def problem_priority(item: dict[str, Any]) -> tuple[int, str]:
        minus_count = int(item.get("minus_count", 0))
        plus_count = len(item.get("plus_candidates", []))
        status = item.get("status", "")
        if status == "ambiguous_plus" and minus_count > 1 and plus_count > 1:
            priority = 0
        elif status == "ambiguous_plus":
            priority = 1
        elif status == "no_plus":
            priority = 2
        else:
            priority = 3
        return priority, str(item.get("folder", "")).casefold()

    problems.sort(key=problem_priority)
    multiple_both = [
        item for item in problems
        if item.get("status") == "ambiguous_plus"
        and int(item.get("minus_count", 0)) > 1
        and len(item.get("plus_candidates", [])) > 1
    ]

    lines = [
        "ПРОБЛЕМНЫЕ ПАПКИ — миграция плюсов",
        f"Сформировано: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "ВАЖНО: эти папки скрипт НЕ МИГРИРУЕТ автоматически.",
        "Сначала исправь файлы вручную и снова запусти ПРОВЕРКА.",
        "",
        f"Всего проблемных папок: {len(problems)}",
        f"Без плюса: {sum(1 for x in problems if x.get('status') == 'no_plus')}",
        f"Несколько кандидатов на плюс: {sum(1 for x in problems if x.get('status') == 'ambiguous_plus')}",
        f"Особо неоднозначные (несколько минусов + несколько плюсов): {len(multiple_both)}",
        "",
    ]

    for item in problems:
        status = item.get("status", "")
        minus_count = int(item.get("minus_count", 0))
        plus_count = len(item.get("plus_candidates", []))
        title = {
            "no_plus": "НЕТ ПЛЮСА",
            "ambiguous_plus": "НЕСКОЛЬКО ПЛЮСОВ",
            "slug_collision": "КОЛЛИЗИЯ ИМЕНИ",
            "tag_read_error": "ОШИБКА ЧТЕНИЯ ТЕГОВ",
        }.get(status, status)
        if status == "ambiguous_plus" and minus_count > 1 and plus_count > 1:
            title = "НЕСКОЛЬКО МИНУСОВ + НЕСКОЛЬКО ПЛЮСОВ"

        lines.append("=" * 88)
        lines.append(f"[{title}] {item.get('folder', '')}")
        lines.append(f"  Минусов ֎: {minus_count}")
        lines.append(f"  Кандидатов на плюс: {plus_count}")
        lines.append("")

        if item.get("minuses"):
            lines.append("  МИНУСЫ:")
            for minus in item.get("minuses", []):
                lines.append(f"    - {Path(minus).name}")

        if item.get("plus_candidates"):
            lines.append("  MP3 БЕЗ ֎ — КАНДИДАТЫ НА ПЛЮС:")
            for plus in item.get("plus_candidates", []):
                lines.append(f"    - {Path(plus).name}")

        note = clean(item.get("note"))
        if note:
            lines.append(f"  ПРИЧИНА: {note}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def load_ftp_password(config: dict[str, Any]) -> str:
    cfg = config.get("plus_upload", {})
    secret_path = APP_ROOT / cfg.get("secret_file", "secrets.local.json")
    key = clean(cfg.get("password_key")) or "ftp_password"

    if secret_path.is_file():
        try:
            value = clean(json.loads(secret_path.read_text(encoding="utf-8")).get(key))
            if value:
                return value
        except Exception:
            pass

    return getpass.getpass("FTP-пароль: ")


class FTPRetriesExhausted(RuntimeError):
    def __init__(self, stage: str, attempts: int, exc: BaseException):
        self.stage = stage
        self.attempts = attempts
        self.original = exc
        super().__init__(
            f"FTP [{stage}]: {type(exc).__name__}: {exc}; "
            f"исчерпано попыток: {attempts}"
        )


class FTPUploader:
    def __init__(self, config: dict[str, Any], password: str):
        self.cfg = config.get("plus_upload", {})
        self.mig_cfg = config.get("migration_plus_links", {})
        self.password = password
        self.ftp: ftplib.FTP | None = None
        self.stage = "инициализация"

    def close(self) -> None:
        if self.ftp is None:
            return
        try:
            self.ftp.quit()
        except Exception:
            try:
                self.ftp.close()
            except Exception:
                pass
        self.ftp = None

    def connect(self) -> ftplib.FTP:
        self.close()
        ftp = ftplib.FTP()

        self.stage = "подключение к серверу"
        ftp.connect(
            clean(self.cfg.get("server")),
            int(self.cfg.get("port", 21)),
            timeout=int(self.cfg.get("timeout_seconds", 60)),
        )

        self.stage = "авторизация"
        ftp.login(clean(self.cfg.get("username")), self.password)
        ftp.set_pasv(bool(self.cfg.get("passive", True)))

        self.stage = "переход в FTP-папку"
        ftp_ensure_dir(ftp, clean(self.cfg.get("remote_dir")))

        self.ftp = ftp
        self.stage = "готово"
        return ftp

    def ensure(self) -> ftplib.FTP:
        if self.ftp is None:
            return self.connect()
        try:
            self.stage = "проверка соединения"
            self.ftp.voidcmd("NOOP")
            self.stage = "готово"
            return self.ftp
        except Exception:
            return self.connect()

    def _upload_stream(
        self,
        ftp: ftplib.FTP,
        local_path: Path,
        remote_name: str,
        local_size: int,
    ) -> int:
        block_size = max(
            8 * 1024,
            int(self.mig_cfg.get("ftp_upload_block_size_kb", 64)) * 1024,
        )
        progress_interval = max(
            0.2,
            float(self.mig_cfg.get("ftp_progress_interval_seconds", 1.0)),
        )
        data_timeout = max(
            5,
            int(
                self.mig_cfg.get(
                    "ftp_data_timeout_seconds",
                    self.cfg.get("timeout_seconds", 60),
                )
            ),
        )

        ftp.voidcmd("TYPE I")
        self.stage = "открытие FTP data-соединения"

        sent = 0
        started = time.monotonic()
        last_progress = started - progress_interval
        progress_shown = False
        total_mb = local_size / 1024 / 1024

        try:
            with local_path.open("rb") as source:
                with ftp.transfercmd(f"STOR {remote_name}") as conn:
                    conn.settimeout(data_timeout)

                    while True:
                        chunk = source.read(block_size)
                        if not chunk:
                            break

                        self.stage = (
                            "передача данных "
                            f"({sent / 1024 / 1024:.1f}/{total_mb:.1f} МБ)"
                        )
                        conn.sendall(chunk)
                        sent += len(chunk)

                        now = time.monotonic()
                        if (
                            now - last_progress >= progress_interval
                            or sent >= local_size
                        ):
                            elapsed = max(now - started, 0.001)
                            speed_kbps = sent / 1024 / elapsed
                            percent = (
                                min(100.0, sent * 100.0 / local_size)
                                if local_size
                                else 100.0
                            )
                            print(
                                "\r    ↑ "
                                f"{sent / 1024 / 1024:.1f}/{total_mb:.1f} МБ "
                                f"({percent:5.1f}%) · {speed_kbps:.0f} КБ/с",
                                end="",
                                flush=True,
                            )
                            progress_shown = True
                            last_progress = now
        finally:
            if progress_shown:
                print()

        self.stage = (
            "ожидание ответа FTP-сервера после передачи "
            f"({sent / 1024 / 1024:.1f}/{total_mb:.1f} МБ)"
        )
        ftp.voidresp()
        return sent

    def upload(
        self,
        local_path: Path,
        remote_name: str,
        overwrite: bool,
    ) -> tuple[str, int | None]:
        self.stage = "подготовка соединения"
        ftp = self.ensure()
        local_size = local_path.stat().st_size

        self.stage = "проверка существующего файла"
        exists = ftp_remote_exists(ftp, remote_name)

        self.stage = "проверка размера существующего файла"
        remote_size = ftp_remote_size(ftp, remote_name) if exists is True else None

        if exists is True and remote_size == local_size:
            return "reused_same_size", remote_size

        if exists is None and not overwrite:
            raise RuntimeError(
                f"FTP-сервер не смог надёжно проверить существование {remote_name}. "
                "Без --overwrite-remote файл не трогаю."
            )

        if exists is True and remote_size != local_size and not overwrite:
            raise RuntimeError(
                f"На FTP уже есть {remote_name} размером {remote_size}, "
                f"а локальный файл {local_size}. Нужен --overwrite-remote."
            )

        temp_name = f".__migrate__{remote_name}"

        self.stage = "проверка временного файла"
        temp_exists = ftp_remote_exists(ftp, temp_name)
        temp_existing_size = (
            ftp_remote_size(ftp, temp_name)
            if temp_exists is True
            else None
        )

        if temp_exists is True and temp_existing_size == local_size:
            print(
                "  ↻ найден полностью переданный временный файл; "
                "повторная загрузка не нужна."
            )
        else:
            if temp_exists is True and temp_existing_size:
                print(
                    "  ↻ найден незавершённый временный файл: "
                    f"{temp_existing_size / 1024 / 1024:.1f}/"
                    f"{local_size / 1024 / 1024:.1f} МБ; "
                    "загрузка начнётся заново."
                )

            self.stage = "очистка временного файла"
            try:
                ftp.delete(temp_name)
            except ftplib.error_perm:
                pass

            self._upload_stream(
                ftp,
                local_path,
                temp_name,
                local_size,
            )

        self.stage = "проверка размера временного файла"
        temp_size = ftp_remote_size(ftp, temp_name)
        if temp_size is not None and temp_size != local_size:
            raise RuntimeError(
                f"Размер временного FTP-файла не совпал: "
                f"{temp_size} != {local_size}"
            )

        if exists is True:
            self.stage = "удаление старого файла"
            try:
                ftp.delete(remote_name)
            except ftplib.error_perm as exc:
                if str(exc)[:3] != "550":
                    raise

        self.stage = "переименование временного файла"
        ftp.rename(temp_name, remote_name)

        self.stage = "проверка итогового файла"
        final_size = ftp_remote_size(ftp, remote_name)
        if final_size is not None and final_size != local_size:
            raise RuntimeError(
                f"Размер итогового FTP-файла не совпал: "
                f"{final_size} != {local_size}"
            )

        self.stage = "готово"
        return "uploaded", final_size


def http_check(url: str, timeout: int) -> tuple[bool, str]:
    headers = {"User-Agent": "Andrey-Repertoire-Migration/1.0"}

    try:
        request = Request(url, method="HEAD", headers=headers)
        with urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            return 200 <= status < 400, f"HTTP {status}"
    except HTTPError as exc:
        if exc.code not in {403, 405, 501}:
            return False, f"HTTP {exc.code}"
    except URLError as exc:
        return False, str(exc.reason)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"

    try:
        headers["Range"] = "bytes=0-0"
        request = Request(url, method="GET", headers=headers)
        with urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            return 200 <= status < 400, f"HTTP {status}"
    except HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except URLError as exc:
        return False, str(exc.reason)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def write_woas(path: Path, url: str) -> tuple[str, str]:
    tags = load_tags(path)
    old = read_url(tags, "WOAS")
    if old == url:
        return "already_matching", old

    backup = copy.deepcopy(tags)
    try:
        write_field(tags, WOAS_SPEC, url)
        tags.save(path, v2_version=4)
        verify = load_tags(path)
        actual = read_url(verify, "WOAS")
        if actual != url:
            raise RuntimeError(f"WOAS verification failed: {actual!r} != {url!r}")
        return "updated", old
    except Exception:
        backup.save(path, v2_version=4)
        raise


def apply_items(
    items: list[dict[str, Any]],
    config: dict[str, Any],
    overwrite_remote: bool,
) -> bool:
    ready = [item for item in items if item["status"] == "ready"]
    if not ready:
        print("Нет однозначных элементов для применения.")
        return False

    password = load_ftp_password(config)
    if not password:
        raise RuntimeError("FTP-пароль не задан.")

    uploader = FTPUploader(config, password)
    timeout = int(
        config.get("migration_plus_links", {}).get(
            "http_check_timeout_seconds",
            config.get("plus_upload", {}).get("http_check_timeout_seconds", 10),
        )
    )
    mig_cfg = config.get("migration_plus_links", {})
    do_http = bool(mig_cfg.get("http_check", True))
    skip_existing_working = bool(
        mig_cfg.get("skip_existing_working_woas", True)
    )
    ftp_retry_attempts = max(1, int(mig_cfg.get("ftp_retry_attempts", 3)))
    ftp_retry_delay = max(0.0, float(mig_cfg.get("ftp_retry_delay_seconds", 2)))
    abort_batch_on_ftp_failure = bool(
        mig_cfg.get("abort_batch_on_ftp_retry_exhausted", True)
    )
    existing_http_cache: dict[str, tuple[bool, str]] = {}
    batch_aborted = False

    try:
        total = len(ready)
        for index, item in enumerate(ready, 1):
            plus = Path(item["plus"])
            remote_name = item["remote_name"]
            url = item["url"]
            print(f"[{index}/{total}] {plus.name}")

            try:
                old_woas_by_file = {
                    str(row.get("file", "")): clean(row.get("woas"))
                    for row in item.get("old_woas", [])
                }
                skipped_results: list[dict[str, str]] = []
                pending_minuses: list[str] = []

                for minus_text in item["minuses"]:
                    old_url = old_woas_by_file.get(str(minus_text), "")
                    if skip_existing_working and old_url:
                        if old_url not in existing_http_cache:
                            existing_http_cache[old_url] = http_check(old_url, timeout)
                        old_ok, old_detail = existing_http_cache[old_url]
                        if old_ok:
                            skipped_results.append(
                                {
                                    "file": str(minus_text),
                                    "status": "skipped_working_woas",
                                    "old_woas": old_url,
                                    "new_woas": old_url,
                                    "http_check": old_detail,
                                }
                            )
                            continue
                    pending_minuses.append(str(minus_text))

                if not pending_minuses:
                    item["minus_results"] = skipped_results
                    item["status"] = "skipped_existing"
                    item["note"] = (
                        "Все минусовки уже содержат рабочую WOAS-ссылку; "
                        "FTP и теги не изменялись."
                    )
                    print(
                        f"  ↷ пропущено: рабочая WOAS уже есть "
                        f"у {len(skipped_results)} минусовок."
                    )
                    continue

                action = ""
                remote_size: int | None = None
                for attempt in range(1, ftp_retry_attempts + 1):
                    try:
                        action, remote_size = uploader.upload(
                            plus,
                            remote_name,
                            overwrite=overwrite_remote,
                        )
                        break
                    except (
                        TimeoutError,
                        ConnectionError,
                        EOFError,
                        OSError,
                        ftplib.error_temp,
                    ) as exc:
                        failed_stage = uploader.stage
                        uploader.close()
                        if attempt >= ftp_retry_attempts:
                            raise FTPRetriesExhausted(
                                failed_stage,
                                ftp_retry_attempts,
                                exc,
                            ) from exc
                        print(
                            f"  ! FTP [{failed_stage}] "
                            f"{type(exc).__name__}: {exc}; "
                            f"повтор {attempt + 1}/{ftp_retry_attempts} "
                            "после переподключения."
                        )
                        if ftp_retry_delay:
                            time.sleep(ftp_retry_delay)

                item["ftp_action"] = action
                item["remote_size"] = remote_size

                if do_http:
                    ok, detail = http_check(url, timeout)
                    existing_http_cache[url] = (ok, detail)
                    item["http_check"] = detail
                    if not ok:
                        item["status"] = "http_error"
                        item["note"] = (
                            "FTP-файл загружен/найден, но публичный URL "
                            f"не прошёл проверку: {detail}"
                        )
                        item["minus_results"] = skipped_results
                        print(f"  ! URL не работает: {detail}")
                        continue

                minus_results: list[dict[str, str]] = list(skipped_results)
                had_error = False
                updated_count = 0
                for minus_text in pending_minuses:
                    minus = Path(minus_text)
                    try:
                        state, old = write_woas(minus, url)
                        if state in {"updated", "already_matching"}:
                            updated_count += 1
                        minus_results.append(
                            {
                                "file": str(minus),
                                "status": state,
                                "old_woas": old,
                                "new_woas": url,
                            }
                        )
                    except Exception as exc:
                        had_error = True
                        minus_results.append(
                            {
                                "file": str(minus),
                                "status": "error",
                                "old_woas": old_woas_by_file.get(str(minus), ""),
                                "new_woas": url,
                                "error": f"{type(exc).__name__}: {exc}",
                            }
                        )

                item["minus_results"] = minus_results
                if had_error:
                    item["status"] = "partial_woas_error"
                    print("  ! Не всем минусовкам удалось записать WOAS.")
                else:
                    item["status"] = "done"
                    skipped_count = len(skipped_results)
                    suffix = (
                        f"; уже готовых пропущено: {skipped_count}"
                        if skipped_count
                        else ""
                    )
                    print(
                        f"  ✓ обновлено минусовок: {updated_count}{suffix} → {url}"
                    )

            except FTPRetriesExhausted as exc:
                item["status"] = "apply_error"
                item["note"] = str(exc)
                print(f"  ! {item['note']}")

                if abort_batch_on_ftp_failure:
                    batch_aborted = True
                    for remaining in ready[index:]:
                        if remaining.get("status") == "ready":
                            remaining["status"] = "not_run_after_ftp_abort"
                            remaining["note"] = (
                                "Не запускалось: пакет остановлен после "
                                "исчерпания FTP-повторов на предыдущем файле."
                            )
                    print(
                        "  ⛔ FTP не восстановился после всех повторов. "
                        "Останавливаю весь APPLY, следующие файлы не трогаю."
                    )
                    break

            except Exception as exc:
                item["status"] = "apply_error"
                item["note"] = f"{type(exc).__name__}: {exc}"
                print(f"  ! {item['note']}")

    finally:
        uploader.close()

    return batch_aborted


def print_summary(items: list[dict[str, Any]]) -> None:
    counts = summary(items)
    print()
    print("Сводка:")
    for key, value in counts.items():
        print(f"  {key}: {value}")


def main() -> int:
    args = parse_args()
    config = load_config()
    mig_cfg = config.get("migration_plus_links", {})

    root = Path(args.root or config.get("paths", {}).get("library_root", ""))
    if not root.is_dir():
        print(f"Корень репертуара не найден: {root}")
        return 2

    filter_mode = args.filter or clean(mig_cfg.get("default_filter")) or "all"
    items = scan_library(root, config, filter_mode, args.folder)
    print_summary(items)

    dry_json, dry_csv = write_report(
        items,
        config,
        mode="dry-run",
        filter_mode=filter_mode,
    )
    problem_path = write_problem_report(items, config)
    print(f"\nDry-run JSON: {dry_json}")
    print(f"Dry-run CSV:  {dry_csv}")
    print(f"Проблемные папки: {problem_path}")

    if not args.apply:
        print(
            "\nНичего не загружено и теги не изменены. "
            "Для реальной миграции запусти с --apply."
        )
        return 0

    problem_statuses = {"no_plus", "ambiguous_plus", "slug_collision", "tag_read_error"}
    problems = [item for item in items if item.get("status") in problem_statuses]

    ready_folders = sum(1 for x in items if x["status"] == "ready")
    ready_minuses = sum(
        int(x.get("minus_count", 0))
        for x in items
        if x["status"] == "ready"
    )
    print(
        f"\nБудет автоматически обработано папок: {ready_folders}; "
        f"минусовок WOAS: {ready_minuses}."
    )
    if problems:
        print(
            f"Проблемных папок будет пропущено без любых изменений: {len(problems)}."
        )
        print(f"Список для ручной обработки: {problem_path}")

    if not args.yes:
        answer = input("Для продолжения введи APPLY: ").strip()
        if answer != "APPLY":
            print("Отменено.")
            return 0

    batch_aborted = apply_items(
        items,
        config,
        overwrite_remote=args.overwrite_remote
        or bool(mig_cfg.get("overwrite_remote_if_size_diff", False)),
    )

    print_summary(items)
    apply_json, apply_csv = write_report(
        items,
        config,
        mode="apply",
        filter_mode=filter_mode,
    )
    print(f"\nApply JSON: {apply_json}")
    print(f"Apply CSV:  {apply_csv}")

    if batch_aborted:
        print(
            "\nМиграция аварийно остановлена из-за недоступного FTP. "
            "Уже обработанные файлы сохранены; следующие не запускались."
        )
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
