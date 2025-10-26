# -*- coding: utf-8 -*-
import os
import telebot
from telebot import types
from flask import Flask
from threading import Thread
import re

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


# --- Беремо токен і ID групи з Environment Variables ---
TOKEN = os.environ['TOKEN']           # токен бота
GROUP_ID = int(os.environ['GROUP_ID'])  # ID групи
THREAD_ID = int(os.environ.get('THREAD_ID', 0))  # ID гілки (необов’язково)

bot = telebot.TeleBot(TOKEN)
user_state = {}  # для зберігання станів користувачів


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

    # --- Автоматичні відповіді користувачу ---
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


# --- Відповідь адміністратора через Reply (тільки у групі) ---
@bot.message_handler(func=lambda message: message.chat.id == GROUP_ID and message.reply_to_message)
def admin_reply(message):
    reply_text = message.text
    original = message.reply_to_message.text

    match = re.search(r'ID користувача: (\d+)', original)
    if match:
        user_id = int(match.group(1))
        bot.send_message(user_id, f"📬 Відповідь учнівського самоврядування:\n\n{reply_text}")
        bot.reply_to(message, "✅ Відповідь надіслано користувачу.")
    else:
        bot.reply_to(message, "⚠️ У цьому повідомленні немає ID користувача — відправити відповідь неможливо.")


print("✅ Бот запущений...")
bot.polling(non_stop=True)
