# -*- coding: utf-8 -*-
import os
import telebot
from telebot import types
from flask import Flask
from threading import Thread
import re
from datetime import datetime, timedelta
import shutil

# === Flask-сервер для Render ===
app = Flask('')

@app.route('/')
def home():
    return "✅ Бот працює 24/7 на Render!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

Thread(target=run).start()
# === Кінець Flask-блоку ===


# --- Токен і ID групи ---
TOKEN = os.environ['TOKEN']
GROUP_ID = int(os.environ['GROUP_ID'])
THREAD_ID = int(os.environ.get('THREAD_ID', 0))
ADMIN_ID = int(os.environ.get('ADMIN_ID', 0))  # ID адміна для команди /getlogs

bot = telebot.TeleBot(TOKEN)
user_state = {}


# === Створення папки логів ===
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

def log_message(category_name, user_id, text):
    """Запис повідомлення у файл категорії"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filename = {
        "Скарга": "skarga.log",
        "Пропозиція": "propozytsiya.log",
        "Запитання": "zapytannya.log",
        "Інше": "inshe.log"
    }.get(category_name, "other.log")

    path = os.path.join(LOG_DIR, filename)
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"[{now}] user_id={user_id} | text=\"{text}\"\n")

def cleanup_old_logs(days=30):
    """Видалення логів старших за N днів"""
    cutoff = datetime.now() - timedelta(days=days)
    for file in os.listdir(LOG_DIR):
        path = os.path.join(LOG_DIR, file)
        if os.path.isfile(path):
            mtime = datetime.fromtimestamp(os.path.getmtime(path))
            if mtime < cutoff:
                os.remove(path)

cleanup_old_logs()


# --- Головне меню ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add('📛 Скарга', '💡 Пропозиція')
    markup.add('❓ Запитання', '📬 Інше')
    return markup


# --- /start ---
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        "Привіт! Вибери тип повідомлення:\n\n"
        "📛 Скарга / 💡 Пропозиція — надсилаються анонімно.\n"
        "❓ Запитання / 📬 Інше — пересилаються з ID користувача, щоб отримати відповідь.",
        reply_markup=main_menu()
    )


# --- /getlogs (для адміна) ---
@bot.message_handler(commands=['getlogs'])
def get_logs(message):
    if message.chat.id != ADMIN_ID:
        bot.reply_to(message, "⛔ У вас немає прав для цієї команди.")
        return

    if not os.listdir(LOG_DIR):
        bot.send_message(ADMIN_ID, "⚠️ Логи порожні.")
        return

    zip_path = "logs.zip"
    shutil.make_archive("logs", 'zip', LOG_DIR)
    with open(zip_path, "rb") as f:
        bot.send_document(ADMIN_ID, f)
    os.remove(zip_path)


# --- Вибір категорії ---
@bot.message_handler(func=lambda message: message.text in ['📛 Скарга', '💡 Пропозиція', '❓ Запитання', '📬 Інше'])
def choose_category(message):
    user_state[message.chat.id] = message.text
    bot.send_message(message.chat.id, "Введи текст повідомлення:")


# --- Обробка повідомлення ---
@bot.message_handler(func=lambda message: message.chat.id in user_state)
def handle_text(message):
    category = user_state.pop(message.chat.id)
    text = message.text
    user_id = message.chat.id

    # --- Логування ---
    log_message(category, user_id, text)

    # --- Відповіді ---
    if category == '📛 Скарга':
        bot.send_message(user_id, "✅ Вашу скаргу отримано. Вона буде розглянута найближчим часом.")
        bot.send_message(GROUP_ID, f"📩 *Нова скарга:*\n\n{text}", parse_mode="Markdown", message_thread_id=THREAD_ID or None)

    elif category == '💡 Пропозиція':
        bot.send_message(user_id, "💬 Дякуємо, що робите нашу школу кращою!")
        bot.send_message(GROUP_ID, f"📩 *Нова пропозиція:*\n\n{text}", parse_mode="Markdown", message_thread_id=THREAD_ID or None)
        elif category == '❓ Запитання':
        bot.send_message(user_id, "✅ Ваше запитання передано учнівському самоврядуванню. Очікуйте відповіді.")
        bot.send_message(GROUP_ID, f"📩 *Нове запитання:*\n\n{text}\n\n👤 ID користувача: {user_id}", parse_mode="Markdown", message_thread_id=THREAD_ID or None)

    elif category == '📬 Інше':
        bot.send_message(user_id, "✅ Повідомлення передано учнівському самоврядуванню. Очікуйте відповіді.")
        bot.send_message(GROUP_ID, f"📩 *Повідомлення (Інше):*\n\n{text}\n\n👤 ID користувача: {user_id}", parse_mode="Markdown", message_thread_id=THREAD_ID or None)


# --- Відповідь адміністратора ---
@bot.message_handler(func=lambda message: message.chat.id == GROUP_ID and message.reply_to_message)
def admin_reply(message):
    reply_text = message.text
    original = message.reply_to_message.text

    match = re.search(r'ID користувача: (\d+)', original)
    if match:
        user_id = int(match.group(1))
        bot.send_message(user_id, f"📬 Відповідь учнівського самоврядування:\n\n{reply_text}")
        bot.reply_to(message, "✅ Відповідь надіслано користувачу.")

print("✅ Бот запущений...")
bot.polling(non_stop=True)

