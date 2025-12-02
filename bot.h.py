# -- coding: utf-8 --

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

# -------------------- Flask на Render --------------------
app = Flask('')

@app.route('/')
def home():
    return "Бот працює 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

Thread(target=run_flask).start()

# -------------------- ENV змінні --------------------
TOKEN = os.environ['TOKEN']
ADMIN_ID = int(os.environ['ADMIN_ID'])

JSONBIN_API_KEY = os.environ['JSONBIN_API_KEY']
LOGS_BIN_ID = os.environ['LOGS_BIN_ID']
BANLIST_BIN_ID = os.environ['BANLIST_BIN_ID']

bot = telebot.TeleBot(TOKEN)

# -------------------- JSONBin --------------------
def load_json(bin_id):
    url = f"https://api.jsonbin.io/v3/b/{bin_id}/latest"
    r = requests.get(url, headers={"X-Master-Key": JSONBIN_API_KEY})
    try:
        return r.json()['record']
    except:
        return []

def save_json(bin_id, data):
    url = f"https://api.jsonbin.io/v3/b/{bin_id}"
    requests.put(url, json=data, headers={"X-Master-Key": JSONBIN_API_KEY})

def load_logs():
    return load_json(LOGS_BIN_ID)

def save_logs(data):
    save_json(LOGS_BIN_ID, data)

def load_banlist():
    return load_json(BANLIST_BIN_ID)

def save_banlist(data):
    save_json(BANLIST_BIN_ID, data)

# -------------------- Отримати ім'я юзера --------------------
def get_user_display_name(message):
    u = message.from_user
    if u.username:
        return f"@{u.username}"
    name = f"{u.first_name or ''} {u.last_name or ''}".strip()
    if name:
        return name
    return f"tg://user?id={u.id}"

# -------------------- Обробка всіх повідомлень --------------------
@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_message(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    # 🔒 Перевірка бану
    banlist = load_banlist()
    if user_id in banlist:
        bot.send_message(
            chat_id,
            "⛔ Вас заблоковано.\nВи більше не можете надсилати повідомлення."
        )
        return

    # -------------------- Тип повідомлення --------------------
    if message.reply_to_message:
        msg_type = "💬 Відповідь"
    else:
        msg_type = "📨 Повідомлення"

    # -------------------- Логи --------------------
    username = f"@{message.from_user.username}" if message.from_user.username else "немає"
    user_link = f"tg://user?id={user_id}"

    logs = load_logs()
    entry = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": msg_type,
        "text": message.text,
        "user_id": user_id,
        "username": username,
        "link": user_link
    }
    logs.append(entry)
    save_logs(logs)

    # -------------------- Пересилання адміну --------------------
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("🚫 Заблокувати", callback_data=f"ban_{user_id}")
    )

    bot.send_message(
        ADMIN_ID,
        f"📩 *Нове повідомлення*\n"
        f"Тип: {msg_type}\n"
        f"Текст: {message.text}\n\n"
        f"ID: `{user_id}`\n"
        f"Username: {username}\n"
        f"Посилання: {user_link}",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

    # -------------------- Відповідь користувачу --------------------
    bot.send_message(chat_id, "✅ Ваше повідомлення отримано.")

# -------------------- Відповідь адміністратора через reply --------------------
@bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.reply_to_message, content_types=['text'])
def admin_reply(message):
    try:
        text = message.reply_to_message.text

        # В тексті знайти ID користувача
        for line in text.split("\n"):
            if line.startswith("ID:"):
                user_id = int(line.split("`")[1])
                break

        bot.send_message(user_id, f"✉ Адміністратор відповів:\n\n{message.text}")
        bot.send_message(ADMIN_ID, "✔ Відповідь надіслано!")

    except:
        bot.send_message(ADMIN_ID, "❌ Не вдалося знайти ID користувача.")

# -------------------- Callback кнопки бану --------------------
@bot.callback_query_handler(func=lambda c: c.data.startswith("ban_"))
def ban_user(call):
    if call.from_user.id != ADMIN_ID:
        call.answer("Немає прав", show_alert=True)
        return

    user_id = int(call.data.split("_")[1])
    banlist = load_banlist()

    if user_id not in banlist:
        banlist.append(user_id)
        save_banlist(banlist)
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.send_message(ADMIN_ID, f"🚫 Користувач {user_id} заблокований.")
    else:
        call.answer("Вже заблокований", show_alert=True)

# -------------------- Команда /ban --------------------
@bot.message_handler(commands=['ban'])
def ban_cmd(message):
    if message.chat.id != ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ Немає прав.")
        return
    try:
        user_id = int(message.text.split()[1])
        banlist = load_banlist()
        if user_id not in banlist:
            banlist.append(user_id)
            save_banlist(banlist)
            bot.send_message(ADMIN_ID, f"🚫 Користувач {user_id} заблокований.")
        else:
            bot.send_message(ADMIN_ID, "Він вже заблокований.")
    except:
        bot.send_message(ADMIN_ID, "Приклад: /ban 123456")

# -------------------- Команда /unban --------------------
@bot.message_handler(commands=['unban'])
def unban_cmd(message):
    if message.chat.id != ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ Немає прав.")
        return
    try:
        user_id = int(message.text.split()[1])
        banlist = load_banlist()
        if user_id in banlist:
            banlist.remove(user_id)
            save_banlist(banlist)
            bot.send_message(ADMIN_ID, f"✔ Користувач {user_id} розблокований.")
        else:
            bot.send_message(ADMIN_ID, "Цей користувач не заблокований.")
    except:
        bot.send_message(ADMIN_ID, "Приклад: /unban 123456")

# -------------------- /getlogs --------------------
@bot.message_handler(commands=['getlogs'])
def get_logs(message):
    if message.chat.id != ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ Немає прав.")
        return

    logs = load_logs()
    with open("logs.txt", "w", encoding="utf-8") as f:
        for l in logs:
            f.write(
                f"[{l['time']}]\n"
                f"Тип: {l['type']}\n"
                f"Повідомлення: {l['text']}\n"
                f"ID: {l['user_id']}\n"
                f"Username: {l['username']}\n"
                f"Посилання: {l['link']}\n\n"
            )

    with open("logs.txt", "rb") as f:
        bot.send_document(ADMIN_ID, f)

# -------------------- /getban --------------------
@bot.message_handler(commands=['getban'])
def get_ban(message):
    if message.chat.id != ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ Немає прав.")
        return

    banlist = load_banlist()
    with open("banlist.txt", "w", encoding="utf-8") as f:
        for uid in banlist:
            f.write(f"{uid}\n")

    with open("banlist.txt", "rb") as f:
        bot.send_document(ADMIN_ID, f)

# -------------------- Автоматична відправка логів о 20:00 --------------------
def send_logs_daily():
    logs = load_logs()
    if logs:
        with open("daily_logs.txt", "w", encoding="utf-8") as f:
            for l in logs:
                f.write(
                    f"[{l['time']}] {l['type']}\n"
                    f"{l['text']}\n"
                    f"ID: {l['user_id']} | {l['username']} | {l['link']}\n\n"
                )
        with open("daily_logs.txt", "rb") as f:
            bot.send_document(ADMIN_ID, f)

def schedule_job():
    schedule.every().day.at("20:00").do(send_logs_daily)
    while True:
        schedule.run_pending()
        time.sleep(30)

Thread(target=schedule_job).start()

# -------------------- Запуск --------------------
print("Бот запущено.")
bot.polling(non_stop=True)
