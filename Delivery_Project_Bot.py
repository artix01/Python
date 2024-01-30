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
bot = telebot.TeleBot(config["tg_token"])

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
    register_user(message)

def register_user(message):
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
            conn.commit()

            # Запрос информации у пользователя
            bot.send_message(user_id, "Привет! Давайте соберем некоторую информацию для регистрации.")
            bot.send_message(user_id, "Как вас зовут?")
            bot.register_next_step_handler(message, lambda msg: process_step(msg, 'name'))
        else:
            # Проверка наличия всех данных в таблице customers
            cursor.execute("SELECT * FROM customers WHERE user_id=?", (user_id,))
            customer_data = cursor.fetchone()

            if not customer_data or any(
                    item is None for item in customer_data[1:]):  # Проверяем, есть ли хоть одно пустое поле
                # Если хотя бы одно поле не заполнено, продолжаем регистрацию
                bot.send_message(user_id, "Привет! Давайте продолжим регистрацию.")
                bot.send_message(user_id, "Как вас зовут?")
                bot.register_next_step_handler(message, lambda msg: process_step(msg, 'name'))
            else:
                # Если все поля заполнены, считаем регистрацию завершенной
                bot.send_message(user_id, "Привет! Как я могу помочь?", reply_markup=main_menu)

def process_step(message, step):
    user_id = message.from_user.id

    with conn:
        cursor.execute("SELECT * FROM customers WHERE user_id=?", (user_id,))
        existing_customer = cursor.fetchone()

    if not existing_customer or any(item is None for item in existing_customer[1:]):  # Проверяем, есть ли хоть одно пустое поле
        # Новый пользователь или не все данные заполнены, добавляем/обновляем в базе данных
        if step == 'name':
            # Обрабатываем шаг с именем
            name = message.text
            with conn:
                cursor.execute("INSERT INTO customers (user_id, name) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET name = ?",
                               (user_id, name, name))
            conn.commit()

            # Переходим ко второму шагу
            bot.send_message(user_id, "Отлично, теперь укажите свой email:")
            bot.register_next_step_handler(message, lambda msg: process_step(msg, 'email'))

        elif step == 'email':
            # Обрабатываем шаг с email
            email = message.text
            with conn:
                cursor.execute("UPDATE customers SET email = ? WHERE user_id = ?", (email, user_id))
            conn.commit()

            # Переходим к следующему шагу
            bot.send_message(user_id, "Спасибо! Теперь укажите свой адрес:")
            bot.register_next_step_handler(message, lambda msg: process_step(msg, 'address'))

        elif step == 'address':
            # Обрабатываем шаг с адресом
            address = message.text
            with conn:
                cursor.execute("UPDATE customers SET address = ? WHERE user_id = ?", (address, user_id))
            conn.commit()

            # Переходим к следующему шагу
            bot.send_message(user_id, "Отлично! Теперь выберите метод оплаты:", reply_markup=payment_method_keyboard())
            bot.register_next_step_handler(message, lambda msg: process_step(msg, 'payment_method'))

        elif step == 'payment_method':
            # Обрабатываем шаг с выбором метода оплаты
            payment_method = message.text
            with conn:
                cursor.execute("UPDATE customers SET payment_method = ? WHERE user_id = ?", (payment_method, user_id))
            conn.commit()

            # Регистрация завершена, отправляем приветственное сообщение
            bot.send_message(user_id, "Спасибо за регистрацию! Теперь вы можете начать пользоваться ботом.", reply_markup=main_menu)
    else:
        # Пользователь уже зарегистрирован и все данные заполнены, отправляем приветственное сообщение
        bot.send_message(user_id, "Привет! Как я могу помочь?", reply_markup=main_menu)

def payment_method_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("Карта"))
    keyboard.add(types.KeyboardButton("Наличные"))
    return keyboard

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
            # Если корзина не пуста, предлагаем выбор адреса
            keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)

            # Получаем адрес из регистрации
            cursor.execute("SELECT address FROM customers WHERE user_id=?", (user_id,))
            user_data = cursor.fetchone()

            if user_data and user_data[0]:
                address = user_data[0]
                keyboard.add(types.KeyboardButton(address))
            else:
                # Если адреса в регистрации нет, предлагаем указать адрес
                keyboard.add(types.KeyboardButton("Указать адрес"))

            bot.send_message(user_id, "Выберите или укажите адрес:", reply_markup=keyboard)
            bot.register_next_step_handler(message, lambda msg: address_step(msg, 'address_choice'))
        else:
            # Если корзина пуста, уведомляем пользователя
            bot.send_message(user_id, "Ваша корзина пуста")

def calculate_total_price(basket):
    total_price = 0

    with conn:
        for item in basket:
            dish_id = item['dish_id']

            # Получаем цену товара из таблицы products
            cursor.execute("SELECT price FROM products WHERE product_id=?", (dish_id,))
            product_info = cursor.fetchone()

            if product_info:
                price = product_info[0]
                quantity = item['quantity']

                # Суммируем цены товаров
                total_price += price * quantity

    return total_price

# Обработка шага "address_choice"
def address_step(message, step):
    user_id = message.from_user.id
    basket = []

    if step == 'address_choice':
        # Пользователь выбрал адрес из регистрации
        address = message.text

        # Получаем данные о корзине пользователя
        with conn:
            cursor.execute("SELECT basket FROM users WHERE user_id=?", (user_id,))
            user_data = cursor.fetchone()

            if user_data:
                basket = json.loads(user_data[0]) if user_data[0] else []


        # Вычисляем общую стоимость заказа
        total_price = calculate_total_price(basket)  # Реализуйте эту функцию

        # Вставляем запись в таблицу orders
        with conn:
            cursor.execute("INSERT INTO orders (user_id, address, total_price, estimated_delivery_time, basket) "
                           "VALUES (?, ?, ?, ?, ?)",
                           (user_id, address, total_price, 30, json.dumps(basket)))
            conn.commit()

            # Очищаем корзину пользователя
            cursor.execute("UPDATE users SET basket = ? WHERE user_id = ?", (None, user_id))
            conn.commit()

        # Отправляем пользователю примерное время ожидания
        estimated_delivery_time = 30  # в минутах
        bot.send_message(user_id, f"Спасибо! Ваш заказ принят. Ожидайте доставку по адресу: {address}. "
                                   f"Примерное время ожидания: {estimated_delivery_time} минут.", reply_markup=main_menu)

# Функция для отображения истории заказов
def show_order_history(user_id):
    with conn:
        # Получаем все заказы пользователя из таблицы orders
        cursor.execute("SELECT order_id, total_price, estimated_delivery_time FROM orders WHERE user_id=?", (user_id,))
        orders = cursor.fetchall()

    if orders:
        # Если есть заказы, формируем клавиатуру с их списком
        keyboard = types.InlineKeyboardMarkup()

        for order in orders:
            order_id, total_price, estimated_delivery_time = order
            callback_data = f"order_info:{order_id}"
            button_text = f"Заказ #{order_id}, Сумма: {total_price} руб., Время доставки: {estimated_delivery_time} мин."
            keyboard.add(types.InlineKeyboardButton(button_text, callback_data=callback_data))

        # Отправляем сообщение с клавиатурой
        bot.send_message(user_id, "Выберите заказ из истории:", reply_markup=keyboard)
    else:
        # Если нет заказов, уведомляем пользователя
        bot.send_message(user_id, "У вас пока нет заказов в истории.")

# Обработчик нажатия на кнопку с информацией о заказе
@bot.callback_query_handler(func=lambda call: call.data.startswith("order_info:"))
def handle_order_info_callback(call):
    user_id = call.from_user.id
    order_id = int(call.data.split(":")[1])

    # Получаем информацию о заказе из базы данных
    with conn:
        cursor.execute("SELECT total_price, estimated_delivery_time, basket FROM orders WHERE order_id=? AND user_id=?", (order_id, user_id))
        order_info = cursor.fetchone()

    if order_info:
        total_price, estimated_delivery_time, basket_json = order_info
        basket = json.loads(basket_json) if basket_json else []

        # Формируем сообщение с информацией о заказе
        order_message = f"Информация о заказе #{order_id}:\n\n"
        for item in basket:
            # Загружаем информацию о блюде из базы данных по его идентификатору
            cursor.execute("SELECT name FROM products WHERE product_id=?", (item['dish_id'],))
            product_info = cursor.fetchone()

            if product_info:
                dish_name = product_info[0]
                order_message += f"{dish_name} (количество: {item['quantity']})\n"

        order_message += f"\nИтого: {total_price} руб.\n"
        order_message += f"Примерное время ожидания: {estimated_delivery_time} минут."

        # Отправляем сообщение с информацией о заказе
        bot.edit_message_text(chat_id=user_id, message_id=call.message.message_id, text=order_message)
    else:
        # Если информация о заказе не найдена, отправляем уведомление
        bot.answer_callback_query(callback_query_id=call.id, show_alert=True, text="Информация о заказе не найдена.")

@bot.message_handler(func=lambda message: message.text == "История заказов")
def handle_order_history(message):
    user_id = message.from_user.id
    show_order_history(user_id)


"""# Обработчик команды "Оценить блюдо"
@bot.message_handler(func=lambda message: message.text == "Оценить блюдо")
def handle_rate_dish(message):
    user_id = message.from_user.id

    with conn:
        # Получаем блюда из базы данных
        cursor.execute("SELECT * FROM products")
        dishes = cursor.fetchall()

        # Генерируем клавиатуру с блюдами для оценки
        keyboard = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
        for dish in dishes:
            dish_id, dish_name, _, _, _, _ = dish
            keyboard.add(types.KeyboardButton(f"Оценить {dish_name}"))

        bot.send_message(user_id, "Выберите блюдо для оценки:", reply_markup=keyboard)

# Обработчик для оценки блюда
@bot.message_handler(func=lambda message: message.text.startswith("Оценить "))
def handle_dish_rating(message):
    user_id = message.from_user.id
    dish_name = message.text.replace("Оценить ", "")

    with conn:
        # Получаем информацию о блюде
        cursor.execute("SELECT * FROM products WHERE name=?", (dish_name,))
        dish_info = cursor.fetchone()

        if dish_info:
            dish_id, _, _, _, rating, total_ratings = dish_info

            # Получаем текущую оценку блюда от пользователя
            cursor.execute("SELECT rating FROM dish_comments WHERE user_id=? AND product_id=?", (user_id, dish_id))
            user_rating = cursor.fetchone()

            if user_rating:
                bot.send_message(user_id, f"Вы уже оценили {dish_name} на {user_rating[0]} звезд(ы).")
            else:
                # Получаем новую оценку от пользователя
                new_rating = int(message.text.split()[-1])

                # Обновляем общую оценку и количество оценок для блюда
                total_ratings += 1
                rating = ((rating * (total_ratings - 1)) + new_rating) / total_ratings

                # Сохраняем новую оценку пользователя
                cursor.execute("INSERT INTO dish_comments (user_id, product_id, comment_text) VALUES (?, ?, ?)",
                               (user_id, dish_id, f"Оценка: {new_rating} звезд(ы)"))
                cursor.execute("UPDATE products SET rating=?, total_ratings=? WHERE product_id=?", (rating, total_ratings, dish_id))
                conn.commit()

                bot.send_message(user_id, f"Спасибо за вашу оценку {dish_name}! Средняя оценка теперь {rating:.2f} звезд(ы).")

# Обработчик команды "Оставить комментарий к заказу"
@bot.message_handler(func=lambda message: message.text == "Оставить комментарий к заказу")
def handle_order_comment(message):
    user_id = message.from_user.id

    with conn:
        # Получаем заказы пользователя
        cursor.execute("SELECT * FROM orders WHERE user_id=?", (user_id,))
        user_orders = cursor.fetchall()

        if not user_orders:
            bot.send_message(user_id, "У вас нет заказов для комментирования.")
            return

        # Генерируем клавиатуру с заказами для комментирования
        keyboard = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
        for order in user_orders:
            order_id, _, _, _, _, _, status, _ = order
            keyboard.add(types.KeyboardButton(f"Комментировать заказ #{order_id} ({status})"))

        bot.send_message(user_id, "Выберите заказ для оставления комментария:", reply_markup=keyboard)

# Обработчик для оставления комментария к заказу
@bot.message_handler(func=lambda message: message.text.startswith("Комментировать заказ #"))
def handle_order_comment_text(message):
    user_id = message.from_user.id
    order_id = int(message.text.split()[2])

    with conn:
        # Получаем информацию о заказе
        cursor.execute("SELECT * FROM orders WHERE order_id=?", (order_id,))
        order_info = cursor.fetchone()

        if order_info:
            _, _, _, _, _, _, status, _, _ = order_info

            # Пользователь может оставить комментарий только к выполненным заказам
            if status == "выполнен":
                # Получаем текущий комментарий пользователя к заказу
                cursor.execute("SELECT comment_text FROM order_comments WHERE user_id=? AND order_id=?", (user_id, order_id))
                user_comment = cursor.fetchone()

                if user_comment:
                    bot.send_message(user_id, f"Вы уже оставили комментарий к этому заказу:\n{user_comment[0]}")
                else:
                    # Сохраняем новый комментарий пользователя
                    comment_text = message.text.replace(f"Комментировать заказ #{order_id} (выполнен) ", "")
                    cursor.execute("INSERT INTO order_comments (user_id, order_id, comment_text) VALUES (?, ?, ?)",
                                   (user_id, order_id, comment_text))
                    conn.commit()

                    bot.send_message(user_id, f"Спасибо за ваш комментарий к заказу #{order_id}!\n{comment_text}")
            else:
                bot.send_message(user_id, "Вы можете оставить комментарий только к выполненным заказам.")
        else:
            bot.send_message(user_id, f"Заказ #{order_id} не найден.")

# Обработчик команды "Показать комментарии к блюдам"
@bot.message_handler(func=lambda message: message.text == "Показать комментарии к блюдам")
def handle_show_dish_comments(message):
    user_id = message.from_user.id

    with conn:
        # Получаем блюда из базы данных
        cursor.execute("SELECT * FROM products")
        dishes = cursor.fetchall()

        # Генерируем клавиатуру с блюдами для просмотра комментариев
        keyboard = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
        for dish in dishes:
            dish_id, dish_name, _, _, _, _ = dish
            keyboard.add(types.KeyboardButton(f"Комментарии к {dish_name}"))

        bot.send_message(user_id, "Выберите блюдо для просмотра комментариев:", reply_markup=keyboard)

# Обработчик для показа комментариев к блюду
@bot.message_handler(func=lambda message: message.text.startswith("Комментарии к "))
def handle_show_dish_comments_text(message):
    user_id = message.from_user.id
    dish_name = message.text.replace("Комментарии к ", "")

    with conn:
        # Получаем информацию о блюде
        cursor.execute("SELECT * FROM products WHERE name=?", (dish_name,))
        dish_info = cursor.fetchone()

        if dish_info:
            dish_id, _, _, _, _, _ = dish_info

            # Получаем комментарии к блюду
            cursor.execute("SELECT comment_text FROM dish_comments WHERE product_id=?", (dish_id,))
            dish_comments = cursor.fetchall()

            if dish_comments:
                # Отправляем комментарии пользователю
                comments_text = "\n".join([f"{i + 1}. {comment[0]}" for i, comment in enumerate(dish_comments)])
                bot.send_message(user_id, f"Комментарии к {dish_name}:\n{comments_text}")
            else:
                bot.send_message(user_id, f"У блюда {dish_name} нет комментариев.")
        else:
            bot.send_message(user_id, f"Блюдо {dish_name} не найдено.")"""

# Запуск бота
print("Ready")
bot.infinity_polling()
