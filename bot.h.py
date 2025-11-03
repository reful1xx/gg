-- coding: utf-8 --

import os
import telebot
from telebot import types
from flask import Flask
from threading import Thread
import shutil
from datetime import datetime, timedelta
import schedule
import time
import pytz

=== Flask-сервер для Render ===

app = Flask('')

@app.route('/')
def home():
return "✅ Бот працює 24/7 на Render!"

def run():
port = int(os.environ.get("PORT", 8080))
app.run(host='0.0.0.0', port=port)

Thread(target=run).start()

=== Кінець Flask-блоку ===

--- Токен і ID групи/адміна ---

TOKEN = os.environ['TOKEN']
GROUP_ID = int(os.environ['GROUP_ID'])
ADMIN_ID = int(os.environ.get('ADMIN_ID', 0))
THREAD_ID = int(os.environ.get('THREAD_ID', 0))

bot = telebot.TeleBot(TOKEN)
user_state = {}

=== Папка логів ===

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

def get_user_display_name(message):
if message.from_user.username:
return f"@{message.from_user.username}"
else:
full_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
return full_name if full_name else f"user_{message.chat.id}"

def log_message(category_name, user_name, text):
now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
filename = "all_messages.log"
path = os.path.join(LOG_DIR, filename)
with open(path, "a", encoding="utf-8") as f:
f.write(f"[{now}] user={user_name} | category={category_name} | text="{text}"\n")

def cleanup_old_logs(days=30):
cutoff = datetime.now() - timedelta(days=days)
for file in os.listdir(LOG_DIR):
path = os.path.join(LOG_DIR, file)
if os.path.isfile(path):
mtime = datetime.fromtimestamp(os.path.getmtime(path))
if mtime < cutoff:
os.remove(path)

cleanup_old_logs()

--- Головне меню ---

def main_menu():
markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
markup.add('📛 Скарга', '💡 Пропозиція')
markup.add('❓ Запитання', '📬 Інше')
return markup

--- /start ---

@bot.message_handler(commands=['start'])
def start(message):
bot.send_message(
message.chat.id,
"Привіт! Вибери тип повідомлення:\n\n"
"Всі повідомлення надсилаються анонімно.\n"
"Ми цінуємо вашу конфіденційність.",
reply_markup=main_menu()
)

--- /getlogs для адміна ---

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

--- Вибір категорії ---

@bot.message_handler(func=lambda message: message.text in ['📛 Скарга', '💡 Пропозиція', '❓ Запитання', '📬 Інше'])
def choose_category(message):
user_state[message.chat.id] = message.text
bot.send_message(message.chat.id, "Введи текст повідомлення:")

--- Обробка повідомлення ---

@bot.message_handler(func=lambda message: message.chat.id in user_state)
def handle_text(message):
category = user_state.pop(message.chat.id)
text = message.text
user_name = get_user_display_name(message)

# --- Логування ---
log_message(category, user_name, text)

# --- Відповідь користувачу ---
bot.send_message(message.chat.id, "✅ Ваше повідомлення отримано. Ми цінуємо вашу конфіденційність.")

# --- Надсилання в групу адміністраторів ---
bot.send_message(
    GROUP_ID,
    f"📩 *Нове повідомлення ({category}):*\n\n{text}",
    parse_mode="Markdown",
    message_thread_id=THREAD_ID or None
)

--- Щоденна відправка логів адміністратору о 20:00 Київ ---

def send_logs_daily():
if os.listdir(LOG_DIR):
zip_path = "logs.zip"
shutil.make_archive("logs", 'zip', LOG_DIR)
with open(zip_path, "rb") as f:
bot.send_document(ADMIN_ID, f)
os.remove(zip_path)
# --- Очистка логів після відправки ---
for file in os.listdir(LOG_DIR):
file_path = os.path.join(LOG_DIR, file)
if os.path.isfile(file_path):
os.remove(file_path)

def schedule_daily_logs():
tz = pytz.timezone('Europe/Kiev')
schedule.every().day.at("20:00").do(send_logs_daily).tag("daily_logs")
while True:
schedule.run_pending()
time.sleep(30)

Thread(target=schedule_daily_logs).start()

print("✅ Бот запущений...")
bot.polling(non_stop=True)
