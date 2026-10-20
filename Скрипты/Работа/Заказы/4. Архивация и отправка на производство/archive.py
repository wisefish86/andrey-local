import os
import sys
import pathlib
import zipfile
import logging
import webbrowser
import urllib.parse
import json
from datetime import datetime

# Попытка импортировать модули для проверки версии
try:
    import win32com.client
    import re
    HAS_PYWIN32 = True
except ImportError:
    HAS_PYWIN32 = False

# ================= НАСТРОЙКИ =================
ITEMS_FILENAME = "- Позиции заказа.txt"          # оставляем в папке и в архиве
EXCLUDE_PATTERN = "- Действия с заказом после заверения"
EXCLUDE_EXTENSIONS = ['.ini', '.ico']            # расширения, которые не включать в архив
EXCLUDE_FILES = []                                # конкретные файлы для исключения (нет)
EXCLUDE_FILE_PREFIXES = ["~$", ".~lock."]        # временные файлы Office/LibreOffice
EXCLUDE_SUFFIXES = [".tmp"]                      # временные расширения
CDR_PREFIX = "[на печать]"                        # префикс для проверяемых файлов
CHECK_CDR_VERSION = True                          # проверять ли версию CorelDRAW
LOG_FILENAME = "archive.log"

EMAILS_FILENAME = "- Emails для согласования.txt"
ORDER_JSON_FILENAME = "- Данные заказа.json"
LEGACY_JSON_FILENAME = "- Позиции заказа.json"
PRODUCTION_EMAIL = "made@magazinot.ru"

# Шаблон тела письма в производство
PRODUCTION_BODY = """Ссылка на макет - CCCCCCCCCC"""
# =============================================


# --- Функция проверки версии CDR через Windows Properties ---
def get_cdr_version_windows(file_path):
    """Возвращает версию CDR-файла или None и сообщение об ошибке."""
    if not HAS_PYWIN32:
        return None, "Модуль win32com.client не установлен"
    try:
        shell = win32com.client.Dispatch("Shell.Application")
        namespace = shell.NameSpace(str(file_path.parent))
        item = namespace.ParseName(str(file_path.name))
        if not item:
            return None, "Не удалось получить доступ к файлу через Shell"

        # Ищем поле с версией (перебираем индексы до 300)
        version_str = None
        for i in range(0, 300):
            prop_name = namespace.GetDetailsOf(None, i)
            if prop_name and ("Версия файла" in prop_name or "File version" in prop_name):
                version_str = namespace.GetDetailsOf(item, i)
                if version_str:
                    break

        if not version_str:
            return None, "Не найдено поле 'Версия файла'"

        match = re.search(r'(\d+)', version_str)
        if match:
            return int(match.group(1)), None
        else:
            return None, f"Не удалось распознать версию из строки: {version_str}"
    except Exception as e:
        return None, f"Ошибка при чтении свойств: {e}"


def check_cdr_versions(folder):
    """
    Проверяет все CDR-файлы с префиксом CDR_PREFIX на соответствие версии 20.
    Возвращает список предупреждений (пустой, если всё хорошо).
    """
    if not CHECK_CDR_VERSION:
        return []
    if not HAS_PYWIN32:
        logger.warning("Проверка версий CDR отключена: модуль win32com.client не установлен.")
        return []

    # Находим все .cdr файлы с префиксом
    cdr_files = list(folder.glob(f"{CDR_PREFIX} *.cdr")) + list(folder.glob(f"{CDR_PREFIX} *.CDR"))

    logger.info(f"Найдено CDR-файлов с префиксом '{CDR_PREFIX}': {len(cdr_files)}")
    for f in cdr_files:
        logger.debug(f"  - {f.name}")

    if not cdr_files:
        return []  # нет файлов с префиксом – считаем ок

    warnings = []
    for cdr in cdr_files:
        version, error = get_cdr_version_windows(cdr)
        if error:
            warnings.append(f"{cdr.name} – ошибка: {error}")
        elif version != 20:
            warnings.append(f"{cdr.name} – версия {version}, требуется 20")
    return warnings


def is_folder_empty(folder_path):
    """Проверяет, пуста ли папка (включая подпапки без файлов)."""
    for item in folder_path.rglob('*'):
        if item.is_file():
            return False
    return True


def is_temp_file(file_path: pathlib.Path) -> bool:
    """Возвращает True, если файл является временным (Office lock, .tmp и т. п.)."""
    name = file_path.name
    for prefix in EXCLUDE_FILE_PREFIXES:
        if name.startswith(prefix):
            return True
    if file_path.suffix.lower() in EXCLUDE_SUFFIXES:
        return True
    return False


def create_archive(source_folder, archive_name, exclude_pattern, exclude_exts, exclude_files):
    """Создаёт ZIP-архив без сжатия ВНУТРИ папки заказа, исключая определённые файлы и расширения."""
    archive_path = source_folder / f"{archive_name}.zip"
    # Если архив уже существует, удалим его, чтобы не добавлять в новый
    if archive_path.exists():
        archive_path.unlink()
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_STORED) as zipf:
        for file_path in source_folder.rglob('*'):
            if file_path.is_dir():
                continue
            if file_path == archive_path:  # исключаем сам архив
                continue
            # Исключаем по расширению
            if file_path.suffix.lower() in exclude_exts:
                continue
            # Исключаем по точному имени файла
            if file_path.name in exclude_files:
                continue
            # Исключаем временные файлы Office/LibreOffice (~$..., .~lock..., *.tmp)
            if is_temp_file(file_path):
                logger.debug(f"Пропущен временный файл: {file_path.name}")
                continue
            # Исключаем по паттерну в имени
            if exclude_pattern in file_path.name:
                continue
            arcname = file_path.relative_to(source_folder)
            try:
                zipf.write(file_path, arcname)
            except PermissionError as e:
                logger.warning(f"Пропущен заблокированный файл {file_path.name}: {e}")
                continue
            except OSError as e:
                logger.warning(f"Пропущен файл {file_path.name} из-за ошибки ОС: {e}")
                continue
    return archive_path


def get_greeting_and_wish():
    """
    Возвращает кортеж (приветствие, пожелание).
    Пожелание может быть пустой строкой.
    """
    now = datetime.now()
    hour = now.hour
    weekday = now.weekday()  # 0=Пн ... 6=Вс

    # Приветствие
    if 5 <= hour < 10:
        greeting = "Доброе утро!"
    elif 10 <= hour < 12:
        greeting = "Здравствуйте!"
    elif 12 <= hour < 18:
        greeting = "Добрый день!"
    elif 18 <= hour < 24:
        greeting = "Добрый вечер!"
    else:
        greeting = "Здравствуйте!"

    # Пожелание
    if 0 <= hour < 5:
        wish = ""
    elif weekday in (5, 6):
        # Сб или Вс — весь день
        wish = "Хороших выходных!"
    elif weekday == 4 and hour >= 18:
        # Пятница вечером
        wish = "Хороших выходных!"
    elif hour >= 18:
        # Пн–Чт вечером
        wish = "Хорошего вечера!"
    else:
        # Пн–Пт днём
        wish = "Хорошего дня!"

    return greeting, wish


def read_emails_from_file(file_path):
    """Читает файл с email-ами (через запятую). Возвращает список."""
    if not file_path.exists():
        return []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        return [e.strip() for e in content.split(',') if e.strip()]
    except Exception as e:
        logger.error(f"Ошибка чтения {file_path}: {e}")
        return []


def was_sent_for_approval_today(folder):
    """Проверяет, была ли последняя отправка на согласование сегодня."""
    json_file = folder / ORDER_JSON_FILENAME
    if not json_file.exists():
        json_file = folder / LEGACY_JSON_FILENAME
    if not json_file.exists():
        logger.info(f"{ORDER_JSON_FILENAME} не найден: приветствие оставляем.")
        return False

    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        last_sent_at = data.get('approval', {}).get('last_sent_at')
        if not last_sent_at:
            logger.info("В JSON нет даты последней отправки на согласование: приветствие оставляем.")
            return False

        last_dt = datetime.fromisoformat(last_sent_at)
        same_day = last_dt.date() == datetime.now().date()
        logger.info(f"Последнее согласование: {last_sent_at}; сегодня: {'да' if same_day else 'нет'}")
        return same_day
    except Exception as e:
        logger.error(f"Не удалось прочитать историю согласований: {e}")
        return False


def create_mailto_link(to_emails, subject, body):
    """Формирует стандартную mailto-ссылку без cc."""
    recipients = ",".join(to_emails)
    params = {
        'subject': subject,
        'body': body,
    }
    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return f"mailto:{recipients}?{query}"


# --- Настройка логирования ---
script_path = pathlib.Path(__file__).resolve()
script_dir = script_path.parent
log_file = script_dir / LOG_FILENAME

logger = logging.getLogger('archive')
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

logger.info("=== Archive started ===")

# --- Получение целевой папки ---
if len(sys.argv) > 1:
    raw_arg = sys.argv[1]
    folder_str = raw_arg.strip().strip('"').strip()
    folder = pathlib.Path(folder_str)
    if not folder.is_absolute():
        folder = (script_dir / folder).resolve()
else:
    logger.error("No target folder passed.")
    sys.exit(1)

logger.info(f"Working folder: {folder}")

if not folder.exists() or not folder.is_dir():
    logger.error("Target folder does not exist or is not a directory.")
    sys.exit(1)

# --- Переменная для хранения пути к файлу ошибок (если будет создан) ---
error_file_path = None

# --- Проверка версий CDR-файлов с префиксом ---
warnings = check_cdr_versions(folder)
if warnings:
    logger.warning("Обнаружены проблемы с CDR-файлами (версия не 20 или ошибка чтения):")
    for w in warnings:
        logger.warning(f"  - {w}")
    # Создаём файл-предупреждение в папке заказа
    error_file_path = folder / "ОШИБКИ.txt"
    try:
        with open(error_file_path, 'w', encoding='utf-8') as f:
            f.write("Обнаружены проблемы с CDR-файлами (версия не 20 или ошибка чтения):\n")
            for w in warnings:
                f.write(f"- {w}\n")
            f.write("\nПожалуйста, пересохраните их в версии 20 (CorelDRAW 2018) перед отправкой в производство.")
        logger.info(f"Создан файл-предупреждение: {error_file_path.name}")
    except Exception as e:
        logger.error(f"Не удалось создать файл-предупреждение: {e}")
        error_file_path = None
else:
    logger.info("Все CDR-файлы с префиксом '%s' имеют версию 20 (или проверка не выполнялась).", CDR_PREFIX)

# --- "Позиции заказа.txt" оставляем в папке и в архиве ---
items_file = folder / ITEMS_FILENAME
if items_file.exists():
    logger.info(f"Keeping {ITEMS_FILENAME} (not removed)")
else:
    logger.info(f"{ITEMS_FILENAME} not found")

# --- Проверка папки "файлы" и удаление, если пуста ---
files_folder = folder / "файлы"
if files_folder.exists() and files_folder.is_dir():
    if is_folder_empty(files_folder):
        try:
            files_folder.rmdir()
            logger.info("Removed empty 'файлы' folder")
        except Exception as e:
            logger.error(f"Cannot remove 'файлы' folder: {e}")
    else:
        logger.info("'файлы' folder is not empty, keeping it")

# --- Проверка: может, архив уже существует (собран вручную) ---
expected_archive_path = folder / f"{folder.name}.zip"
if expected_archive_path.exists():
    archive_path = expected_archive_path
    logger.info(f"Архив уже существует, пересоздание пропущено: {archive_path}")
else:
    # --- Создание архива ВНУТРИ папки заказа с учётом исключений ---
    archive_path = create_archive(folder, folder.name, EXCLUDE_PATTERN, EXCLUDE_EXTENSIONS, EXCLUDE_FILES)
    logger.info(f"Archive created inside order folder: {archive_path}")

# --- Открытие почтового клиента: письмо в производство ---
archive_name_without_ext = archive_path.stem
subject = f"Макет, {archive_name_without_ext}"
mailto_link = create_mailto_link([PRODUCTION_EMAIL], subject, PRODUCTION_BODY)

logger.info(f"Opening mail client (production): {mailto_link}")
try:
    webbrowser.open(mailto_link)
    logger.info("Mail client (production) opened successfully.")
except Exception as e:
    logger.error(f"Failed to open mail client (production): {e}")

# --- Письмо заказчику: только если нет проблем с CDR и есть email-ы ---
if error_file_path and error_file_path.exists():
    logger.info("Пропускаем письмо заказчику: есть ОШИБКИ.txt")
else:
    emails_file = folder / EMAILS_FILENAME
    new_json = folder / ORDER_JSON_FILENAME
    if new_json.exists():
        try:
            with open(new_json, encoding="utf-8-sig") as f:
                to_emails = json.load(f).get("emails", [])
        except (OSError, ValueError, TypeError) as e:
            logger.error(f"Ошибка чтения JSON заказа: {e}")
            to_emails = []
    else:
        to_emails = read_emails_from_file(emails_file)
    if not to_emails:
        logger.warning(
            f"Файл {EMAILS_FILENAME} не найден, пуст или без валидных адресов. "
            f"Письмо заказчику не отправляем."
        )
    else:
        greeting, wish = get_greeting_and_wish()
        approved_today = was_sent_for_approval_today(folder)

        if approved_today:
            logger.info("Сегодня уже отправляли макет на согласование — повторное приветствие убираем.")
            body_parts = [
                "Ваш макет подготовлен и отправлен в производство.",
                "",
            ]
        else:
            logger.info(f"Приветствие: {greeting}; пожелание: {wish or '(нет)'}")
            body_parts = [
                greeting,
                "",
                "Ваш макет подготовлен и отправлен в производство.",
                "",
            ]
        if wish:
            body_parts.append(wish)
            body_parts.append("")
        body_parts.append("🕒 Актуальные сроки готовности заказа можете уточнить у менеджера.")
        body = "\n".join(body_parts)

        customer_subject = f"Макет отправлен в печать, {folder.name}"
        customer_mailto = create_mailto_link(to_emails, customer_subject, body)

        logger.info(f"Получатели (заказчик): {', '.join(to_emails)}")
        logger.debug(f"Customer mailto: {customer_mailto}")
        try:
            webbrowser.open(customer_mailto)
            logger.info("Mail client (customer) opened successfully.")
        except Exception as e:
            logger.error(f"Failed to open mail client (customer): {e}")

# --- Если был создан файл ошибок, открываем его ---
if error_file_path and error_file_path.exists():
    try:
        os.startfile(str(error_file_path))
        logger.info(f"Opened error file: {error_file_path.name}")
    except Exception as e:
        logger.error(f"Failed to open error file: {e}")

logger.info("=== Archive finished ===")