# -*- coding: utf-8 -*-
import os
import telebot
from telebot import types
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta
import shutil
import threading
import time
import pytz  # для таймзони

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
ADMIN_ID = int(os.environ.get('ADMIN_ID', 0))

bot = telebot.TeleBot(TOKEN)
user_state = {}

# === Папка логів ===
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# === Логування з іменами ===
def log_message(category_name, user, text):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filename = {
        '📛 Скарга': 'skarga.log',
        '💡 Пропозиція': 'propozytsiya.log',
        '❓ Запитання': 'zapytannya.log',
        '📬 Інше': 'inshe.log'
    }.get(category_name, 'other.log')
    path = os.path.join(LOG_DIR, filename)
    user_info = user.username or user.first_name or f"id:{user.id}"
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"[{now}] user={user_info} | text=\"{text}\"\n")

def cleanup_old_logs(days=30):
    cutoff = datetime.now() - timedelta(days=days)
    for file in os.listdir(LOG_DIR):
        path = os.path.join(LOG_DIR, file)
        if os.path.isfile(path):
            mtime = datetime.fromtimestamp(os.path.getmtime(path))
            if mtime < cutoff:
                os.remove(path)

cleanup_old_logs()

# --- Меню ---
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
        "📛 Скарга / 💡 Пропозиція / ❓ Запитання / 📬 Інше — *усі повідомлення анонімні.*\n"
        "Ми цінуємо вашу конфіденційність 💬",
        parse_mode="Markdown",
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
    bot.send_message(message.chat.id, "✍️ Введіть текст повідомлення (воно залишиться анонімним):")

# === Словник для зв’язку між повідомленням у групі та користувачем ===
message_links = {}

# --- Обробка повідомлень від користувачів ---
@bot.message_handler(func=lambda message: message.chat.id in user_state)
def handle_text(message):
    category = user_state.pop(message.chat.id)
    text = message.text.strip()

    log_message(category, message.from_user, text)

    # Надсилаємо в групу
    sent = bot.send_message(
        GROUP_ID,
        f"📩 *Нове повідомлення ({category}):*\n\n{text}",
        parse_mode="Markdown",
        message_thread_id=THREAD_ID or None
    )

    # Зберігаємо зв’язок між повідомленням у групі та користувачем
    message_links[sent.message_id] = message.chat.id

    bot.send_message(
        message.chat.id,
        "✅ Ваше повідомлення отримано. Ми цінуємо вашу конфіденційність 💬"
    )

# --- Обробка відповідей у групі ---
@bot.message_handler(func=lambda m: m.chat.id == GROUP_ID)
def handle_group_message(m):
    # Якщо це не reply — нічого не робимо
    if not m.reply_to_message:
        return

    # Якщо reply не на повідомлення бота — ігноруємо
    if m.reply_to_message.from_user.id != bot.get_me().id:
        return

    # Якщо reply на повідомлення, яке бот відправив користувача
    if m.reply_to_message.message_id in message_links:
        user_id = message_links[m.reply_to_message.message_id]
        try:
            bot.send_message(
                user_id,
                f"💬 *Відповідь від адміністрації:*\n\n{m.text}",
                parse_mode="Markdown"
            )
            bot.reply_to(m, "✅ Відповідь переслано користувачу (анонімно).")
        except Exception as e:
            bot.reply_to(m, f"⚠️ Не вдалося надіслати відповідь: {e}")

# === Автоматична відправка логів адміну о 20:00 за Києвом ===
def send_daily_logs():
    tz = pytz.timezone("Europe/Kyiv")
    while True:
        now = datetime.now(tz)
        target = now.replace(hour=20, minute=0, second=0, microsecond=0)
        if now > target:
            target += timedelta(days=1)
        sleep_time = (target - now).total_seconds()
        time.sleep(sleep_time)

        try:
            if os.listdir(LOG_DIR):
                zip_path = "logs.zip"
                shutil.make_archive("logs", 'zip', LOG_DIR)
                with open(zip_path, "rb") as f:
                    bot.send_message(ADMIN_ID, "📦 Щоденні логи за сьогодні:")
                    bot.send_document(ADMIN_ID, f)
                os.remove(zip_path)
        except Exception as e:
            bot.send_message(ADMIN_ID, f"⚠️ Помилка при відправці логів: {e}")

# Запускаємо в окремому потоці
Thread(target=send_daily_logs, daemon=True).start()

# === Запуск бота ===
bot.infinity_polling(skip_pending=True)
