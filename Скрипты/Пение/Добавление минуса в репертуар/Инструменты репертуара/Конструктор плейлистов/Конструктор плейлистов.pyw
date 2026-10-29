"""Double-click entrypoint for the read-only setlist editor on Windows."""
from pathlib import Path
import os
import subprocess
import sys


HERE = Path(__file__).resolve().parent


def show(message, flags=0x40):
    if os.name == "nt":
        import ctypes
        return ctypes.windll.user32.MessageBoxW(None, str(message), "Конструктор плейлистов", flags)
    print(message)
    return 0


def main():
    missing = []
    for module in ("PySide6", "mutagen"):
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    if missing:
        if show("Не установлены библиотеки: " + ", ".join(missing) +
                "\n\nУстановить через pip? Нужен интернет.", 0x24) != 6:
            return
        completed = subprocess.run(
            [sys.executable, "-m", "pip", "install", *missing],
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        if completed.returncode != 0:
            show("Не удалось установить зависимости. Проверь установленный Python.", 0x10)
            return
    sys.path.insert(0, str(HERE))
    try:
        from app import main as start
        start()
    except Exception as exc:
        show("Ошибка запуска:\n\n" + str(exc), 0x10)
        raise


if __name__ == "__main__":
    main()
