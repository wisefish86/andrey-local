import os
import sys
import shutil
import subprocess
import pathlib
import logging
from datetime import datetime

# ================= НАСТРОЙКИ =================
ARCHIVE_DIR = pathlib.Path(r"D:\YandexDisk\Проекты\Работа в Компас\Заказы\# Заказы. Архив (залил на ЯД)")
PARENT_DIR  = pathlib.Path(r"D:\YandexDisk\Проекты\Работа в Компас\Заказы")
LOG_FILENAME = "cleanup_order.log"

PNG_PREFIX = "Заказ "
ZIP_PREFIX = "Заказ "
TASK_FILE_TEMPLATE = "[закрыть задачу] {name}.txt"

# Пакеты, которые нужны скрипту (имя для pip -> имя для import)
REQUIRED_PACKAGES = {
    "send2trash": "send2trash",
}
# =============================================

# --- Логирование ---
script_path = pathlib.Path(__file__).resolve()
script_dir = script_path.parent
log_file = script_dir / LOG_FILENAME

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8', mode='a'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('cleanup_order')

logger.info("=== Cleanup order started ===")


def _pip_install(package_name, extra_args=None):
    """Пробует установить пакет через python -m pip. Возвращает True/False."""
    cmd = [sys.executable, "-m", "pip", "install", package_name]
    if extra_args:
        cmd.extend(extra_args)
    logger.info(f"Запуск: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        logger.debug(f"pip stdout:\n{result.stdout}")
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Не удалось запустить pip: {e}")
        return False


def ensure_package(pip_name, import_name):
    """
    Проверяет, что пакет импортируется. Если нет — пробует установить
    сначала в пользовательское окружение (--user), потом глобально.
    Возвращает True, если пакет доступен после всех попыток.
    """
    try:
        __import__(import_name)
        logger.info(f"Пакет '{import_name}' уже установлен.")
        return True
    except ImportError:
        logger.warning(f"Пакет '{import_name}' не найден. Пробую установить...")

    # Попытка 1: --user (не требует прав администратора)
    if _pip_install(pip_name, ["--user"]):
        try:
            import importlib
            importlib.invalidate_caches()
            __import__(import_name)
            logger.info(f"Пакет '{import_name}' установлен (--user).")
            return True
        except ImportError:
            logger.warning("После --user импорт всё ещё не работает, пробую глобально...")

    # Попытка 2: глобально
    if _pip_install(pip_name):
        try:
            import importlib
            importlib.invalidate_caches()
            __import__(import_name)
            logger.info(f"Пакет '{import_name}' установлен глобально.")
            return True
        except ImportError:
            logger.error(f"Пакет '{import_name}' всё ещё не импортируется.")
            return False

    return False


# --- Проверка и автоустановка зависимостей ---
for pip_name, import_name in REQUIRED_PACKAGES.items():
    if not ensure_package(pip_name, import_name):
        print()
        print(f"!!! Не удалось установить библиотеку '{pip_name}'.")
        print("Проверьте интернет и права, либо установите вручную:")
        print(f"    {sys.executable} -m pip install {pip_name}")
        sys.exit(1)

# Теперь безопасно импортируем
from send2trash import send2trash


# --- Получение целевой папки ---
if len(sys.argv) > 1:
    raw_arg = sys.argv[1]
    folder_str = raw_arg.strip().strip('"').strip()
    folder = pathlib.Path(folder_str)
    if not folder.is_absolute():
        folder = (script_dir / folder).resolve()
else:
    logger.error("Не передана целевая папка.")
    sys.exit(1)

logger.info(f"Рабочая папка: {folder}")

if not folder.exists() or not folder.is_dir():
    logger.error("Целевая папка не существует или не является папкой.")
    sys.exit(1)

# --- Проверка архивной папки ---
if not ARCHIVE_DIR.exists() or not ARCHIVE_DIR.is_dir():
    logger.error(f"Архивная папка не найдена: {ARCHIVE_DIR}")
    print(f"!!! Архивная папка не найдена: {ARCHIVE_DIR}")
    sys.exit(1)

# --- Поиск PNG и ZIP ---
png_files = []
zip_files = []
for entry in folder.iterdir():
    if not entry.is_file():
        continue
    if entry.suffix.lower() == ".png" and entry.name.startswith(PNG_PREFIX):
        png_files.append(entry)
    elif entry.suffix.lower() == ".zip" and entry.name.startswith(ZIP_PREFIX):
        zip_files.append(entry)

logger.info(f"Найдено PNG: {len(png_files)}")
for f in png_files:
    logger.info(f"  PNG: {f.name}")
logger.info(f"Найдено ZIP: {len(zip_files)}")
for f in zip_files:
    logger.info(f"  ZIP: {f.name}")

# --- Проверка обязательных условий ---
errors = []
if not png_files:
    errors.append(f'Не найден ни один PNG, начинающийся с "{PNG_PREFIX}"')
if not zip_files:
    errors.append(f'Не найден ни один ZIP, начинающийся с "{ZIP_PREFIX}"')

if errors:
    logger.error("Ошибка. Ничего не изменено:")
    for e in errors:
        logger.error(f"  - {e}")
    print()
    print("!!! ОШИБКА. Ничего не скопировано и не удалено:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)

# --- Подтверждение ---
print()
print("Будет выполнено:")
print(f"  1. Скопировать {len(png_files)} PNG в:")
print(f"     {ARCHIVE_DIR}")
for f in png_files:
    print(f"       - {f.name}")
print(f"  2. Удалить БЕЗ корзины {len(zip_files)} ZIP:")
for f in zip_files:
    print(f"       - {f.name}")
print(f"  3. Удалить В КОРЗИНУ папку:")
print(f"       {folder}")
task_path = PARENT_DIR / TASK_FILE_TEMPLATE.format(name=folder.name)
print(f"  4. Создать файл-маркер:")
print(f"       {task_path}")
print()

answer = input("Продолжить? (1/да — подтвердить, Enter — отмена): ").strip().lower()
if answer not in ("1", "да"):
    logger.info(f"Отменено пользователем (ответ: '{answer}').")
    print("Отменено. Ничего не изменено.")
    sys.exit(0)

# --- Шаг 1: копирование PNG ---
try:
    for f in png_files:
        dest = ARCHIVE_DIR / f.name
        shutil.copy2(f, dest)
        logger.info(f"Скопирован: {f.name} -> {dest}")
except Exception as e:
    logger.error(f"Ошибка копирования PNG: {e}")
    print(f"!!! Ошибка копирования PNG: {e}")
    sys.exit(1)

# --- Шаг 2: удаление ZIP без корзины ---
try:
    for f in zip_files:
        os.remove(f)
        logger.info(f"Удалён ZIP без корзины: {f.name}")
except Exception as e:
    logger.error(f"Ошибка удаления ZIP: {e}")
    print(f"!!! Ошибка удаления ZIP: {e}")
    sys.exit(1)

# --- Шаг 3: удаление папки в корзину ---
try:
    send2trash(str(folder))
    logger.info(f"Папка отправлена в корзину: {folder}")
except Exception as e:
    logger.error(f"Ошибка удаления папки в корзину: {e}")
    print(f"!!! Ошибка удаления папки в корзину: {e}")
    sys.exit(1)

# --- Шаг 4: создание txt-маркера ---
try:
    task_file = PARENT_DIR / TASK_FILE_TEMPLATE.format(name=folder.name)
    with open(task_file, "w", encoding="utf-8") as f:
        f.write(f"Заказ закрыт: {datetime.now().isoformat(timespec='seconds')}\n")
        f.write(f"Папка: {folder.name}\n")
    logger.info(f"Создан файл-маркер: {task_file}")
except Exception as e:
    logger.error(f"Ошибка создания txt-маркера: {e}")
    print(f"!!! Ошибка создания txt-маркера: {e}")
    sys.exit(1)

print()
print("Готово.")
logger.info("=== Cleanup order finished ===")