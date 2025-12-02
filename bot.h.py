# -*- coding: utf-8 -*-
import os
import time
import requests
import schedule
from threading import Thread
from datetime import datetime
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
GROUP_ID = int(os.environ['GROUP_ID'])           # ID групи
THREAD_ID = int(os.environ.get('THREAD_ID', 0))  # ID гілки
ADMIN_ID = int(os.environ['ADMIN_ID'])

JSONBIN_API_KEY = os.environ['JSONBIN_API_KEY']
LOGS_BIN_ID = os.environ['LOGS_BIN_ID']
BANLIST_BIN_ID = os.environ['BANLIST_BIN_ID']

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# -------------------- Стан користувача --------------------
user_state = {}               # chat_id -> category
msg_to_user = {}              # message_id в групі -> user_id автора

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
    bot.send_message(message.chat.id, "Привіт! Вибери тип повідомлення (Повідомлення відправляються Анонімно!):", reply_markup=main_menu())

# -------------------- Вибір категорії --------------------
@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text in ['📛 Скарга', '💡 Пропозиція', '❓ Запитання', '📬 Інше'])
def choose_category(message):
    user_state[message.chat.id] = message.text
    bot.send_message(message.chat.id, "✍️ Введіть текст повідомлення:")

# -------------------- Обробка повідомлення від користувача --------------------
@bot.message_handler(func=lambda m: m.chat.type == "private" and m.chat.id in user_state, content_types=['text'])
def handle_user_submission(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    category = user_state.pop(chat_id)
    text = message.text or ""

    if is_banned(user_id):
        bot.send_message(chat_id, "⛔ Вас заблоковано.\nВи більше не можете надсилати повідомлення.")
        return

    # Логи (повні)
    logs = load_logs()
    logs.append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": category,
        "text": text,
        "user_id": user_id,
        "username": message.from_user.username or "",
        "link": user_link(user_id)
    })
    save_logs(logs)

    bot.send_message(chat_id, "✅ Ваше повідомлення надіслано. Дякуємо!")

    # Повідомлення в групу (скорочене)
    group_text = (
        f"📩 <b>Нове повідомлення</b>\n"
        f"Тип: {category}\n\n"
        f"{text}\n\n"
        f"ID: <code>{user_id}</code>"
    )

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("🚫 Заблокувати", callback_data=f"ban_{user_id}"),
        types.InlineKeyboardButton("✔️ Розблокувати", callback_data=f"unban_{user_id}")
    )

    if THREAD_ID:
        sent = bot.send_message(GROUP_ID, group_text, reply_markup=kb, parse_mode="HTML", message_thread_id=THREAD_ID)
    else:
        sent = bot.send_message(GROUP_ID, group_text, reply_markup=kb, parse_mode="HTML")

    msg_to_user[sent.message_id] = user_id

# -------------------- Callback кнопки --------------------
@bot.callback_query_handler(func=lambda c: c.data and (c.data.startswith("ban_") or c.data.startswith("unban_")))
def callback_ban_unban(call):
    if call.from_user.id != ADMIN_ID:
        call.answer("⛔ Тільки адміністратор", show_alert=True)
        return
    action, uid_str = call.data.split("_", 1)
    try:
        uid = int(uid_str)
    except:
        call.answer("Невірний ID", show_alert=True)
        return
    if action == "ban":
        add_ban(uid)
        try: bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except: pass
        bot.send_message(call.message.chat.id, f"🚫 Користувач {uid} заблокований.")
    else:
        remove_ban(uid)
        try: bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except: pass
        bot.send_message(call.message.chat.id, f"✔️ Користувач {uid} розблокований.")
    call.answer()

# -------------------- Reply у групі -> автору --------------------
@bot.message_handler(func=lambda m: m.chat.id == GROUP_ID and m.reply_to_message and m.reply_to_message.message_id in msg_to_user, content_types=['text'])
def group_reply_handler(message):
    original_user_id = msg_to_user.get(message.reply_to_message.message_id)
    if not original_user_id:
        return
    try:
        bot.send_message(original_user_id, f"📬 Відповідь на ваше повідомлення:\n\n{message.text}")
        bot.reply_to(message, "✅ Відповідь надіслана користувачу.")
    except:
        bot.reply_to(message, "❌ Не вдалося надіслати повідомлення користувачу.")

# -------------------- Команди адміну --------------------
@bot.message_handler(commands=['getlogs'])
def cmd_getlogs(message):
    if message.chat.type != "private" or message.from_user.id != ADMIN_ID:
        return
    logs = load_logs()
    if not logs:
        return bot.send_message(message.chat.id, "⚠️ Логи порожні.")
    fname = "logs.txt"
    with open(fname, "w", encoding="utf-8") as f:
        for l in logs:
            uname = format_username(l.get("username"))
            f.write(f"[{l.get('time')}] {l.get('type')}: {l.get('text')}\nID: {l.get('user_id')} | {uname} | {l.get('link')}\n\n")
    with open(fname, "rb") as f: bot.send_document(message.chat.id, f)
    os.remove(fname)

@bot.message_handler(commands=['getban'])
def cmd_getban(message):
    if message.chat.type != "private" or message.from_user.id != ADMIN_ID:
        return
    bl = load_banlist()
    if not bl:
        return bot.send_message(message.chat.id, "⚠️ Банлист порожній.")
    fname = "banlist.txt"
    with open(fname, "w", encoding="utf-8") as f:
        for b in bl:
            uname = format_username(b.get("username"))
            uid = b.get("user_id")
            f.write(f"{uname} | {uid} | {user_link(uid)}\n")
    with open(fname, "rb") as f: bot.send_document(message.chat.id, f)
    os.remove(fname)

@bot.message_handler(commands=['ban'])
def cmd_ban(message):
    if message.chat.type != "private" or message.from_user.id != ADMIN_ID:
        return
    try:
        uid = int(message.text.split()[1])
        add_ban(uid)
        bot.send_message(message.chat.id, f"🚫 Користувач {uid} заблокований.")
    except:
        bot.send_message(message.chat.id, "Невірний ID.")

@bot.message_handler(commands=['unban'])
def cmd_unban(message):
    if message.chat.type != "private" or message.from_user.id != ADMIN_ID:
        return
    try:
        uid = int(message.text.split()[1])
        remove_ban(uid)
        bot.send_message(message.chat.id, f"✔️ Користувач {uid} розблокований.")
    except:
        bot.send_message(message.chat.id, "Невірний ID.")

# -------------------- Щоденні логи адміну --------------------
def schedule_jobs():
    kyiv = pytz.timezone("Europe/Kyiv")
    while True:
        now = datetime.now(kyiv)
        target = now.replace(hour=20, minute=0, second=0, microsecond=0)

        if now > target:
            target = target + timedelta(days=1)

        wait_seconds = (target - now).total_seconds()
        time.sleep(wait_seconds)

        send_logs_daily()
        
# -------------------- Запуск --------------------
print("Бот запущено")
while True:
    try:
        bot.polling(non_stop=True)
    except Exception as e:
        print("Polling error:", e)
        time.sleep(5)


