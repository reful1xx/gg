# -*- coding: utf-8 -*-
import os
import telebot
from flask import Flask
from threading import Thread

# --- Налаштування ---
TOKEN = os.environ['TOKEN']  # Токен бота з BotFather
bot = telebot.TeleBot(TOKEN)

# --- Flask-сервер для Render ---
app = Flask('')

@app.route('/')
def home():
    return "✅ Бот працює 24/7 на Render!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

Thread(target=run_flask).start()

# --- Команда для отримання Thread ID ---
@bot.message_handler(commands=['threadid'])
def thread_id_check(message):
    if message.message_thread_id:
        bot.reply_to(message, f"🧩 ID цієї гілки: {message.message_thread_id}", parse_mode="Markdown")
        print(f"Chat ID: {message.chat.id}, Thread ID: {message.message_thread_id}")
    else:
        bot.reply_to(message, "⚠️ Ця гілка не є форумною (немає thread_id).")
        print(f"Chat ID: {message.chat.id}, Thread ID: None")

# --- Лог всіх повідомлень для дебагу ---
@bot.message_handler(func=lambda m: True)
def debug(message):
    print("===========")
    print("From:", message.from_user.id, message.from_user.username)
    print("Chat ID:", message.chat.id)
    print("Thread ID:", message.message_thread_id)
    print("Text:", message.text)
    print("===========")

# --- Запуск бота у окремому потоці ---
def run_bot():
    print("✅ Бот запускається...")
    bot.polling(non_stop=True)

Thread(target=run_bot).start()
