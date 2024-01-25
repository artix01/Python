import telebot
from telebot import types
import sqlite3
import json
from datetime import datetime, timedelta
import time
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot.types import InputMediaPhoto

# Подключение к базе данных SQLite
conn = sqlite3.connect('bot_database.db')
cursor = conn.cursor()

# Создание таблицы пользователей
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    address TEXT,
                    basket TEXT
                )''')

# Создание таблицы для администраторов
cursor.execute('''CREATE TABLE IF NOT EXISTS administrators (
                    admin_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    admin_level INTEGER     
                )''')

# Создание таблицы клиентов
cursor.execute('''CREATE TABLE IF NOT EXISTS customers (
                    user_id INTEGER PRIMARY KEY,
                    name TEXT,
                    email TEXT,
                    address TEXT,
                    payment_method TEXT
                )''')

# Создание таблицы заказов
cursor.execute('''CREATE TABLE IF NOT EXISTS orders (
                    user_id INTEGER PRIMARY KEY,
                    customer_id INTEGER,
                    product_id INTEGER,
                    quantity INTEGER,
                    FOREIGN KEY (customer_id) REFERENCES customers (id),
                    FOREIGN KEY (product_id) REFERENCES products (id)
                )''')

# Создание таблицы продуктов
cursor.execute('''CREATE TABLE IF NOT EXISTS products (
                    product_id INTEGER PRIMARY KEY,
                    name TEXT,
                    description TEXT,
                    price REAL
                )''')

conn.commit()