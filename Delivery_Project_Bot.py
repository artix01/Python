import telebot
from telebot import types
import sqlite3
import json
from datetime import datetime, timedelta
import time
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot.types import InputMediaPhoto
# Путь к файлу с настройками и ключами
config_file_path = 'config.json'

# Путь к файлу с историей изменений
history_file_path = 'history.json'

# Инициализация бота
with open(config_file_path, 'r') as config_file:
    config = json.load(config_file)
bot = telebot.TeleBot(config["token"])

# Подключение к базе данных SQLite
conn = sqlite3.connect('bot_database.db', check_same_thread=False)
cursor = conn.cursor()


# Основное меню
main_menu = types.ReplyKeyboardMarkup(resize_keyboard=True)
main_menu.add(types.KeyboardButton("Меню"))
main_menu.add(types.KeyboardButton("Корзина"))
main_menu.add(types.KeyboardButton("Оформить заказ"))
main_menu.add(types.KeyboardButton("История заказов"))
main_menu.add(types.KeyboardButton("Оценить блюдо"))

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    username = message.from_user.username
    address = ''
    basket = ''

    # Проверка наличия пользователя в базе данных
    with conn:
        cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        existing_user = cursor.fetchone()

        if not existing_user:
            # Если пользователя нет в базе данных, добавляем его
            cursor.execute("INSERT INTO users (user_id, username, address, basket) VALUES (?, ?, ?, ?)",
                           (user_id, username, address, basket))

    # Отправляем приветственное сообщение
    bot.send_message(user_id, "Привет! Я бот для заказа еды из ресторана. Как я могу помочь?", reply_markup=main_menu)

# Обработчик команды "Меню"
@bot.message_handler(func=lambda message: message.text == "Меню")
def handle_menu(message):
    user_id = message.from_user.id

    with conn:
        # Получаем список блюд из базы данных (предположим, что у вас есть таблица 'products')
        cursor.execute("SELECT * FROM products")
        dishes = cursor.fetchall()

        if dishes:
            # Если есть блюда, создаем InlineKeyboard с кнопками для каждого блюда
            keyboard = InlineKeyboardMarkup(row_width=1)

            for dish in dishes:
                dish_id, dish_name, dish_description, dish_price = dish
                button_text = f"{dish_name}\n{dish_description}\nЦена: {dish_price} руб."
                callback_data = f"add_to_cart:{dish_id}"  # пример callback_data, можно изменить по вашему усмотрению
                keyboard.add(InlineKeyboardButton(button_text, callback_data=callback_data))

            # Отправляем сообщение с меню блюд
            bot.send_message(user_id, "Выберите блюдо из меню:", reply_markup=keyboard)
        else:
            # Если меню пусто, уведомляем пользователя
            bot.send_message(user_id, "Извините, меню временно недоступно.")

# Обработчик команды "Корзина"
@bot.message_handler(func=lambda message: message.text == "Корзина")
def handle_cart_menu(message):
    user_id = message.from_user.id

    # Получаем текущую корзину пользователя
    with conn:
        cursor.execute("SELECT basket FROM users WHERE user_id=?", (user_id,))
        user_data = cursor.fetchone()

        if user_data:
            basket = json.loads(user_data[0]) if user_data[0] else []  # Разбираем JSON, если корзина не пуста
        else:
            basket = []

    if not basket:
        bot.send_message(user_id, "Ваша корзина пуста.")
        return

    # Формируем сообщение с продуктами в корзине
    cart_message = "Ваша корзина:\n"
    keyboard = types.InlineKeyboardMarkup()

    for item in basket:
        # Загружаем информацию о блюде из базы данных по его идентификатору
        cursor.execute("SELECT name FROM products WHERE product_id=?", (item['dish_id'],))
        product_info = cursor.fetchone()

        if product_info:
            dish_name = product_info[0]
            cart_message += f"{dish_name} (количество: {item['quantity']})\n"

            # Создаем callback_data с уникальным идентификатором блюда
            delete_callback_data = f"cart_item:delete:{item['dish_id']}"
            increase_callback_data = f"cart_item:increase:{item['dish_id']}"
            decrease_callback_data = f"cart_item:decrease:{item['dish_id']}"

            # Создаем кнопки для удаления, увеличения и уменьшения количества блюда
            delete_button = types.InlineKeyboardButton(f"Удалить {dish_name}", callback_data=delete_callback_data)
            increase_button = types.InlineKeyboardButton(f"+", callback_data=increase_callback_data)
            decrease_button = types.InlineKeyboardButton(f"-", callback_data=decrease_callback_data)

            keyboard.add(delete_button, increase_button, decrease_button)

    # Отправляем сообщение с корзиной и кнопками удаления, увеличения и уменьшения
    bot.send_message(user_id, cart_message, reply_markup=keyboard)


# Обработчик нажатия на кнопку в InlineKeyboard (удаление или изменение количества блюда в корзине)
@bot.callback_query_handler(func=lambda call: call.data.startswith("cart_item:"))
def handle_cart_item_callback(call):
    user_id = call.from_user.id
    action, dish_id = call.data.split(":")[1:]

    # Получаем текущую корзину пользователя
    with conn:
        cursor.execute("SELECT basket FROM users WHERE user_id=?", (user_id,))
        user_data = cursor.fetchone()

        if user_data:
            basket = json.loads(user_data[0]) if user_data[0] else []  # Разбираем JSON, если корзина не пуста
        else:
            basket = []

        # Находим позицию в корзине по dish_id
        selected_item = next((item for item in basket if item['dish_id'] == int(dish_id)), None)

        if selected_item:
            # Выполняем действие в зависимости от выбранной кнопки
            if action == "delete":
                # Удаляем блюдо из корзины
                basket.remove(selected_item)
            elif action == "increase":
                # Увеличиваем количество блюда
                selected_item['quantity'] += 1
            elif action == "decrease":
                # Уменьшаем количество блюда, не может быть меньше 1
                selected_item['quantity'] = max(1, selected_item['quantity'] - 1)

            # Обновляем корзину в базе данных
            cursor.execute("UPDATE users SET basket = ? WHERE user_id = ?", (json.dumps(basket), user_id))

    # Обновляем сообщение с корзиной после удаления или изменения количества
    update_cart_message(call.message)

# Обработчик нажатия на кнопку в InlineKeyboard(menu)
@bot.callback_query_handler(func=lambda call: call.data.startswith("add_to_cart:"))
def handle_inline_callback(call):
    user_id = call.from_user.id
    dish_id = int(call.data.split(":")[1])

    # Получаем текущую корзину пользователя
    with conn:
        cursor.execute("SELECT basket FROM users WHERE user_id=?", (user_id,))
        user_data = cursor.fetchone()

        if user_data:
            basket = json.loads(user_data[0]) if user_data[0] else []  # Разбираем JSON, если корзина не пуста
        else:
            basket = []

        # Проверяем, есть ли уже такое блюдо в корзине
        existing_dish = next((item for item in basket if item['dish_id'] == dish_id), None)

        if existing_dish:
            # Если блюдо уже в корзине, увеличиваем количество
            existing_dish['quantity'] += 1
        else:
            # Если блюда нет в корзине, добавляем его
            new_dish = {'dish_id': dish_id, 'quantity': 1}
            basket.append(new_dish)

        # Обновляем корзину в базе данных
        cursor.execute("UPDATE users SET basket = ? WHERE user_id = ?", (json.dumps(basket), user_id))

    # Отправляем сообщение, что блюдо добавлено в корзину
    bot.answer_callback_query(callback_query_id=call.id, show_alert=True, text="Блюдо добавлено в корзину!")

    # Обновляем сообщение с корзиной после добавления блюда
    update_cart_message(call.message)

def update_cart_message(message):
    user_id = message.chat.id

    # Получаем текущую корзину пользователя
    with conn:
        cursor.execute("SELECT basket FROM users WHERE user_id=?", (user_id,))
        user_data = cursor.fetchone()

        if user_data:
            basket = json.loads(user_data[0]) if user_data[0] else []  # Разбираем JSON, если корзина не пуста
        else:
            basket = []

    if not basket:
        bot.send_message(user_id, "Ваша корзина пуста.")
        return

    # Формируем сообщение с продуктами в корзине
    cart_message = "Ваша корзина:\n"
    keyboard = types.InlineKeyboardMarkup()

    for item in basket:
        # Загружаем информацию о блюде из базы данных по его идентификатору
        cursor.execute("SELECT name FROM products WHERE product_id=?", (item['dish_id'],))
        product_info = cursor.fetchone()

        if product_info:
            dish_name = product_info[0]
            cart_message += f"{dish_name} (количество: {item['quantity']})\n"

            # Создаем callback_data с уникальным идентификатором блюда
            delete_callback_data = f"cart_item:delete:{item['dish_id']}"
            increase_callback_data = f"cart_item:increase:{item['dish_id']}"
            decrease_callback_data = f"cart_item:decrease:{item['dish_id']}"

            # Создаем кнопки для удаления, увеличения и уменьшения количества блюда
            delete_button = types.InlineKeyboardButton(f"Удалить {dish_name}", callback_data=delete_callback_data)
            increase_button = types.InlineKeyboardButton(f"+", callback_data=increase_callback_data)
            decrease_button = types.InlineKeyboardButton(f"-", callback_data=decrease_callback_data)

            keyboard.add(delete_button, increase_button, decrease_button)

    # Отправляем сообщение с корзиной и кнопками удаления, увеличения и уменьшения
    bot.edit_message_text(chat_id=user_id, message_id=message.message_id, text=cart_message, reply_markup=keyboard)


# Обработчик команды "Оформить заказ"
@bot.message_handler(func=lambda message: message.text == "Оформить заказ")
def handle_checkout(message):
    user_id = message.from_user.id

    with conn:
        # Проверяем, есть ли позиции в корзине
        cursor.execute("SELECT basket FROM users WHERE user_id=?", (user_id,))
        basket = cursor.fetchone()

        if basket and basket[0]:
            # Если корзина не пуста, показываем кнопку "Оформить заказ"
            bot.send_message(user_id, "Вы можете оформить заказ", reply_markup=types.ReplyKeyboardMarkup(
                keyboard=[types.KeyboardButton("Оформить заказ")], resize_keyboard=True
            ))
        else:
            # Если корзина пуста, уведомляем пользователя и убираем кнопку "Оформить заказ"
            bot.send_message(user_id, "Ваша корзина пуста")


# Обработчик команды "Оценить блюдо"
@bot.message_handler(func=lambda message: message.text == "Оценить блюдо")
def handle_rate_dish(message):
    user_id = message.from_user.id

    with conn:
        # Проверяем, есть ли успешные заказы
        cursor.execute("SELECT * FROM orders WHERE user_id=?", (user_id,))
        successful_orders = cursor.fetchall()

        if successful_orders:
            # Если есть успешные заказы, показываем кнопку "Оценить блюдо"
            bot.send_message(user_id, "Оцените блюдо", reply_markup=types.ReplyKeyboardMarkup(
                keyboard=[types.KeyboardButton("Оценить блюдо")], resize_keyboard=True
            ))
        else:
            # Если нет успешных заказов, уведомляем пользователя и убираем кнопку "Оценить блюдо"
            bot.send_message(user_id, "У вас нет успешных заказов для оценки")


# Запуск бота
print("Ready")
bot.infinity_polling()
