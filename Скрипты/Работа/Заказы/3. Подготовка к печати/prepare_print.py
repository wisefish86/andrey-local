import os
import sys
import pathlib
import shutil
import logging

# ================= НАСТРОЙКИ =================
ITEMS_FILENAME = "- Позиции заказа.txt"
LOG_FILENAME = "prepare_print.log"        # файл лога (в папке скрипта)
# =============================================

# --- Настройка логирования ---
script_path = pathlib.Path(__file__).resolve()
script_dir = script_path.parent
log_file = script_dir / LOG_FILENAME

logger = logging.getLogger('prepare_print')
logger.setLevel(logging.DEBUG)

file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='a')
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

logger.info("=== Prepare print started ===")

# --- Получение целевой папки (из аргумента или текущая) ---
if len(sys.argv) > 1:
    raw_arg = sys.argv[1]
    logger.debug(f"Raw argv[1]: {repr(raw_arg)}")
    folder_str = raw_arg.strip().strip('"').strip()
    folder = pathlib.Path(folder_str)
    if not folder.is_absolute():
        folder = (script_dir / folder).resolve()
else:
    # Если аргумент не передан, работаем в текущей папке
    folder = script_dir
    logger.info("No target folder passed, using current directory.")

logger.info(f"Working folder: {folder}")

if not folder.exists() or not folder.is_dir():
    logger.error("Target folder does not exist or is not a directory.")
    input("Press Enter...")
    sys.exit(1)

# --- Удаление файла "Позиции заказа.txt" ---
items_file = folder / ITEMS_FILENAME
if items_file.exists():
    try:
        items_file.unlink()
        logger.info(f"✅ Removed {ITEMS_FILENAME}")
    except Exception as e:
        logger.error(f"❌ Error removing {ITEMS_FILENAME}: {e}")
else:
    logger.info(f"ℹ️ {ITEMS_FILENAME} not found, nothing to remove.")

# --- Поиск всех CDR-файлов ---
cdr_files = list(folder.glob("*.cdr")) + list(folder.glob("*.CDR"))
if not cdr_files:
    logger.warning("No CDR files found.")
    sys.exit(0)

logger.info(f"Found {len(cdr_files)} CDR file(s).")

# --- Создание копий с префиксом "[на печать] " и открытие последней созданной ---
created_copy = None
for cdr in cdr_files:
    # Формируем имя копии: "[на печать] исходное_имя.cdr"
    new_name = "[на печать] " + cdr.name
    new_path = folder / new_name

    try:
        # Копируем (если файл уже есть, перезаписываем)
        shutil.copy2(str(cdr), str(new_path))
        logger.info(f"✅ Created copy: {new_name}")
        created_copy = new_path  # запоминаем последнюю созданную копию
    except Exception as e:
        logger.error(f"❌ Error copying {cdr.name}: {e}")

# --- Если была создана хотя бы одна копия, открываем её ---
if created_copy is not None:
    try:
        os.startfile(str(created_copy))
        logger.info(f"Opened copy: {created_copy.name}")
    except Exception as e:
        logger.error(f"Cannot open copy: {e}")
else:
    logger.warning("No copies were created, nothing to open.")

logger.info("=== Prepare print finished ===")