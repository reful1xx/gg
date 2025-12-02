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
GROUP_ID = int(os.environ['GROUP_ID'])           # ID групи, куди надсилати повідомлення
THREAD_ID = int(os.environ.get('THREAD_ID', 0))  # id гілки (thread) або 0
ADMIN_ID = int(os.environ['ADMIN_ID'])

JSONBIN_API_KEY = os.environ['JSONBIN_API_KEY']
LOGS_BIN_ID = os.environ['LOGS_BIN_ID']
BANLIST_BIN_ID = os.environ['BANLIST_BIN_ID']

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# -------------------- Стан користувача --------------------
# коли користувач у приваті вибрав категорію, ми чекаємо його повідомлення
user_state = {}               # chat_id -> category
# мапа: message_id (в групі) -> user_id (оригінального автора)
msg_to_user = {}

# -------------------- JSONBin допоміжні --------------------
def load_jsonbin(bin_id):
    url = f"https://api.jsonbin.io/v3/b/{bin_id}/latest"
    headers = {"X-Master-Key": JSONBIN_API_KEY}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json().get('record', [])
    except Exception as e:
        print("JSONBin load error:", e)
    return []

def save_jsonbin(bin_id, data):
    url = f"https://api.jsonbin.io/v3/b/{bin_id}"
    headers = {"X-Master-Key": JSONBIN_API_KEY, "Content-Type": "application/json"}
    try:
        requests.put(url, json=data, headers=headers, timeout=10)
    except Exception as e:
        print("JSONBin save error:", e)

# -------------------- Банлист / Логи --------------------
def load_banlist():
    # банлист зберігається як список об'єктів: {"user_id": 123, "username": "name"}
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

def update_username_in_banlist(user_id, username):
    bl = load_banlist()
    changed = False
    for b in bl:
        if b.get("user_id") == int(user_id):
            if (b.get("username") or "") != (username or ""):
                b["username"] = username or ""
                changed = True
            break
    if changed:
        save_banlist(bl)

def add_ban(user_id, username=""):
    bl = load_banlist()
    if not any(b.get("user_id") == int(user_id) for b in bl):
        bl.append({"user_id": int(user_id), "username": username or ""})
        save_banlist(bl)

def remove_ban(user_id):
    bl = load_banlist()
    bl = [b for b in bl if b.get("user_id") != int(user_id)]
    save_banlist(bl)

# -------------------- Утиліти для username/link --------------------
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

# -------------------- /start (тільки в приваті) --------------------
@bot.message_handler(commands=['start'])
def start_cmd(message):
    if message.chat.type != "private":
        return  # ігноруємо виклики /start у групах
    bot.send_message(message.chat.id,
                     "Привіт! Виберіть тип повідомлення:",
                     reply_markup=main_menu())

# -------------------- Вибір категорії (приват) --------------------
@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text in ['📛 Скарга', '💡 Пропозиція', '❓ Запитання', '📬 Інше'])
def choose_category(message):
    user_state[message.chat.id] = message.text
    bot.send_message(message.chat.id, "✍️ Введіть текст повідомлення (воно буде анонімно переслане в групу):")

# -------------------- Обробка повідомлення від користувача після вибору категорії (приват) --------------------
@bot.message_handler(func=lambda m: m.chat.type == "private" and m.chat.id in user_state, content_types=['text'])
def handle_user_submission(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    category = user_state.pop(chat_id)  # беремо та видаляємо стан
    text = message.text or ""

    # Якщо забанений — відповідаємо, нічого не логгуємо і не пересилаємо
    if is_banned(user_id):
        bot.send_message(chat_id, "⛔ Вас заблоковано.\nВи більше не можете надсилати повідомлення.")
        return

    # Оновлюємо username у банлисті якщо треба
    update_username_in_banlist(user_id, message.from_user.username or "")

    # --- Логування у JSONBin ---
    logs = load_logs()
    entry = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": category,
        "text": text,
        "user_id": user_id,
        "username": message.from_user.username or "",
        "link": user_link(user_id)
    }
    logs.append(entry)
    save_logs(logs)

    # --- Підтвердження користувачу ---
    bot.send_message(chat_id, "✅ Ваше повідомлення надіслано. Дякуємо!")

    # --- Формуємо повідомлення для групи (в гілку, якщо THREAD_ID заданий) ---
    display_uname = format_username(message.from_user.username)
    group_text = (
        f"📩 <b>Нове повідомлення</b>\n"
        f"Тип: {category}\n\n"
        f"{text}\n\n"
        f"ID: <code>{user_id}</code>\n"
        f"Username: {display_uname}\n"
        f"Посилання: {user_link(user_id)}"
    )

    # Inline клавіатура: кнопки для адміна
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🚫 Заблокувати", callback_data=f"ban_{user_id}"),
           types.InlineKeyboardButton("✔️ Розблокувати", callback_data=f"unban_{user_id}"))

    # Надсилаємо в групу (в гілку якщо THREAD_ID)
    if THREAD_ID:
        sent = bot.send_message(GROUP_ID, group_text, reply_markup=kb, parse_mode="HTML", message_thread_id=THREAD_ID)
    else:
        sent = bot.send_message(GROUP_ID, group_text, reply_markup=kb, parse_mode="HTML")

    # Зберігаємо відповідність групового повідомлення -> оригінальний user_id
    try:
        msg_to_user[sent.message_id] = user_id
    except Exception:
        # деякі старі версії бібліотеки можуть не повертати message_id у відповіді
        pass

# -------------------- Callback: бан/розбан (тільки адмін може) --------------------
@bot.callback_query_handler(func=lambda call: call.data and (call.data.startswith("ban_") or call.data.startswith("unban_")))
def callback_ban_unban(call):
    # дозволяємо натискати лише адміну
    if call.from_user.id != ADMIN_ID:
        call.answer("⛔ Тільки адміністратор може виконувати цю дію", show_alert=True)
        return

    data = call.data
    action, uid_str = data.split("_", 1)
    try:
        uid = int(uid_str)
    except:
        call.answer("Невірний ID", show_alert=True)
        return

    if action == "ban":
        # отримуємо username (якщо можливо) щоб додати в банліст
        username = ""
        try:
            chat = bot.get_chat(uid)
            username = chat.username or ""
        except:
            username = ""
        add_ban(uid, username)
        # прибираємо reply_markup
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except:
            pass
        bot.send_message(call.message.chat.id, f"🚫 Користувач {uid} заблокований.")
    else:  # unban
        remove_ban(uid)
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except:
            pass
        bot.send_message(call.message.chat.id, f"✔️ Користувач {uid} розблокований.")

    call.answer()

# -------------------- Reply у групі -> надсилати автору (будь-хто може відповідати) --------------------
@bot.message_handler(func=lambda m: m.chat.id == GROUP_ID and m.reply_to_message and m.reply_to_message.message_id in msg_to_user, content_types=['text'])
def group_reply_handler(message):
    original_group_msg_id = message.reply_to_message.message_id
    user_id = msg_to_user.get(original_group_msg_id)
    if not user_id:
        return

    # Надсилаємо текст автору
    try:
        bot.send_message(user_id, f"📬 Відповідь до вашого повідомлення:\n\n{message.text}")
        # підтверджуємо у групі
        bot.reply_to(message, "✅ Відповідь відправлена користувачу.")
    except Exception as e:
        bot.reply_to(message, "❌ Не вдалося надіслати повідомлення користувачу.")

# -------------------- Команди адміну у ЛС: /getlogs, /getban, /ban, /unban --------------------
@bot.message_handler(commands=['getlogs'])
def cmd_getlogs(message):
    # команда тільки у приваті адміну
    if message.chat.type != "private" or message.from_user.id != ADMIN_ID:
        return bot.reply_to(message, "❗ Цю команду використовуйте в ЛС (тільки адмiн).")
    logs = load_logs()
    if not logs:
        return bot.send_message(message.chat.id, "⚠️ Логи порожні.")
    # формуємо текстовий файл
    fname = "logs.txt"
    with open(fname, "w", encoding="utf-8") as f:
        for l in logs:
            uname = format_username(l.get("username"))
            f.write(f"[{l.get('time')}]\nТип: {l.get('type')}\nПовідомлення: \"{l.get('text')}\"\nID: {l.get('user_id')}\nUsername: {uname}\nПосилання: {l.get('link')}\n\n")
    with open(fname, "rb") as f:
        bot.send_document(message.chat.id, f)
    os.remove(fname)

@bot.message_handler(commands=['getban'])
def cmd_getban(message):
    if message.chat.type != "private" or message.from_user.id != ADMIN_ID:
        return bot.reply_to(message, "❗ Цю команду використовуйте в ЛС (тільки адмiн).")
    bl = load_banlist()
    if not bl:
        return bot.send_message(message.chat.id, "⚠️ Банлист порожній.")
    fname = "banlist.txt"
    with open(fname, "w", encoding="utf-8") as f:
        for b in bl:
            uname = format_username(b.get("username"))
            uid = b.get("user_id")
            f.write(f"{uname} | {uid} | {user_link(uid)}\n")
    with open(fname, "rb") as f:
        bot.send_document(message.chat.id, f)
    os.remove(fname)

@bot.message_handler(commands=['ban'])
def cmd_ban(message):
    if message.chat.type != "private" or message.from_user.id != ADMIN_ID:
        return bot.reply_to(message, "❗ Цю команду використовуйте в ЛС (тільки адмiн).")
    parts = message.text.split()
    if len(parts) < 2:
        return bot.send_message(message.chat.id, "Використання: /ban USER_ID")
    try:
        uid = int(parts[1])
        username = ""
        try:
            chat = bot.get_chat(uid)
            username = chat.username or ""
        except:
            username = ""
        add_ban(uid, username)
        bot.send_message(message.chat.id, f"🚫 Користувач {uid} заблокований.")
    except:
        bot.send_message(message.chat.id, "Невірний ID.")

@bot.message_handler(commands=['unban'])
def cmd_unban(message):
    if message.chat.type != "private" or message.from_user.id != ADMIN_ID:
        return bot.reply_to(message, "❗ Цю команду використовуйте в ЛС (тільки адмiн).")
    parts = message.text.split()
    if len(parts) < 2:
        return bot.send_message(message.chat.id, "Використання: /unban USER_ID")
    try:
        uid = int(parts[1])
        remove_ban(uid)
        bot.send_message(message.chat.id, f"✔️ Користувач {uid} розблокований.")
    except:
        bot.send_message(message.chat.id, "Невірний ID.")

# -------------------- Щоденна відправка логів адміну о 20:00 --------------------
def send_logs_daily():
    logs = load_logs()
    if not logs:
        return
    fname = "daily_logs.txt"
    with open(fname, "w", encoding="utf-8") as f:
        for l in logs:
            uname = format_username(l.get("username"))
            f.write(f"[{l.get('time')}]\nТип: {l.get('type')}\nПовідомлення: \"{l.get('text')}\"\nID: {l.get('user_id')}\nUsername: {uname}\nПосилання: {l.get('link')}\n\n")
    with open(fname, "rb") as f:
        bot.send_document(ADMIN_ID, f)
    os.remove(fname)

def schedule_jobs():
    schedule.every().day.at("20:00").do(send_logs_daily)
    while True:
        schedule.run_pending()
        time.sleep(30)

Thread(target=schedule_jobs, daemon=True).start()

# -------------------- Запуск бота --------------------
print("Бот запущено")
while True:
    try:
        bot.polling(non_stop=True)
    except Exception as e:
        print("Polling error:", e)
        time.sleep(5)
