# -*- coding: utf-8 -*-

import os
import time
import requests
from threading import Thread
from datetime import datetime, timedelta
import pytz
from flask import Flask
import telebot
from telebot import types

# -------------------- Flask (ping для Render) --------------------
app = Flask('')
@app.route('/')
def home():
    return "OK"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

Thread(target=run_flask, daemon=True).start()

# -------------------- ENV --------------------
TOKEN = os.environ['TOKEN']
GROUP_ID = int(os.environ['GROUP_ID'])
THREAD_ID = int(os.environ.get('THREAD_ID', 0))
ADMIN_ID = int(os.environ['ADMIN_ID'])

# Підтримка порожнього MODERATORS_ID
MODERATORS_ID = os.environ.get('MODERATORS_ID', '')
if MODERATORS_ID:
    MODERATORS_ID = list(map(int, MODERATORS_ID.split(',')))
else:
    MODERATORS_ID = []

JSONBIN_API_KEY = os.environ['JSONBIN_API_KEY']
LOGS_BIN_ID = os.environ['LOGS_BIN_ID']
BANLIST_BIN_ID = os.environ['BANLIST_BIN_ID']

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# -------------------- Стан користувача --------------------
user_state = {}
msg_to_user = {}

# -------------------- JSONBin --------------------
def load_jsonbin(bin_id):
    url = f"https://api.jsonbin.io/v3/b/{bin_id}/latest"
    headers = {"X-Master-Key": JSONBIN_API_KEY}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json().get('record', [])
    except:
        return []
    return []

def save_jsonbin(bin_id, data):
    url = f"https://api.jsonbin.io/v3/b/{bin_id}"
    headers = {"X-Master-Key": JSONBIN_API_KEY, "Content-Type": "application/json"}
    try:
        requests.put(url, json=data, headers=headers, timeout=10)
    except:
        pass

def load_banlist():
    return load_jsonbin(BANLIST_BIN_ID) or []

def save_banlist(data):
    save_jsonbin(BANLIST_BIN_ID, data)

def load_logs():
    return load_jsonbin(LOGS_BIN_ID) or []

def save_logs(data):
    save_jsonbin(LOGS_BIN_ID, data)

def is_banned(user_id):
    for b in load_banlist():
        if b.get("user_id") == int(user_id):
            return True
    return False

def add_ban(user_id, username=""):
    bl = load_banlist()
    if not any(b.get("user_id") == int(user_id) for b in bl):
        bl.append({"user_id": int(user_id), "username": username or ""})
        save_banlist(bl)

def remove_ban(user_id):
    bl = load_banlist()
    bl = [b for b in bl if b.get("user_id") != int(user_id)]
    save_banlist(bl)

def format_username(username):
    return f"@{username}" if username else "немає"

def user_link(user_id):
    return f"tg://user?id={user_id}"

# -------------------- Меню --------------------
def main_menu():
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add('📛 Скарга', '💡 Пропозиція')
    markup.add('❓ Запитання', '📬 Інше')
    return markup

# -------------------- /start --------------------
@bot.message_handler(commands=['start'])
def start_cmd(message):
    if message.chat.type != "private":
        return
    bot.send_message(
        message.chat.id,
        "Привіт! Вибери тип повідомлення (Повідомлення відправляються Анонімно!):",
        reply_markup=main_menu()
    )

# -------------------- Вибір категорії --------------------
@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text in ['📛 Скарга', '💡 Пропозиція', '❓ Запитання', '📬 Інше'])
def choose_category(message):
    user_state[message.chat.id] = message.text
    # ✅ виправлений текст
    bot.send_message(message.chat.id, "✍️ Введіть текст з вашим повідомленням")

# -------------------- Генерація кнопки бану --------------------
def get_user_ban_button(user_id):
    kb = types.InlineKeyboardMarkup()
    if is_banned(user_id):
        kb.add(types.InlineKeyboardButton("✔️ Розблокувати", callback_data=f"unban_{user_id}"))
    else:
        kb.add(types.InlineKeyboardButton("🚫 Заблокувати", callback_data=f"ban_{user_id}"))
    return kb

# -------------------- Повідомлення від користувача --------------------
@bot.message_handler(func=lambda m: m.chat.type == "private" and m.chat.id in user_state,
                     content_types=['text', 'photo'])
def handle_user_submission(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    category = user_state.pop(chat_id)

    if is_banned(user_id):
        bot.send_message(chat_id, "⛔ Вас заблоковано.\nВи більше не можете надсилати повідомлення.")
        return

    if message.content_type == "photo":
        file_id = message.photo[-1].file_id
        text = message.caption or ""
        is_photo = True
    else:
        file_id = None
        text = message.text or ""
        is_photo = False

    kyiv = pytz.timezone("Europe/Kyiv")
    logs = load_logs()
    logs.append({
        "time": datetime.now(kyiv).strftime("%Y-%m-%d %H:%M:%S"),
        "type": category,
        "text": text,
        "user_id": user_id,
        "username": message.from_user.username or "",
        "link": user_link(user_id),
        "photo_id": file_id
    })
    save_logs(logs)

    bot.send_message(chat_id, "✅ Ваше повідомлення надіслано. Дякуємо!")

    group_text = (
        f"📩 <b>Нове повідомлення</b>\n"
        f"Тип: {category}\n\n"
        f"{text}\n\n"
        f"ID: <code>{user_id}</code>"
    )

    kb = get_user_ban_button(user_id)

    if is_photo:
        if THREAD_ID:
            sent = bot.send_photo(GROUP_ID, file_id, caption=group_text,
                                  reply_markup=kb, parse_mode="HTML",
                                  message_thread_id=THREAD_ID)
        else:
            sent = bot.send_photo(GROUP_ID, file_id, caption=group_text,
                                  reply_markup=kb, parse_mode="HTML")
    else:
        if THREAD_ID:
            sent = bot.send_message(GROUP_ID, group_text,
                                    reply_markup=kb, parse_mode="HTML",
                                    message_thread_id=THREAD_ID)
        else:
            sent = bot.send_message(GROUP_ID, group_text,
                                    reply_markup=kb, parse_mode="HTML")

    msg_to_user[sent.message_id] = user_id

# -------------------- Callback кнопки --------------------
@bot.callback_query_handler(func=lambda c: c.data and (c.data.startswith("ban_") or c.data.startswith("unban_")))
def callback_ban_unban(call):
    user_is_admin = call.from_user.id == ADMIN_ID or call.from_user.id in MODERATORS_ID
    if not user_is_admin:
        call.answer("⛔ Тільки адміністратор або модератор", show_alert=True)
        return

    action, uid_str = call.data.split("_", 1)
    try:
        uid = int(uid_str)
    except:
        call.answer("Невірний ID", show_alert=True)
        return

    if action == "ban":
        add_ban(uid)
        try:
            bot.edit_message_reply_markup(call.message.chat.id,
                                          call.message.message_id,
                                          reply_markup=get_user_ban_button(uid))
        except:
            pass
        bot.send_message(call.message.chat.id, f"🚫 Користувач {uid} заблокований.")
    else:
        remove_ban(uid)
        try:
            bot.edit_message_reply_markup(call.message.chat.id,
                                          call.message.message_id,
                                          reply_markup=get_user_ban_button(uid))
        except:
            pass
        bot.send_message(call.message.chat.id, f"✔️ Користувач {uid} розблокований.")

    call.answer()

# -------------------- Reply у групі -> автору --------------------
@bot.message_handler(func=lambda m: m.chat.id == GROUP_ID
                               and m.reply_to_message
                               and m.reply_to_message.message_id in msg_to_user,
                     content_types=['text', 'photo'])
def group_reply_handler(message):
    original_user_id = msg_to_user.get(message.reply_to_message.message_id)
    if not original_user_id:
        return
    try:
        if message.content_type == "photo":
            file_id = message.photo[-1].file_id
            caption = message.caption or ""
            bot.send_photo(original_user_id, file_id, caption=caption)
        else:
            bot.send_message(original_user_id,
                             f"📬 Відповідь на ваше повідомлення:\n\n{message.text}")
        bot.reply_to(message, "✅ Відповідь надіслана користувачу.")
    except:
        bot.reply_to(message, "❌ Не вдалося надіслати повідомлення користувачу.")

# -------------------- Команди адміністратора --------------------
@bot.message_handler(commands=['ban'])
def cmd_ban(message):
    if message.chat.type != "private" or message.from_user.id != ADMIN_ID:
        return
    try:
        uid = int(message.text.split()[1])
        add_ban(uid)
        bot.send_message(message.chat.id, f"🚫 Користувач {uid} заблокований.")
    except:
        bot.send_message(message.chat.id, "❌ Використання: /ban USER_ID")

@bot.message_handler(commands=['unban'])
def cmd_unban(message):
    if message.chat.type != "private" or message.from_user.id != ADMIN_ID:
        return
    try:
        uid = int(message.text.split()[1])
        remove_ban(uid)
        bot.send_message(message.chat.id, f"✔️ Користувач {uid} розблокований.")
    except:
        bot.send_message(message.chat.id, "❌ Використання: /unban USER_ID")

@bot.message_handler(commands=['getban'])
def cmd_getban(message):
    if message.chat.type != "private" or message.from_user.id != ADMIN_ID:
        return

    bl = load_banlist()
    if not bl:
        bot.send_message(message.chat.id, "✅ Банлист порожній.")
        return

    text = "🚫 Заблоковані користувачі:\n\n"
    for b in bl:
        text += f"{format_username(b.get('username'))} | {b.get('user_id')}\n"

    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['getlogs'])
def cmd_getlogs(message):
    if message.chat.type != "private" or message.from_user.id != ADMIN_ID:
        return

    logs = load_logs()
    if not logs:
        bot.send_message(message.chat.id, "⚠️ Логи порожні.")
        return

    for l in logs:
        uname = format_username(l.get("username"))
        text = (
            f"🕒 {l.get('time')}\n"
            f"Тип: {l.get('type')}\n"
            f"Текст: {l.get('text')}\n"
            f"ID: {l.get('user_id')} | {uname}\n"
            f"{l.get('link')}"
        )

        bot.send_message(message.chat.id, text)

        if l.get("photo_id"):
            bot.send_photo(
                message.chat.id,
                l["photo_id"],
                caption="🖼 Фото з повідомлення"
            )
# -------------------- Очищення логів вручну --------------------
@bot.message_handler(commands=['clearlogs'])
def cmd_clearlogs(message):
    if message.chat.type != "private" or message.from_user.id != ADMIN_ID:
        return

    save_logs([])
    bot.send_message(message.chat.id, "✅ Усі логи в JSONBin повністю видалені")

# -------------------- Очищення старих логів --------------------
def clean_old_logs():
    kyiv = pytz.timezone("Europe/Kyiv")
    logs = load_logs()
    cutoff_date = datetime.now(kyiv) - timedelta(days=7)

    new_logs = []
    for log in logs:
        try:
            log_time = datetime.strptime(log.get("time"), "%Y-%m-%d %H:%M:%S")
            if log_time >= cutoff_date or is_banned(log.get("user_id")):
                new_logs.append(log)
        except:
            pass

    if len(new_logs) != len(logs):
        save_logs(new_logs)

# -------------------- Щоденні TXT-логи адміну --------------------
def send_logs_daily():
    clean_old_logs()

    logs = load_logs()
    bl = load_banlist()
    if not logs and not bl:
        return

    fname_logs = "logs.txt"
    fname_ban = "banlist.txt"
    kyiv = pytz.timezone("Europe/Kyiv")

    with open(fname_logs, "w", encoding="utf-8") as f:
        for l in logs:
            uname = format_username(l.get("username"))
            f.write(
                f"[{l.get('time')}] {l.get('type')}: {l.get('text')}\n"
                f"ID: {l.get('user_id')} | {uname} | {l.get('link')} | Photo: {l.get('photo_id')}\n\n"
            )

    with open(fname_ban, "w", encoding="utf-8") as f:
        for b in bl:
            uname = format_username(b.get("username"))
            uid = b.get("user_id")
            f.write(f"{uname} | {uid} | {user_link(uid)}\n")

    with open(fname_logs, "rb") as f:
        bot.send_document(ADMIN_ID, f)

    with open(fname_ban, "rb") as f:
        bot.send_document(ADMIN_ID, f)

def daily_logs_loop():
    kyiv = pytz.timezone("Europe/Kyiv")
    while True:
        now = datetime.now(kyiv)
        target = now.replace(hour=20, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)

        wait_seconds = (target - now).total_seconds()
        time.sleep(wait_seconds)

        try:
            send_logs_daily()
        except Exception as e:
            print("Error sending daily logs:", e)

        time.sleep(60)

Thread(target=daily_logs_loop, daemon=True).start()

# -------------------- Запуск --------------------
print("Бот запущено")
while True:
    try:
        bot.polling(non_stop=True)
    except Exception as e:
        print("Polling error:", e)
        time.sleep(5)

