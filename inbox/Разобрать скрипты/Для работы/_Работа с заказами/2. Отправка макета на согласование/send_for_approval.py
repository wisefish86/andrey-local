import os
import sys
import pathlib
import logging
import urllib.parse
import json
from datetime import datetime

# ================= НАСТРОЙКИ =================
EMAILS_FILENAME = "- Emails для согласования.txt"
ORDER_JSON_FILENAME = "- Позиции заказа.json"
LOG_FILENAME = "send_for_approval.log"

# Соответствие менеджер → email (для копии)
MANAGER_EMAILS = {
    "Андрей Майоров": "a.mayorov@magazinot.ru",
    "Галина Полякова": "galina@magazinot.ru",
    "Владимир Артемьев": "artemev@magazinot.ru",
    "Наталия Миронова": "mironova@magazinot.ru",
    "Василий Зверев": "zver@magazinot.ru"
}
# =============================================

def get_greeting():
    """Возвращает приветствие в зависимости от текущего часа."""
    hour = datetime.now().hour
    if 5 <= hour < 10:
        return "Доброе утро"
    elif 10 <= hour < 12:
        return "Здравствуйте"
    elif 12 <= hour < 18:
        return "Добрый день"
    elif 18 <= hour < 24:
        return "Добрый вечер"
    else:
        return "Здравствуйте"

def extract_manager_from_folder(folder_name):
    """
    Из имени папки вида "Заказ N от даты (Клиент) - Менеджер"
    извлекает часть после " - ". Если нет дефиса, возвращает None.
    """
    if " - " in folder_name:
        return folder_name.split(" - ", 1)[1].strip()
    return None

def read_emails_from_file(file_path):
    """Читает файл с email-ами (через запятую) и возвращает список."""
    if not file_path.exists():
        return []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        # Разделяем по запятой, убираем пробелы
        emails = [email.strip() for email in content.split(',') if email.strip()]
        return emails
    except Exception as e:
        logging.error(f"Ошибка чтения {file_path}: {e}")
        return []

def create_mailto_link(to_emails, cc_emails, subject, body):
    """Формирует стандартную mailto-ссылку."""
    recipients = ",".join(to_emails)
    params = {}
    if cc_emails:
        params['cc'] = ",".join(cc_emails)
    params['subject'] = subject
    params['body'] = body
    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return f"mailto:{recipients}?{query}"


def update_approval_history(folder):
    """Обновляет историю отправок на согласование в JSON заказа."""
    json_file = folder / ORDER_JSON_FILENAME
    if not json_file.exists():
        logger.warning(f"{ORDER_JSON_FILENAME} не найден. История согласований не обновлена.")
        return

    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        approval_info = data.setdefault('approval', {})
        history = approval_info.get('history')
        if not isinstance(history, list):
            history = []

        now_text = datetime.now().isoformat(timespec='seconds')
        previous_count = approval_info.get('send_count', 0)
        try:
            previous_count = int(previous_count)
        except (TypeError, ValueError):
            previous_count = len(history)

        history.append(now_text)
        approval_info['last_sent_at'] = now_text
        approval_info['send_count'] = max(previous_count + 1, len(history))
        approval_info['history'] = history

        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"История согласований обновлена: отправка №{approval_info['send_count']}, {now_text}")
    except Exception as e:
        logger.error(f"Не удалось обновить историю согласований: {e}")

# --- Настройка логирования ---
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
logger = logging.getLogger('send_for_approval')

logger.info("=== Send for approval started ===")

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

# --- Определяем имя папки (без пути) для темы ---
folder_name = folder.name
subject = f"Согласование макета, {folder_name}"

# --- Определяем менеджера из имени папки ---
manager_name = extract_manager_from_folder(folder_name)
cc_emails = []
if manager_name and manager_name in MANAGER_EMAILS:
    cc_emails.append(MANAGER_EMAILS[manager_name])
    logger.info(f"Менеджер: {manager_name} -> копия: {cc_emails[0]}")
else:
    logger.info("Менеджер не определён, копия не добавляется.")

# --- Читаем email-ы получателей из файла ---
emails_file = folder / EMAILS_FILENAME
to_emails = read_emails_from_file(emails_file)
if not to_emails:
    logger.warning(f"Файл {EMAILS_FILENAME} не найден или пуст. Получатели не указаны.")
else:
    logger.info(f"Получатели: {', '.join(to_emails)}")

# --- Приветствие ---
greeting = get_greeting()
logger.info(f"Приветствие: {greeting}")

# --- Формируем тело письма ---
body = f"""[!] ❓ В самом макете оставил несколько вопросов по предпочитаемому варианту
🔍 Также прикладываю PDF-документ. Чтобы увидеть изделие в его фактическом размере, установите масштаб просмотра на 100%. Так вы сможете убедиться, что весь текст читаемый.
Обратите внимание: на печати детализация будет выше, поскольку печатное разрешение составляет 300 dpi, тогда как экраны обычно отображают от 72 точек на дюйм.

════════════════════════════
█▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀█
    ⚠️ ПРИКРЕПИ ПРЕВЬЮ МАКЕТА ⚠️  
█▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄█
════════════════════════════


{greeting}! Направляю превью макета для согласования.

Пожалуйста, проверьте макет перед отправкой в печать:
✅ текст и дизайн (во избежание опечаток и ошибок при печати),
✅ количество экземпляров,
✅ размеры изделия(-й).

Жду ваши комментарии или подтверждение. Для подтверждения достаточно короткого ответа, например: "Ок", "Подтверждаю", "Можно печатать", "Всё верно", "Утверждаю"...
Прошу не забывать дублировать ответные письма менеджеру (оставлять его в копии).

После получения письменного согласования передаю макет в производство.

🕒 Актуальные сроки готовности заказа можете уточнить у менеджера."""

# --- Создаём mailto ссылку и открываем её ---
mailto_link = create_mailto_link(to_emails, cc_emails, subject, body)
logger.debug(f"Mailto link: {mailto_link}")

try:
    if sys.platform == "win32":
        # Открываем через назначенный в Windows обработчик MAILTO, а не браузер Python.
        os.startfile(mailto_link)
        logger.info("Запрос на открытие письма передан обработчику MAILTO Windows.")
        update_approval_history(folder)
    else:
        logger.error("Этот способ открытия письма поддерживается только в Windows.")
except Exception as e:
    logger.error(f"Не удалось открыть почтовый клиент: {e}")

logger.info("=== Send for approval finished ===")