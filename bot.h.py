# -- coding: utf-8 --

import os
import asyncio
import requests
from datetime import datetime
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# -------------------- Flask-сервер для Render --------------------
app = Flask('')

@app.route('/')
def home():
    return "✅ Бот працює 24/7 на Render!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

Thread(target=run).start()

# -------------------- Змінні --------------------
TOKEN = os.environ['TOKEN']
ADMIN_ID = int(os.environ['ADMIN_ID'])
JSONBIN_API_KEY = os.environ['JSONBIN_API_KEY']
BANLIST_BIN_ID = os.environ['BANLIST_BIN_ID']
LOGS_BIN_ID = os.environ['LOGS_BIN_ID']
GROUP_ID = int(os.environ['GROUP_ID'])
THREAD_ID = int(os.environ.get('THREAD_ID', 0))

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

# -------------------- Керування станом користувача --------------------
user_state = {}  # chat_id -> category

def get_user_display_name(user):
    if user.username:
        return f"@{user.username}"
    else:
        return f"[{user.first_name}](tg://user?id={user.id})"

# -------------------- Головне меню --------------------
def main_menu():
    return ReplyKeyboardMarkup(
        [['📛 Скарга', '💡 Пропозиція'], ['❓ Запитання', '📬 Інше']],
        resize_keyboard=True, one_time_keyboard=True
    )

# -------------------- Команди адміну --------------------
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if len(context.args) == 0:
        await update.message.reply_text("Вкажи ID користувача: /ban 123456")
        return
    user_id = int(context.args[0])
    banlist = load_banlist()
    if user_id not in banlist:
        banlist.append(user_id)
        save_banlist(banlist)
        await update.message.reply_text(f"🔒 Користувач {user_id} заблокований")
    else:
        await update.message.reply_text("Він вже заблокований.")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if len(context.args) == 0:
        await update.message.reply_text("Вкажи ID: /unban 123456")
        return
    user_id = int(context.args[0])
    banlist = load_banlist()
    if user_id in banlist:
        banlist.remove(user_id)
        save_banlist(banlist)
        await update.message.reply_text(f"✔ Користувач {user_id} розблокований")
    else:
        await update.message.reply_text("ID не знайдено у бані.")

# -------------------- /banlogs --------------------
async def banlogs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    banlist = load_banlist()
    if not banlist:
        await update.message.reply_text("⚠️ Список заблокованих порожній.")
        return

    text = "📌 Заблоковані користувачі:\n"
    for user_id in banlist:
        text += f"- [{user_id}](tg://user?id={user_id})\n"
    await update.message.reply_text(text, parse_mode="Markdown")
    # -------------------- Кнопки Заблокувати / Розблокувати --------------------
async def block_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return

    user_id = int(query.data.split("_")[1])
    action = query.data.split("_")[0]
    banlist = load_banlist()

    if action == "ban":
        if user_id not in banlist:
            banlist.append(user_id)
            save_banlist(banlist)
            await query.edit_message_reply_markup(None)
            await query.message.reply_text(f"🔒 Користувач {user_id} заблокований кнопкою")
        else:
            await query.answer("Він вже заблокований", show_alert=True)
    elif action == "unban":
        if user_id in banlist:
            banlist.remove(user_id)
            save_banlist(banlist)
            await query.edit_message_reply_markup(None)
            await query.message.reply_text(f"✔ Користувач {user_id} розблокований кнопкою")
        else:
            await query.answer("Він не заблокований", show_alert=True)

# -------------------- /start --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! Вибери тип повідомлення:\n\n"
        "📛 Скарга / 💡 Пропозиція / ❓ Запитання / 📬 Інше — усі повідомлення анонімні.\n"
        "Ми цінуємо вашу конфіденційність 💬",
        reply_markup=main_menu()
    )

# -------------------- Обробка повідомлень --------------------
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    user_id = user.id
    text = update.message.text
    banlist = load_banlist()

    # -------------------- Якщо заблокований --------------------
    if user_id in banlist:
        await update.message.reply_text("⛔ Вас заблоковано і ви не можете надсилати повідомлення.")
        return

    # -------------------- Вибір категорії --------------------
    if text in ['📛 Скарга', '💡 Пропозиція', '❓ Запитання', '📬 Інше']:
        user_state[chat_id] = text
        await update.message.reply_text("✍️ Введіть текст повідомлення (воно залишиться анонімним):")
        return

    # -------------------- Обробка повідомлення --------------------
    if chat_id in user_state:
        category = user_state.pop(chat_id)
        display_name = get_user_display_name(user)

        # Логування на JSONBin
        logs = load_logs()
        logs.append({
            "user_id": user_id,
            "username": display_name,
            "category": category,
            "text": text,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        save_logs(logs)

        # Відповідь користувачу
        await update.message.reply_text("✅ Ваше повідомлення отримано. Ми цінуємо вашу конфіденційність і думки.")

        # Надсилання в групу + гілку з кнопками
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔒 Заблокувати", callback_data=f"ban_{user_id}"),
             InlineKeyboardButton("✅ Розблокувати", callback_data=f"unban_{user_id}")]
        ])
        await context.bot.send_message(
            chat_id=GROUP_ID,
            text=f"📩 *Нове повідомлення ({category}):*\n\n{text}\n\nВід користувача: {display_name}",
            parse_mode="Markdown",
            message_thread_id=THREAD_ID or None,
            reply_markup=keyboard
        )

# -------------------- Щоденна відправка логів адміну --------------------
async def send_logs_daily(app):
    while True:
        now = datetime.now()
        if now.hour == 20 and now.minute == 0:
            logs = load_logs()
            if logs:
                with open("logs.txt", "w", encoding="utf-8") as f:
                    for l in logs:
                        f.write(f"[{l['time']}] {l['user_id']} ({l['username']}, {l['category']}): {l['text']}\n")
                with open("logs.txt", "rb") as f:
                    await app.bot.send_document(chat_id=ADMIN_ID, document=f)
                os.remove("logs.txt")
            await asyncio.sleep(60)
        await asyncio.sleep(20)

# -------------------- Запуск --------------------
async def main():
    print("Бот запущено... Чекаю повідомлень")
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("banlogs", banlogs))
    app.add_handler(CallbackQueryHandler(block_button_callback, pattern=r"^(ban|unban)_\d+$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    asyncio.create_task(send_logs_daily(app))

    await app.run_polling()

if__name__=="__main__":
    import asyncio
    asyncio.run(main())
