from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
SRC = APP_ROOT / "src"


def msgbox(text: str, title: str, flags: int = 0x40) -> int:
    return ctypes.windll.user32.MessageBoxW(None, text, title, flags)


def ensure_dependencies() -> bool:
    missing = []
    try:
        import mutagen  # noqa: F401
    except Exception:
        missing.append("mutagen")
    try:
        import PySide6  # noqa: F401
    except Exception:
        missing.append("PySide6")
    if not missing:
        return True

    answer = msgbox(
        "Для программы не хватает библиотек:\n\n"
        + ", ".join(missing)
        + "\n\nУстановить автоматически через pip?",
        "Первый запуск",
        0x24,
    )
    if answer != 6:
        return False

    creationflags = 0x08000000 if os.name == "nt" else 0
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", *missing],
        creationflags=creationflags,
    )
    if result.returncode != 0:
        msgbox("Не удалось установить зависимости. Проверь Python/pip.", "Ошибка", 0x10)
        return False
    return True


def main():
    if not ensure_dependencies():
        return
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    try:
        from app import run
        run()
    except Exception as exc:
        msgbox(str(exc), "Ошибка запуска", 0x10)


if __name__ == "__main__":
    main()
