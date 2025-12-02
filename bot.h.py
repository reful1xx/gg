# -*- coding: utf-8 -*-

import os
import telebot
from telebot import types
from flask import Flask
from threading import Thread
from datetime import datetime
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

Thread(target=run_flask, daemon=True).start()

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
msg_to_user = {}  # message_id в групі -> user_id

# -------------------- JSONBin функції --------------------
def load_jsonbin(bin_id):
    url = f"https://api.jsonbin.io/v3/b/{bin_id}/latest"
    r = requests.get(url, headers={"X-Master-Key": JSONBIN_API_KEY})
    if r.status_code == 200:
        return r.json().get('record', [])
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
def get_user_info(user):
    username = f"@{user.username}" if user.username else f"[user](tg://user?id={user.id})"
    link = f"[link](tg://user?id={user.id})"
    return username, user.id, link

def format_user_line(user_dict):
    uname = f"@{user_dict['username']}" if user_dict['username'] else f"[user](tg://user?id={user_dict['user_id']})"
    uid = user_dict['user_id']
    link = f"[link](tg://user?id={uid})"
    return f"{uname} | {uid} | {link}"

def update_username_in_banlist(user_id, new_username):
    banlist = load_banlist()
    changed = False
    for b in banlist:
        if b['user_id'] == user_id:
            if b.get('username') != new_username:
                b['username'] = new_username
                changed = True
            break
    if changed:
        save_banlist(banlist)

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

@bot.message_handler(commands=['getlogs'])
def get_logs_command(message):
    if message.chat.id != ADMIN_ID:
        bot.reply_to(message, "⛔ У вас немає прав")
        return
    send_logs_file()

@bot.message_handler(commands=['getban'])
def get_ban_command(message):
    if message.chat.id != ADMIN_ID:
        bot.reply_to(message, "⛔ У вас немає прав")
        return
    send_ban_file()

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
    uname, uid, link = get_user_info(message.from_user)

    # --- Оновлюємо username у банлисті, якщо користувач там ---
    update_username_in_banlist(uid, message.from_user.username or "")

    banlist = [b['user_id'] for b in load_banlist()]
    if user_id in banlist:
        bot.send_message(chat_id, "⛔ Вас заблоковано і ви не можете надсилати повідомлення.")
        return

    # --- Логування ---
    logs = load_logs()
    logs.append({
        "user_id": uid,
        "username": message.from_user.username or "",
        "category": category,
        "text": text,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    save_logs(logs)

    bot.send_message(chat_id, "✅ Ваше повідомлення отримано. Ми цінуємо вашу конфіденційність і думки.")

    # --- Надсилання в групу + кнопки ---
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("🔒 Заблокувати", callback_data=f"ban_{uid}"),
        types.InlineKeyboardButton("✅ Розблокувати", callback_data=f"unban_{uid}")
    )
    msg = bot.send_message(
        GROUP_ID,
        f"📩 *Нове повідомлення ({category}):*\n\n{text}\n\nВід користувача: {uname} | {uid} | {link}",
        parse_mode="Markdown",
        message_thread_id=THREAD_ID if THREAD_ID else None,
        reply_markup=keyboard
    )
    msg_to_user[msg.message_id] = uid

# -------------------- Кнопки Адміна --------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith(("ban_", "unban_")))
def callback_buttons(call):
    if call.from_user.id != ADMIN_ID:
        call.answer("⛔ Тільки адміністратор")
        return

    action, uid = call.data.split("_")
    uid = int(uid)
    banlist = load_banlist()
    existing_ids = [b['user_id'] for b in banlist]

    if action == "ban":
        if uid not in existing_ids:
            try:
                username = bot.get_chat(uid).username or ""
            except:
                username = ""
            banlist.append({"user_id": uid, "username": username})
            save_banlist(banlist)
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
            bot.send_message(call.message.chat.id, f"🔒 Користувач {uid} заблокований")
        else:
            call.answer("Він вже заблокований", show_alert=True)
    elif action == "unban":
        if uid in existing_ids:
            banlist = [b for b in banlist if b['user_id'] != uid]
            save_banlist(banlist)
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
            bot.send_message(call.message.chat.id, f"✔ Користувач {uid} розблокований")
        else:
            call.answer("Він не заблокований", show_alert=True)

# -------------------- Відповідь адміну через reply --------------------
@bot.message_handler(func=lambda message: message.reply_to_message and message.chat.id == GROUP_ID and message.from_user.id == ADMIN_ID)
def admin_reply(message):
    replied_id = message.reply_to_message.message_id
    if replied_id in msg_to_user:
        user_id = msg_to_user[replied_id]
        bot.send_message(user_id, f"📬 Відповідь адміністратора:\n\n{message.text}")
        bot.send_message(ADMIN_ID, f"✅ Відповідь надіслана користувачу {user_id}")

# -------------------- Логи та банлист у файли --------------------
def send_logs_file():
    logs = load_logs()
    if not logs:
        bot.send_message(ADMIN_ID, "⚠️ Логи порожні.")
        return
    with open("logs.txt", "w", encoding="utf-8") as f:
        for l in logs:
            line = format_user_line(l)
            f.write(f"[{l['time']}] {l['category']} - {line}: {l['text']}\n")
    with open("logs.txt", "rb") as f:
        bot.send_document(ADMIN_ID, f)
    os.remove("logs.txt")

def send_ban_file():
    banlist = load_banlist()
    if not banlist:
        bot.send_message(ADMIN_ID, "⚠️ Банлист порожній.")
        return
    with open("banlist.txt", "w", encoding="utf-8") as f:
        for b in banlist:
            uname = f"@{b['username']}" if b['username'] else f"[user](tg://user?id={b['user_id']})"
            uid = b['user_id']
            link = f"[link](tg://user?id={uid})"
            f.write(f"{uname} | {uid} | {link}\n")
    with open("banlist.txt", "rb") as f:
        bot.send_document(ADMIN_ID, f)
    os.remove("banlist.txt")

# -------------------- Щоденна відправка логів та банлисту --------------------
def send_logs_daily():
    send_logs_file()
    send_ban_file()

def schedule_daily_logs():
    tz = pytz.timezone("Europe/Kiev")
    schedule.every().day.at("20:00").do(send_logs_daily).tag("daily_logs")
    while True:
        schedule.run_pending()
        time.sleep(30)

Thread(target=schedule_daily_logs, daemon=True).start()

# -------------------- Запуск бота --------------------
print("Бот запущено... Чекаю повідомлень")
while True:
    try:
        bot.polling(non_stop=True)
    except Exception as e:
        print(f"Помилка бота: {e}")
        time.sleep(5)
