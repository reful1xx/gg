# -- coding: utf-8 --

import os
import telebot
from telebot import types
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta
import schedule
import time
import pytz
import requests

# -------------------- Flask-сервер для Render --------------------
app = Flask('')

@app.route('/')
def home():
    return "✅ Бот працює 24/7 на Render!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

Thread(target=run_flask).start()

# -------------------- Змінні --------------------
TOKEN = os.environ['TOKEN']
GROUP_ID = int(os.environ['GROUP_ID'])
THREAD_ID = int(os.environ.get('THREAD_ID', 0))
ADMIN_ID = int(os.environ['ADMIN_ID'])
JSONBIN_API_KEY = os.environ['JSONBIN_API_KEY']
BANLIST_BIN_ID = os.environ['BANLIST_BIN_ID']
LOGS_BIN_ID = os.environ['LOGS_BIN_ID']

bot = telebot.TeleBot(TOKEN)
user_state = {}  # chat_id -> category

# -------------------- JSONBin функції --------------------
def load_jsonbin(bin_id):
    url = f"https://api.jsonbin.io/v3/b/{bin_id}/latest"
    r = requests.get(url, headers={"X-Master-Key": JSONBIN_API_KEY})
    try:
        return r.json()['record']
    except:
        return []

def save_jsonbin(bin_id, data):
    url = f"https://api.jsonbin.io/v3/b/{bin_id}"
    requests.put(url, json=data, headers={"X-Master-Key": JSONBIN_API_KEY})

def load_banlist():
    return load_jsonbin(BANLIST_BIN_ID)

def save_banlist(data):
    save_jsonbin(BANLIST_BIN_ID, data)

def load_logs():
    return load_jsonbin(LOGS_BIN_ID)

def save_logs(data):
    save_jsonbin(LOGS_BIN_ID, data)

# -------------------- Користувач --------------------
def get_user_display_name(message):
    if message.from_user.username:
        return f"@{message.from_user.username}"
    else:
        full_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
        return full_name if full_name else f"[user](tg://user?id={message.from_user.id})"

# -------------------- Головне меню --------------------
def main_menu():
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add('📛 Скарга', '💡 Пропозиція')
    markup.add('❓ Запитання', '📬 Інше')
    return markup

# -------------------- Команди --------------------
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        "Привіт! Вибери тип повідомлення:\n\n"
        "📛 Скарга / 💡 Пропозиція / ❓ Запитання / 📬 Інше — усі повідомлення анонімні.\n"
        "Ми цінуємо вашу конфіденційність 💬",
        reply_markup=main_menu()
    )

@bot.message_handler(commands=['banlogs'])
def banlogs(message):
    if message.chat.id != ADMIN_ID:
        bot.reply_to(message, "⛔ У вас немає прав")
        return
    banlist = load_banlist()
    if not banlist:
        bot.send_message(ADMIN_ID, "⚠️ Список заблокованих порожній.")
        return
    text = "📌 Заблоковані користувачі:\n"
    for uid in banlist:
        text += f"- [{uid}](tg://user?id={uid})\n"
    bot.send_message(ADMIN_ID, text, parse_mode="Markdown")

# -------------------- Вибір категорії --------------------
@bot.message_handler(func=lambda message: message.text in ['📛 Скарга', '💡 Пропозиція', '❓ Запитання', '📬 Інше'])
def choose_category(message):
    user_state[message.chat.id] = message.text
    bot.send_message(message.chat.id, "✍️ Введіть текст повідомлення (воно залишиться анонімним):")

# -------------------- Обробка повідомлень --------------------
@bot.message_handler(func=lambda message: message.chat.id in user_state)
def handle_text(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    category = user_state.pop(chat_id)
    text = message.text
    display_name = get_user_display_name(message)
    banlist = load_banlist()

    if user_id in banlist:
        bot.send_message(chat_id, "⛔ Вас заблоковано і ви не можете надсилати повідомлення.")
        return

    # --- Логування ---
    logs = load_logs()
    logs.append({
        "user_id": user_id,
        "username": display_name,
        "category": category,
        "text": text,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    save_logs(logs)

    # --- Відповідь користувачу ---
    bot.send_message(chat_id, "✅ Ваше повідомлення отримано. Ми цінуємо вашу конфіденційність і думки.")

    # --- Надсилання в групу + гілку з кнопками ---
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("🔒 Заблокувати", callback_data=f"ban_{user_id}"),
        types.InlineKeyboardButton("✅ Розблокувати", callback_data=f"unban_{user_id}")
    )
    bot.send_message(
        GROUP_ID,
        f"📩 *Нове повідомлення ({category}):*\n\n{text}\n\nВід користувача: {display_name}",
        parse_mode="Markdown",
        message_thread_id=THREAD_ID or None,
        reply_markup=keyboard
    )

# -------------------- Кнопки Заблокувати / Розблокувати --------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith(("ban_", "unban_")))
def callback_buttons(call):
    if call.from_user.id != ADMIN_ID:
        call.answer("⛔ Тільки адміністратор")
        return

    action, uid = call.data.split("_")
    uid = int(uid)
    banlist = load_banlist()

    if action == "ban":
        if uid not in banlist:
            banlist.append(uid)
            save_banlist(banlist)
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
            bot.send_message(call.message.chat.id, f"🔒 Користувач {uid} заблокований кнопкою")
        else:
            call.answer("Він вже заблокований", show_alert=True)
    elif action == "unban":
        if uid in banlist:
            banlist.remove(uid)
            save_banlist(banlist)
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
            bot.send_message(call.message.chat.id, f"✔ Користувач {uid} розблокований кнопкою")
        else:
            call.answer("Він не заблокований", show_alert=True)

# -------------------- Щоденна відправка логів адміну --------------------
def send_logs_daily():
    logs = load_logs()
    if logs:
        filename = "logs.txt"
        with open(filename, "w", encoding="utf-8") as f:
            for l in logs:
                f.write(f"[{l['time']}] {l['user_id']} ({l['username']}, {l['category']}): {l['text']}\n")
        with open(filename, "rb") as f:
            bot.send_document(ADMIN_ID, f)
        os.remove(filename)

def schedule_daily_logs():
    tz = pytz.timezone("Europe/Kiev")
    schedule.every().day.at("20:00").do(send_logs_daily).tag("daily_logs")
    while True:
        schedule.run_pending()
        time.sleep(30)

# -------------------- Запуск --------------------
Thread(target=schedule_daily_logs).start()
print("Бот запущено... Чекаю повідомлень")
bot.polling(non_stop=True)
