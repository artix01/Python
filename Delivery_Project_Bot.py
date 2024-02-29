import telebot
from telebot import types
import sqlite3
import json
import database_f as dbf
from datetime import datetime, timedelta
import time
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
# Путь к файлу с настройками и ключами
config_file_path = 'config.json'

# Путь к файлу с историей изменений
history_file_path = 'history.json'

# Инициализация бота
with open(config_file_path, 'r') as config_file:
    config = json.load(config_file)
bot = telebot.TeleBot(config["tg_token"])
admin_group_chat_id = config["ADMIN_GROUP_CHAT_ID"]

# Подключение к базе данных SQLite
conn = sqlite3.connect('bot_database.db', check_same_thread=False)
cursor = conn.cursor()

total = 0

# Основное меню
main_menu = types.ReplyKeyboardMarkup(resize_keyboard=True)
main_menu.add(types.KeyboardButton("Меню"))
main_menu.add(types.KeyboardButton("Корзина"))
main_menu.add(types.KeyboardButton("Мои заказы"))
main_menu.add(types.KeyboardButton("Оценить блюдо"))

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def handle_start(message):
    if message.chat.type == 'private':
        # Только если сообщение было отправлено приватно
        register_user(message)
    else:
        # Если сообщение было отправлено в группу или канал, игнорируем его
        pass

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
            cursor.execute("INSERT INTO users (user_id, username) VALUES (?, ?)",
                           (user_id, username))
            cursor.execute("INSERT INTO customers (telegram_id) VALUES (?)",
                           (user_id,))
            conn.commit()

            # Отправляем приветственное сообщение и меню
            bot.send_message(user_id, "Привет! Добро пожаловать!")
            bot.send_message(user_id, "Как я могу помочь?", reply_markup=main_menu)
        else:
            # Если пользователь уже зарегистрирован, отправляем приветственное сообщение и меню
            bot.send_message(user_id, "Привет! Как я могу помочь?", reply_markup=main_menu)


def payment_method_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("Карта"))
    keyboard.add(types.KeyboardButton("Наличные"))
    return keyboard


# Глобальная переменная для хранения категорий блюд
categories = []
current_category = None
g_dishes = ()

# Обработчик команды "Меню"
@bot.message_handler(func=lambda message: message.text == "Меню")
def handle_menu(message):
    global categories

    with conn:
        categories = dbf.s_categories()
        if categories:
            # Формируем клавиатуру с кнопками для переключения между категориями
            category_buttons = InlineKeyboardMarkup(row_width=2)
            for category in categories:
                category_name = category[0]
                category_buttons.add(InlineKeyboardButton(category_name, callback_data=f"category:{category_name}"))

            # Отправляем сообщение с кнопками категорий
            bot.send_message(message.from_user.id, "Выберите категорию:", reply_markup=category_buttons)
        else:
            bot.send_message(message.from_user.id, "Извините, меню временно недоступно.")

# Обработчик нажатия на кнопку переключения между блюдами
@bot.callback_query_handler(func=lambda call: call.data.startswith("next_dish:") or call.data.startswith("prev_dish:"))
def handle_dish_switch_callback(call):
    global current_category, g_dishes
    action, dish_index, total_dishes = call.data.split(":")

    dish_index = int(dish_index)
    total_dishes = int(total_dishes)

    with conn:
        dishes = dbf.s_products_from_category(current_category)
        g_dishes = dishes

        if total_dishes == 1:
            # Если в категории всего одно блюдо, игнорируем запрос
            bot.answer_callback_query(callback_query_id=call.id, text="В данной категории только одно блюдо")
            return

        # Отправляем сообщение с карточкой следующего блюда
        if action == "next_dish":
            next_dish_index = (dish_index + 1) % total_dishes
        else:
            next_dish_index = (dish_index - 1) % total_dishes

        send_dish_card(call.from_user.id, dishes[next_dish_index], next_dish_index, total_dishes, current_category, call.message.message_id)

# Обработчик нажатия на кнопку переключения категории (следующая или предыдущая)
@bot.callback_query_handler(func=lambda call: call.data.startswith("next_category:") or call.data.startswith("prev_category:"))
def handle_category_switch_callback(call):
    global current_category, g_dishes
    action, current_category_name = call.data.split(":")
    current_category_index = categories.index((current_category_name,))
    categories_count = len(categories)

    if action == "next_category":
        next_category_index = (current_category_index + 1) % categories_count
    else:
        next_category_index = (current_category_index - 1) % categories_count

    next_category_name = categories[next_category_index][0]  # Получаем только имя категории
    current_category = next_category_name  # Обновляем текущую категорию

    with conn:
        dishes = dbf.s_products_from_category(next_category_name)
        g_dishes = dishes
        if dishes:
            send_dish_card(call.from_user.id, dishes[0], 0, len(dishes), next_category_name, call.message.message_id)
        else:
            bot.send_message(call.from_user.id, "В данной категории нет блюд.")

# Обработчик нажатия на кнопку категории
@bot.callback_query_handler(func=lambda call: call.data.startswith("category:"))
def handle_category_callback(call):
    global current_category, g_dishes
    category_name = call.data.split(":")[1]

    with conn:
        dishes = dbf.s_products_from_category(category_name)
        if dishes:
            send_dish_card(call.from_user.id, dishes[0], 0, len(dishes), category_name, call.message.message_id)
            current_category = category_name
            g_dishes= dishes
            print("current_category", current_category, "dishes[0]", dishes[0])
        else:
            bot.send_message(call.from_user.id, "В данной категории нет блюд.")

# Функция для отправки сообщения с карточкой блюда и кнопками навигации
def send_dish_card(user_id, dish, current_index, total_dishes, current_category, message_id=None, quantity=1):
    dish_id, dish_name, dish_description, dish_price, dish_rating, total_ratings, category, _ = dish
    print("send dish card", current_category, category, "dish", dish)

    prev_category = (categories.index((current_category,)) - 1) % len(categories)
    next_category = (categories.index((current_category,)) + 1) % len(categories)
    print(prev_category)
    # Создаем клавиатуру с кнопками переключения блюд и категорий
    navigation_buttons = InlineKeyboardMarkup(row_width=3)
    prev_button = InlineKeyboardButton("◀️", callback_data=f"prev_dish:{current_index}:{total_dishes}")
    next_button = InlineKeyboardButton("▶️", callback_data=f"next_dish:{current_index}:{total_dishes}")
    prev_category_button = InlineKeyboardButton(f"⬅️ {categories[prev_category][0]}",
                                                callback_data=f"prev_category:{current_category}")
    next_category_button = InlineKeyboardButton(f"{categories[next_category][0]} ➡️",
                                                callback_data=f"next_category:{current_category}")

    plus_button = InlineKeyboardButton("+", callback_data=f"increase_quantity:{quantity}:{current_index}")
    quantity_button = InlineKeyboardButton(str(quantity), callback_data="ignore")
    minus_button = InlineKeyboardButton("-", callback_data=f"decrease_quantity:{quantity}:{current_index}")

    add_to_basket_button = InlineKeyboardButton("🛒Добавить в корзину", callback_data=f"add_to_basket:{quantity}:{current_index}")

    navigation_buttons.row(prev_button, minus_button, quantity_button, plus_button, next_button)
    navigation_buttons.row(prev_category_button, next_category_button)
    navigation_buttons.row(add_to_basket_button)
    print(dish_name)
    # Формируем сообщение с карточкой блюда и кнопками навигации
    message_text = f"{dish_name}\n{dish_description}\nЦена: {dish_price} руб.\n\n"
    message_text += f"Блюдо {current_index + 1} из {total_dishes}"
    image_path = f"images/{dish_id}.jpg"

    try:
        if message_id:
            bot.edit_message_media(chat_id=user_id, message_id=message_id,
                                   media=InputMediaPhoto(open(image_path, 'rb'), caption=message_text),
                                   reply_markup=navigation_buttons)
    except:
        bot.send_photo(user_id, open(image_path, 'rb'), caption=message_text, reply_markup=navigation_buttons)

# Обработчик нажатия кнопки "+"
@bot.callback_query_handler(func=lambda call: call.data.startswith("increase_quantity:"))
def handle_increase_quantity(call):
    quantity = int(call.data.split(":")[1]) + 1  # Увеличиваем количество на 1
    current_index = int(call.data.split(":")[2])
    send_dish_card(call.from_user.id, g_dishes[current_index], current_index, len(g_dishes), g_dishes[current_index][6], call.message.message_id, quantity=quantity)

# Обработчик нажатия кнопки "-"
@bot.callback_query_handler(func=lambda call: call.data.startswith("decrease_quantity:"))
def handle_decrease_quantity(call):
    quantity = int(call.data.split(":")[1]) - 1  # Уменьшаем количество на 1
    current_index = int(call.data.split(":")[2])

    if quantity < 1:
        # Если количество стало меньше 1, игнорируем запрос
        bot.answer_callback_query(callback_query_id=call.id, text="Количество не может быть меньше 1")
        return
    # Переотправляем сообщение с карточкой блюда с обновленным количеством
    send_dish_card(call.from_user.id, g_dishes[current_index], current_index, len(g_dishes), g_dishes[current_index][6], call.message.message_id, quantity=quantity)

# Обработчик нажатия кнопки "Добавить в корзину"
@bot.callback_query_handler(func=lambda call: call.data.startswith("add_to_basket:"))
def handle_add_to_cart(call):
    print(dbf.s_user_id(call.from_user.id)[0])
    user_id = dbf.s_user_id(call.from_user.id)[0]
    quantity = int(call.data.split(":")[1])
    current_index = int(call.data.split(":")[2])
    product_id = g_dishes[current_index][0]  # Получаем id продукта из данных кнопки

    # Получаем информацию о выбранном блюде из базы данных
    with conn:
        product = dbf.s_product_info(product_id)
        if product:
            # Получаем корзину пользователя из базы данных
            basket_data = dbf.s_basket(user_id)

            if basket_data and basket_data != None:
                # Если корзина не пуста, загружаем её из JSON
                basket = json.loads(basket_data[0])
            else:
                # Если корзина пуста, создаем новую
                dbf.insert("basket", "user_id", (user_id,))
                basket = []

            # Проверяем, есть ли уже такой продукт в корзине
            product_found = False
            for item in basket:
                if item['product_id'] == product_id:
                    # Если товар найден в корзине, обновляем его количество
                    item['quantity'] += quantity
                    product_found = True
                    break

            # Если товар не найден в корзине, добавляем его
            if not product_found:
                basket.append({
                    "product_id": product_id,
                    "quantity": quantity
                })

            # Обновляем корзину пользователя в базе данных
            dbf.update("basket", ("basket_data", json.dumps(basket)), ("user_id", user_id))

            # Отправляем пользователю сообщение о добавлении в корзину
            bot.answer_callback_query(callback_query_id=call.id, text=f"{product[1]} добавлен в корзину")

        else:
            bot.answer_callback_query(callback_query_id=call.id, text="Произошла ошибка при добавлении в корзину")


# Обработчик команды "Корзина"
@bot.message_handler(func=lambda message: message.text == "Корзина")
def handle_cart_menu(message):
    send_basket_dish_card(message.from_user.id)

def send_basket_dish_card(chat_user_id, message_id=None, current_index=0):
    user_id = dbf.s_user_id(chat_user_id)[0]
    # Получаем текущую корзину пользователя
    with conn:
        cursor.execute("SELECT basket_data FROM basket WHERE user_id=?", (user_id,))
        user_data = cursor.fetchone()

        if user_data:
            basket = json.loads(user_data[0]) if user_data[0] else []  # Разбираем JSON, если корзина не пуста
        else:
            basket = []

    if not basket:
        bot.send_message(chat_user_id, "Ваша корзина пуста.")
        return

    # Переменная для хранения инлайн клавиатуры
    keyboard = InlineKeyboardMarkup(row_width=3)

    # Переменная для хранения данных о корзине
    total_items = len(basket)

    # Получаем информацию о текущем товаре в корзине
    current_item = basket[current_index]
    product_id = current_item['product_id']
    quantity = current_item['quantity']

    # Получаем информацию о товаре из базы данных
    product_info = dbf.s_product_info(product_id, "name, price")

    if product_info:
        dish_name = product_info[0]
        dish_price = product_info[1]
        image_path = f"images/{product_id}.jpg"
        cart_message = f"{dish_name} цена: {dish_price} руб."

        # Создаем кнопки для управления количеством товара и кнопку удаления товара
        increase_button = InlineKeyboardButton("+", callback_data=f"cart_item:increase:{current_index}:{quantity}")
        decrease_button = InlineKeyboardButton("-", callback_data=f"cart_item:decrease:{current_index}:{quantity}")
        quantity_button = InlineKeyboardButton(f"Количество: {str(quantity)}", callback_data="ignore")
        index_button = InlineKeyboardButton(f"{current_index + 1}/{total_items}", callback_data="ignore")
        delete_button = InlineKeyboardButton(f"Удалить {dish_name}", callback_data=f"cart_item:delete:{product_id}")
        checkout_button = InlineKeyboardButton(f"Офоромить заказ", callback_data=f"checkout")

        # Создаем кнопки для переключения между товарами в корзине
        prev_button = InlineKeyboardButton("◀️", callback_data=f"prev_cart_item:{current_index}:{total_items}")
        next_button = InlineKeyboardButton("▶️", callback_data=f"next_cart_item:{current_index}:{total_items}")
        keyboard.row( decrease_button, quantity_button, increase_button, )
        keyboard.add(prev_button, index_button, next_button)
        keyboard.add(delete_button)
        keyboard.add(checkout_button)

        if message_id:
            bot.edit_message_media(chat_id=chat_user_id, message_id=message_id,
                                   media=InputMediaPhoto(open(image_path, 'rb'), caption=cart_message),
                                   reply_markup=keyboard)
        else:
            bot.send_photo(chat_user_id, open(image_path, 'rb'), caption=cart_message, reply_markup=keyboard)

# Обработчик нажатия кнопок изменения quantity(basket) и удаления товара из корзины
@bot.callback_query_handler(func=lambda call: call.data.startswith("cart_item:"))
def handle_change_quantity(call):
    user_id = dbf.s_user_id(call.from_user.id)[0]
    current_index = int(call.data.split(":")[2])

    # Определяем операцию: увеличение, уменьшение количества товара или удаление товара
    operation = call.data.split(":")[1]
    if operation == "increase":
        new_quantity = int(call.data.split(":")[3]) + 1  # Увеличиваем количество на 1
    elif operation == "decrease":
        if int(call.data.split(":")[3]) <= 1:
            # Если количество стало меньше 1, игнорируем запрос
            bot.answer_callback_query(callback_query_id=call.id, text="Количество не может быть меньше 1")
            return
        new_quantity = int(call.data.split(":")[3]) - 1  # Уменьшаем количество на 1
    elif operation == "delete":
        # Получаем идентификатор удаляемого товара
        product_id = int(call.data.split(":")[2])

        # Получаем текущую корзину пользователя из базы данных
        with conn:
            user_data = dbf.s_basket(user_id)
            if user_data:
                basket = json.loads(user_data[0]) if user_data[0] else []  # Разбираем JSON, если корзина не пуста
            else:
                basket = []

            # Удаляем товар из корзины по его идентификатору
            new_basket = [item for item in basket if item['product_id'] != product_id]

            # Обновляем корзину пользователя в базе данных
            dbf.update("basket", ("basket_data", json.dumps(new_basket)), ("user_id", user_id))

        # Отправляем обновленную информацию о корзине пользователю
        send_basket_dish_card(call.from_user.id, call.message.message_id)
        return

    # Получаем текущую корзину пользователя из базы данных
    with conn:
        user_data = dbf.s_basket(user_id)

        if user_data:
            basket = json.loads(user_data[0]) if user_data[0] else []  # Разбираем JSON, если корзина не пуста
        else:
            basket = []

        # Обновляем количество товара в корзине
        basket[current_index]['quantity'] = new_quantity

        # Обновляем корзину пользователя в базе данных
        dbf.update("basket", ("basket_data", json.dumps(basket)), ("user_id", user_id))

    # Отправляем обновленную информацию о корзине пользователю
    send_basket_dish_card(call.from_user.id, call.message.message_id, current_index=current_index)



# Обработчик нажатия кнопок переключения между товарами в корзине
@bot.callback_query_handler(func=lambda call: call.data.startswith("prev_cart_item") or call.data.startswith("next_cart_item"))
def handle_change_cart_item(call):

    # Определяем текущий индекс товара в корзине
    current_index = int(call.data.split(":")[1])
    total_items = int(call.data.split(":")[2])

    if total_items == 1:
        # Если в категории всего одно блюдо, игнорируем запрос
        bot.answer_callback_query(callback_query_id=call.id, text="В корзине только одно блюдо")
        return

    # Переключаемся к следующему товару
    if call.data.startswith("next_cart_item"):
        next_index = (current_index + 1) % total_items
    # Переключаемся к предыдущему товару
    else:
        next_index = (current_index - 1) % total_items

    send_basket_dish_card(call.from_user.id, call.message.message_id, next_index)

# Обработчик команды "Оформить заказ"
@bot.callback_query_handler(func=lambda call: call.data == "checkout")
def handle_checkout(call):
    user_id = dbf.s_user_id(call.from_user.id)[0]
    with conn:
        # Проверяем, есть ли позиции в корзине
        basket = dbf.s_basket(user_id)
        if basket and basket[0]:
            user_data = dbf.select("customers", "name, email, address", "WHERE user_id = ?", (user_id,))[0]
            print(user_data)
            if user_data[2] != None:
                # Если данные пользователя уже заполнены, предлагаем выбор адреса
                address = user_data[2]
                keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
                keyboard.add(types.KeyboardButton(address))
                bot.send_message(call.from_user.id, "Выберите или укажите адрес:", reply_markup=keyboard)
                bot.register_next_step_handler(call.message, lambda msg: address_step(msg, 'address_choice'))
            else:
                if user_data[0] == None:
                    # Если данные не заполнены, запрашиваем у пользователя имя и email
                    bot.send_message(call.from_user.id, "Для оформления укажите ваше имя.")
                    bot.register_next_step_handler(call.message, lambda msg: process_step(msg, 'name'))
        else:
            # Если корзина пуста, уведомляем пользователя
            bot.send_message(call.from_user.id, "Ваша корзина пуста")

def process_step(message, step):
    user_id = dbf.s_user_id(message.from_user.id)[0]

    if step == 'name':
        # Обрабатываем шаг с именем
        name = message.text
        dbf.update("customers", ("name", name), ("user_id", user_id))

        # Переходим к следующему шагу
        bot.send_message(message.from_user.id, "Отлично! Теперь укажите ваш email:")
        bot.register_next_step_handler(message, lambda msg: process_step(msg, 'email'))

    elif step == 'email':
        # Обрабатываем шаг с email
        email = message.text
        dbf.update("customers", ("email", email), ("user_id", user_id))

        # После получения email, запрашиваем адрес
        bot.send_message(message.from_user.id, "Теперь укажите ваш адрес:")
        bot.register_next_step_handler(message, lambda msg: address_step(msg, 'address_choice'))

def calculate_total_price(basket):
    total_price = 0

    with conn:
        for item in basket:
            product_id = item['product_id']

            # Получаем цену товара из таблицы products
            cursor.execute("SELECT price FROM products WHERE product_id=?", (product_id,))
            product_info = cursor.fetchone()

            if product_info:
                price = product_info[0]
                quantity = item['quantity']

                # Суммируем цены товаров
                total_price += price * quantity

    return total_price

# Функция для вычисления времени ожидания
def calculate_estimated_delivery_time(basket):
    max_cooking_time = 0

    # Находим максимальное время приготовления блюда в корзине
    for item in basket:
        product_id = item['product_id']

        cursor.execute("SELECT cooking_time FROM products WHERE product_id=?", (product_id,))
        product_info = cursor.fetchone()

        if product_info:
            cooking_time = product_info[0]
            max_cooking_time = max(max_cooking_time, cooking_time)

    # Вычисляем время ожидания как максимальное время приготовления + 30 минут
    delivery_time = max_cooking_time + 30
    return delivery_time

# Обработка шага "address_choice"
def address_step(message, step):
    from_user_id = message.from_user.id
    user_id = dbf.s_user_id(from_user_id)[0]
    basket = []

    if step == 'address_choice':
        address = message.text

        # Получаем данные о корзине пользователя
        with conn:
            user_data = dbf.s_basket(user_id)

            if user_data:
                basket = json.loads(user_data[0]) if user_data[0] else []

        # Вычисляем общую стоимость заказа
        total_price = calculate_total_price(basket)

        # Вычисляем время ожидания
        estimated_delivery_time = calculate_estimated_delivery_time(basket)

        # Вставляем запись в таблицу orders
        with conn:
            cursor.execute("INSERT INTO orders (user_id, address, total_price, estimated_delivery_time, basket) "
                           "VALUES (?, ?, ?, ?, ?)",
                           (user_id, address, total_price, estimated_delivery_time, json.dumps(basket)))
            conn.commit()

            # Очищаем корзину пользователя
            dbf.update("basket", ("basket_data", "[]"), ("user_id", user_id))

        # Отправляем пользователю примерное время ожидания
        bot.send_message(message.from_user.id, f"Спасибо! Ваш заказ принят. Ожидайте доставку по адресу: {address}. "
                                                f"Примерное время ожидания: {estimated_delivery_time} минут.", reply_markup=main_menu)

        # Отправляем уведомление о заказе в группу администраторов
        notify_admins_about_order(cursor.lastrowid, address, status=0, chat_id=admin_group_chat_id)

# Функция для отображения истории заказов
def show_order_history(from_user_id, message_id=None):
    with conn:
        # Получаем заказы пользователя из таблицы orders
        my_orders =dbf.select("orders", "*", "WHERE status = ? OR status = ? OR status = ?", ("Ожидает подтверждения", "готовится", "готов"))
        print(my_orders)

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("📦ИСТОРИЯ ЗАКАЗОВ📦", callback_data="orders_history:"))
    if my_orders:
        # Если есть заказы, формируем клавиатуру с их списком

        for order in my_orders:
            order_id, user_id, address, total_price, order_date, estimated_delivery_time, status, basket, rated = order
            callback_data = f"order_info:{order_id}"
            button_text = f"Заказ {order_date}, Сумма: {total_price} руб., Время доставки: {estimated_delivery_time} мин."
            keyboard.add(types.InlineKeyboardButton(button_text, callback_data=callback_data))
        # Отправляем сообщение с клавиатурой
        if message_id:
            bot.edit_message_text(chat_id=from_user_id, message_id=message_id, text="Активные заказы:", reply_markup=keyboard)
        else:
            bot.send_message(from_user_id, "Активные заказы:", reply_markup=keyboard)
    else:
        if message_id:
            bot.edit_message_text(chat_id=from_user_id, message_id=message_id, text="У вас нет активных заказов.", reply_markup=keyboard)
        else:
            bot.send_message(from_user_id, "У вас нет активных заказов.", reply_markup=keyboard)

    orders_history = types.ReplyKeyboardMarkup(resize_keyboard=True)
    orders_history.add(types.KeyboardButton("История заказов"))


# Обработчик нажатия на кнопку с информацией о заказе
@bot.callback_query_handler(func=lambda call: call.data.startswith("order_info:") or call.data == "back_to_orders")
def handle_order_info_callback(call):
    from_user_id = call.from_user.id
    if call.data == "back_to_orders":
        show_order_history(from_user_id, call.message.message_id)
        return
    user_id = dbf.s_user_id(call.from_user.id)[0]
    order_id = int(call.data.split(":")[1])
    back_button_text = "Мои заказы"
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton(f"Назад к {back_button_text}", callback_data="back_to_orders"))

    # Получаем информацию о заказе из базы данных
    with conn:
        order_info = dbf.select("orders", "total_price, estimated_delivery_time, order_date, basket, status, rated", "WHERE order_id = ? AND user_id = ?", (order_id, user_id))

    if order_info:
        total_price, estimated_delivery_time, order_date, basket_json, status, rated = order_info[0]
        basket = json.loads(basket_json) if basket_json else []
        if status == "доставлен" and int(rated) == 0:
            keyboard.add(InlineKeyboardButton(f"Оставить отзыв", callback_data=f"order_comment:{order_id}"))
        elif status == "доставлен" and int(rated) == 1:
            keyboard.add(InlineKeyboardButton(f"Посмотреть отзыв", callback_data=f"show_comment:{order_id}"))
        # Формируем сообщение с информацией о заказе
        order_message = f"Информация о заказе от {order_date}:\n\n"
        for item in basket:
            # Загружаем информацию о блюде из базы данных по его идентификатору
            product_info = dbf.s_product_info(item['product_id'], "name")

            if product_info:
                dish_name = product_info[0]
                order_message += f"{dish_name} (количество: {item['quantity']})\n"

        order_message += f"\nИтого: {total_price} руб.\nСтатус: {status}\n"
        order_message += f"Примерное время ожидания: {estimated_delivery_time} минут."

        # Отправляем сообщение с информацией о заказе
        bot.edit_message_text(chat_id=from_user_id, message_id=call.message.message_id, text=order_message, reply_markup=keyboard)
    else:
        # Если информация о заказе не найдена, отправляем уведомление
        bot.answer_callback_query(callback_query_id=call.id, show_alert=True, text="Информация о заказе не найдена.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("show_comment:"))
def handle_show_comment(call):
    from_user_id = call.from_user.id
    order_id = call.data.split(":")[1]
    message_id = call.message.message_id
    comment_text = dbf.select("order_comments","comment_text", "WHERE order_id = ?", (order_id,))[0][0]
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton(f"Назад к заказам", callback_data="back_to_orders"))
    bot.edit_message_text(chat_id=from_user_id, message_id=message_id, text=f"Ваш отзыв:\n{comment_text}", reply_markup=keyboard)

# Обработчик нажатия на оставить отзыв
@bot.callback_query_handler(func=lambda call: call.data.startswith("order_comment:") or call.data.startswith("edit_comment:"))
def handle_order_comment(call):
    from_user_id = call.from_user.id
    message_id = call.message.message_id
    user_id = dbf.s_user_id(from_user_id)
    order_id = int(call.data.split(":")[1])
    if call.data.startswith("order_comment:"):
        order_ids = []
        orders = dbf.select("order_comments", "DISTINCT order_id", "", ())
        for order in orders:
            order_ids.append(order[0])
        if order_id in order_ids:
            bot.answer_callback_query(callback_query_id=call.id, text="Вы уже оставляли отзыв к этому заказу")
            return
    if user_id:
        # Предложить пользователю ввести отзыв
        if message_id:
            bot.edit_message_text(chat_id=from_user_id, message_id=message_id, text="Пожалуйста, введите ваш отзыв:")
        else:
            bot.send_message(from_user_id, "Пожалуйста, введите ваш отзыв:")
        # Установить следующий шаг обработки ввода отзыва
        bot.register_next_step_handler(call.message, process_order_comment, order_id)
        dbf.insert("order_comments", "order_id", (order_id,))
    else:
        bot.send_message(from_user_id, "Ваш аккаунт не найден. Попробуйте позже.")


def process_order_comment(message, order_id):
    # Получить текст отзыва
    comment_text = message.text
    from_user_id = message.from_user.id
    message_id = int(message.message_id)+1
    print(message_id)

    if from_user_id:
        # Отправить пользователю его отзыв с кнопками "Сохранить отзыв" и "Изменить отзыв"
        keyboard = types.InlineKeyboardMarkup()
        save_button = types.InlineKeyboardButton("Сохранить отзыв",
                                                 callback_data=f"save_comment:{order_id}:{message_id}:order")
        edit_button = types.InlineKeyboardButton("Изменить отзыв", callback_data=f"edit_comment:{order_id}:{message_id}:order")
        keyboard.add(save_button, edit_button)
        dbf.update("order_comments", ("comment_text", comment_text), ("order_id", order_id))
        bot.send_message(from_user_id, f"Ваш отзыв:\n{comment_text}", reply_markup=keyboard)
    else:
        bot.send_message(from_user_id, "Ваш аккаунт не найден. Попробуйте позже.")


# Обработчик нажатия на кнопку "Сохранить отзыв"
@bot.callback_query_handler(func=lambda call: call.data.startswith("save_comment:"))
def handle_save_comment(call):
    message_id = call.data.split(":")[2]
    user_id = dbf.s_user_id(call.from_user.id)[0]
    order_id = call.data.split(":")[1]
    where_from = call.data.split(":")[3]
    if where_from == "order":
        comment_text = dbf.select("order_comments", "comment_text", "WHERE order_id = ?", (order_id,))
    else:
        comment_text = dbf.select("dish_comments", "comment_text", "WHERE product_id = ?", (order_id,))
    print(comment_text)
    # Отправить уведомление в группу администраторов о новом отзыве
    keyboard_admin = types.InlineKeyboardMarkup()
    access_comment_button = types.InlineKeyboardButton("Одобрить комментарий",
                                                       callback_data=f"access_comment:{user_id}:{order_id}:{message_id}:{where_from}")
    delete_comment_button = types.InlineKeyboardButton("Удалить комментарий",
                                                       callback_data=f"delete_comment:{user_id}:{order_id}:{message_id}:{where_from}")
    keyboard_admin.add(access_comment_button, delete_comment_button)
    back_to_dishes_keyboard = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("К списку блюд", callback_data=f"back_to_dishes:"))
    bot.edit_message_text(chat_id=call.from_user.id, text="Ваш отзыв сохранен!", message_id=call.message.message_id, reply_markup=back_to_dishes_keyboard)
    print(comment_text)
    if call.data.split(":")[3] == "order":
        text = f"Новый отзыв к заказу №{order_id}:\n{comment_text[0][0]}"
    else:
        dish_name = dbf.select("products", "name", "WHERE product_id=?", (order_id,))
        text = f"Новый отзыв к блюду {dish_name}:\n{comment_text[0][0]}"
    bot.send_message(admin_group_chat_id, text, reply_markup=keyboard_admin)


# Обработчик нажатия на историю заказов
@bot.callback_query_handler(func=lambda call: call.data.startswith("orders_history:"))
def handle_orders_history_callback(call):
    from_user_id = call.from_user.id
    user_id = dbf.s_user_id(from_user_id)
    if user_id:
        user_id = user_id[0]
        # Получаем историю заказов пользователя из базы данных
        with conn:
            orders =dbf.select("orders", "*", "WHERE status = ? OR status = ?", ("доставлен", "отменен"))

        if orders:
            order_buttons = []
            for order in orders:
                order_id, user_id, address, total_price, order_date, estimated_delivery_time, status, basket, rated = order
                order_button_text = f"Заказ на {total_price} рублей ({order_date}) - {status}"
                order_buttons.append(InlineKeyboardButton(order_button_text, callback_data=f"order_info:{order_id}"))

            # Добавляем кнопку "Назад"
            keyboard = types.InlineKeyboardMarkup()
            for button in order_buttons:
                keyboard.add(button)
            keyboard.add(InlineKeyboardButton("Назад", callback_data="back_to_orders"))

            bot.edit_message_text(chat_id=from_user_id, message_id=call.message.message_id,
                                  text="Выберите заказ для просмотра:", reply_markup=keyboard)
        else:
            bot.answer_callback_query(callback_query_id=call.id, show_alert=True, text="У вас нет заказов в истории.")
    else:
        bot.answer_callback_query(callback_query_id=call.id, show_alert=True,
                                  text="Информация о пользователе не найдена.")


# Обработчик команды /admin
@bot.message_handler(commands=['admin'])
def handle_admin(message, message_id=None):
    from_user_id = message.from_user.id
    # Проверяем, является ли пользователь администратором
    if is_admin(from_user_id):
        admin_markup = types.InlineKeyboardMarkup()

        # Кнопки для действий с продуктами
        product_actions = types.InlineKeyboardButton(text="Действия с продуктами", callback_data="product_actions")
        admin_markup.add(product_actions)

        # Кнопка для просмотра заказов
        orders_group = types.InlineKeyboardButton(text="Заказы", callback_data="orders_group")
        admin_markup.add(orders_group)

        if message_id:
            bot.edit_message_text(chat_id=from_user_id, message_id=message_id,
                                  text="Выберите категорию действий:", reply_markup=admin_markup)
        else:
            bot.send_message(from_user_id, "Выберите категорию действий:", reply_markup=admin_markup)
    else:
        bot.send_message(from_user_id, "У вас нет доступа к админ-панели.")


# Обработчик для inline-кнопки "Заказы"
@bot.callback_query_handler(func=lambda call: call.data == 'orders_group')
def handle_orders_group(call):
    from_user_id = call.from_user.id
    if is_admin(from_user_id):
        orders_markup = types.InlineKeyboardMarkup()

        # Кнопка "Просмотреть заказы"
        view_orders = types.InlineKeyboardButton(text="Просмотреть заказы", callback_data="view_orders")

        # Кнопка "Действия с заказами"
        order_actions = types.InlineKeyboardButton(text="Действия с заказами", callback_data="orders_actions")
        orders_markup.add(view_orders, order_actions)
        orders_markup.add(InlineKeyboardButton("Назад", callback_data=f"back_to_admin_panel:{call.message.message_id}"))

        bot.edit_message_text(chat_id=from_user_id, message_id=call.message.message_id, text="Выберите действие с заказами:",
                              reply_markup=orders_markup)
    else:
        bot.edit_message_text(chat_id=from_user_id, message_id=call.message.message_id,
                              text="У вас нет доступа к админ-панели.")

# Обработчик для inline-кнопки "Действия с продуктами"
@bot.callback_query_handler(func=lambda call: call.data == 'product_actions')
def handle_product_actions(call):
    from_user_id = call.from_user.id
    if is_admin(from_user_id):
        product_markup = types.InlineKeyboardMarkup()
        product_markup.row(types.InlineKeyboardButton(text="Добавить продукт", callback_data="add_product"), types.InlineKeyboardButton(text="Удалить продукт", callback_data="remove_product"),types.InlineKeyboardButton(text="Изменить цену", callback_data="change_price"))
        product_markup.add(types.InlineKeyboardButton(text="Назад", callback_data=f"back_to_admin_panel:{call.message.message_id}"))
        # Можно добавить другие действия по аналогии

        bot.edit_message_text(chat_id=from_user_id, message_id=call.message.message_id, text="Выберите действие с продуктами:", reply_markup=product_markup)
    else:
        bot.edit_message_text(chat_id=from_user_id, message_id=call.message.message_id, text="У вас нет доступа к админ-панели.")



# Обработчик для inline-кнопки "Просмотреть заказы"
@bot.callback_query_handler(func=lambda call: call.data == 'view_orders' or call.data == 'back_to_view')
def handle_view_orders(call):
    from_user_id = call.from_user.id
    chat_id = admin_group_chat_id
    if is_admin(from_user_id):
        # Клавиатура для выбора категории заказов
        categories_markup = types.InlineKeyboardMarkup()
        categories_markup.row(types.InlineKeyboardButton("Активные заказы", callback_data="view_orders:active"),
                              types.InlineKeyboardButton("Успешные заказы", callback_data="view_orders:successful"),
                              types.InlineKeyboardButton("Отмененные заказы", callback_data="view_orders:cancelled"))
        categories_markup.row(types.InlineKeyboardButton("Назад", callback_data=f"back_to_orders_group:{call.message.message_id}"))
        bot.edit_message_text(chat_id=from_user_id, message_id=call.message.message_id, text="Выберите категорию заказов:", reply_markup=categories_markup)
    else:
        bot.send_message(chat_id, "У вас нет доступа к админ-панели.")

@bot.callback_query_handler(func=lambda call: call.data.startswith(("back_to_admin_panel:", "back_to_orders_group:", "back_to_view_orders:", "back_to_orders_actions:")))
def back_to_admin_panel(call):
    message_id = call.data.split(":")[1]
    if call.data.startswith("back_to_admin_panel:"):
        handle_admin(call, message_id)
    elif call.data.startswith("back_to_orders_group:"):
        handle_orders_group(call)
    elif call.data.startswith("back_to_view_orders:"):
        handle_view_orders(call)
    elif call.data.startswith("back_to_orders_actions:"):
        print(call.message.message_id)
        bad_try = call.data.split(":")[1]
        print(bad_try)
        handle_orders_actions(call, bad_try)

@bot.callback_query_handler(func=lambda call: call.data.startswith('view_orders:'))
def handle_view_orders_category(call):
    from_user_id = call.from_user.id
    chat_id = admin_group_chat_id
    if is_admin(from_user_id):
        category = call.data.split(":")[1]
        print(category)
        orders_info = get_orders_info(category)
        if orders_info:
            total_orders = len(orders_info)
            orders_per_page = 5
            total_pages = (total_orders + orders_per_page - 1) // orders_per_page
            current_page = 1

            send_orders_page(from_user_id, call.message.message_id, category, orders_info, current_page, total_pages)
        else:
            bot.send_message(from_user_id, "Заказов пока нет.")
    else:
        bot.send_message(from_user_id, "У вас нет доступа к админ-панели.")


def get_orders_info(category):
    if category == "active":
        return dbf.select("orders", "*", "WHERE status IN (?, ?, ?)", ('Ожидает подтверждения', 'готовится', 'готов'))
    elif category == "successful":
        return dbf.select("orders", "*", "WHERE status = ?", ('доставлен',))
    elif category == "cancelled":
        return dbf.select("orders", "*", "WHERE status = ?", ('отменен',))
    else:
        return None


def send_orders_page(chat_id, message_id, category, orders_info, current_page, total_pages):
    start_index = (current_page - 1) * 5
    end_index = min(start_index + 5, len(orders_info))
    orders_info_page = orders_info[start_index:end_index]
    print(start_index, end_index)
    order_text = f"{category}\n"
    order_text += f"Страница: {current_page}/{total_pages}\n\n"

    for order_info in orders_info_page:
        order_id, _, address, total_price, order_date, _, status, basket, _ = order_info
        order_text += f"Заказ №{order_id} от {order_date}\n"
        order_text += f"Адрес: {address}\n"
        order_text += f"Сумма заказа: {total_price}\n"
        order_text += f"Статус: {status}\n"
        order_text += "Состав заказа:\n"

        basket_items = eval(basket)
        for item in basket_items:
            product_id, quantity = item['product_id'], item['quantity']
            product_info = dbf.s_product_info(product_id)
            if product_info:
                product_name = product_info[1]
                order_text += f"- {product_name} (количество: {quantity})\n"

        order_text += "\n"

    navigation_markup = types.InlineKeyboardMarkup()
    navigation_markup.row(types.InlineKeyboardButton("Предыдущая", callback_data=f"view_orders_back:{category}:{current_page}:{total_pages}"),
                          types.InlineKeyboardButton(f"Страница: {current_page}/{total_pages}", callback_data="ignore"),
                          types.InlineKeyboardButton("Следующая", callback_data=f"view_orders_next:{category}:{current_page}:{total_pages}"))
    navigation_markup.add(types.InlineKeyboardButton("Назад", callback_data=f"back_to_view_orders:"))
    bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=order_text, reply_markup=navigation_markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith(("view_orders_next:", "view_orders_back:")))
def handle_pagination(call):
    from_user_id = call.from_user.id
    chat_id = admin_group_chat_id
    if is_admin(from_user_id):
        category = call.data.split(":")[1]
        current_page = int(call.data.split(":")[2])
        total_pages = int(call.data.split(":")[3])
        if call.data.startswith('view_orders_back:') and current_page > 1:
            current_page -= 1
        elif call.data.startswith('view_orders_next:') and current_page < total_pages:
            current_page += 1
        elif call.data.startswith('view_orders_next:') and current_page == total_pages:
            bot.answer_callback_query(callback_query_id=call.id, text="Вы находитесь на последней странице.")
            return
        elif call.data.startswith('view_orders_back:') and current_page == 1:
            bot.answer_callback_query(callback_query_id=call.id, text="Вы находитесь на первой странице.")
            return
        print(current_page)
        orders_info = get_orders_info(category)
        if orders_info:
            send_orders_page(from_user_id, call.message.message_id, category, orders_info, current_page, total_pages)
        else:
            bot.send_message(from_user_id, "Заказов пока нет.")
    else:
        bot.send_message(from_user_id, "У вас нет доступа к админ-панели.")

# Проверка, является ли пользователь администратором
def is_admin(user_id):
    with conn:
        cursor.execute("SELECT * FROM admin_users WHERE user_id=?", (user_id,))
        admin_data = cursor.fetchone()
        return bool(admin_data)

# Функция для отправки уведомления о сформированном заказе в группу администраторов
def notify_admins_about_order(order_id, address, status, chat_id, message_id=None):
    if status == 0 or status == "Ожидает подтверждения":
        status = 0
        message_text = f"Ожидает подтверждения\nНовый заказ №{order_id}.\nАдрес доставки: {address}."
    elif status == 2 or status == "отменен":
        status = 2
        message_text = f"Отменен\nЗаказ №{order_id}.\nАдрес доставки: {address}."
    elif status == 3 or status == "готов":
        status = 3
        message_text = f"Готов! В процессе доставки.\nЗаказ №{order_id}.\nАдрес доставки: {address}."
    elif status == 4 or status == "доставлен":
        status = 4
        message_text = f"Доставлен.\nЗаказ №{order_id}.\nАдрес доставки: {address}."
    else:
        status = 1
        message_text = f"Заказ готовится\nЗаказ №{order_id}.\nАдрес доставки: {address}."

    order_button = InlineKeyboardButton("Информация о заказе", callback_data=f"confirm_order_info:{order_id}:{status}:{chat_id}")
    actions_button = InlineKeyboardButton("Действия с заказом", callback_data=f"order_actions:{order_id}:{status}:{chat_id}")
    keyboard = InlineKeyboardMarkup().add(order_button, actions_button)
    keyboard.add(InlineKeyboardButton("Назад", callback_data=f"back_to_orders_group:"))
    if not chat_id:
        chat_id = admin_group_chat_id

    if message_id:
        print(message_id)
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=message_text, reply_markup=keyboard)
        except:
            bot.edit_message_text(chat_id=chat_id, message_id=(message_id-1), text=message_text, reply_markup=keyboard)
    else:
        bot.send_message(chat_id, message_text, reply_markup=keyboard)

# Обработчик для inline-кнопки "Действия с заказами"
@bot.callback_query_handler(func=lambda call: call.data == 'orders_actions')
def handle_orders_actions(call, bad_try=None):
    from_user_id = call.from_user.id
    message_id = call.message.message_id
    if is_admin(from_user_id):
        keyboard = types.InlineKeyboardMarkup().add(InlineKeyboardButton("Назад", callback_data="back_to_orders_group:"))
        bot.edit_message_text(chat_id=from_user_id, message_id=message_id, text="Введите номер заказа для выполнения действий с ним:", reply_markup=keyboard)
        bot.register_next_step_handler(call.message, admin_orders_actions, bad_try)
    else:
        bot.send_message(from_user_id, "У вас нет доступа к админ-панели.")

# Обработчик для ввода номера заказа
def admin_orders_actions(message, bad_try=None):
    global total
    from_user_id = message.from_user.id
    order_id = message.text
    message_id = message.message_id
    total += 1
    try:
        order_info = dbf.select("orders", "address, status", "WHERE order_id=?", (order_id,))[0]
        bot.delete_message(from_user_id, message_id)
        print(message_id)
        message_id -= total
    except:
        if message.text:
            bot.delete_message(from_user_id, message_id)
            message_id -= 1
        if bad_try:
            message_id = bad_try
        keyboard = types.InlineKeyboardMarkup().add(
            InlineKeyboardButton("Назад", callback_data=f"back_to_orders_actions:{message_id}"))
        bot.edit_message_text(chat_id=from_user_id, message_id=message_id, text="Заказ с указанным номером не найден.", reply_markup=keyboard)
        return
    address, status = order_info
    # Вызываем функцию для отправки уведомления об изменении статуса заказа
    notify_admins_about_order(order_id, address, status, chat_id=from_user_id, message_id=message_id)

# Обработчик нажатия кнопки "Действия с заказом"
@bot.callback_query_handler(
    func=lambda call: call.data.startswith(('confirm_order:', 'confirm_done:', 'confirm_delivery:', 'confirm_order_info', 'back_to_order:', 'order_actions:', 'cancel_order:')))
def confirm_order(call):
    chat_id = call.data.split(':')[3]
    status = int(call.data.split(':')[2])
    order_id = int(call.data.split(':')[1])
    address = dbf.select("orders", "address", "WHERE order_id=?", (order_id,))
    if not chat_id:
        chat_id = admin_group_chat_id
    if call.data.startswith('confirm_order:'):
        if int(status) == 1:
            # Отправляем уведомление о том, что заказ уже был подтвержден
            bot.answer_callback_query(call.id, text="Заказ уже был подтвержден.", show_alert=True)
        elif int(status) == 0:
            # Обновляем статус заказа на "готовится"
            with conn:
                dbf.update("orders", ("status", "готовится"), ("order_id", order_id))
                bot.answer_callback_query(call.id, text="Заказ успешно подтвержден.", show_alert=True)
                status = 1
                # Отправляем уведомление об успешном подтверждении заказа
                notify_admins_about_order(order_id, address, status, message_id=call.message.message_id, chat_id=chat_id)
        elif int(status) == 2:
            bot.answer_callback_query(call.id, text="Невозможно подтвердить. Заказ был отменен.",
                                      show_alert=True)
        elif int(status) == 3:
            bot.answer_callback_query(call.id, text="Заказ уже приготовлен.",
                                      show_alert=True)
        elif int(status) == 4:
            bot.answer_callback_query(call.id, text="Заказ уже доставлен.",
                                      show_alert=True)
    elif call.data.startswith('cancel_order:'):
        if int(status) == 1:
            bot.answer_callback_query(call.id, text="Невозможно отменить. Заказ уже был подтвержден.", show_alert=True)
        elif int(status) == 0:
            # Обновляем статус заказа на "отменен"
            with conn:
                dbf.update("orders", ("status", "отменен"), ("order_id", order_id))
                bot.answer_callback_query(call.id, text="Заказ успешно отменен.", show_alert=True)
                status = 2
            # Отправляем уведомление об успешном подтверждении заказа
            notify_admins_about_order(order_id, address, status, message_id=call.message.message_id, chat_id=chat_id)
        elif int(status) == 2:
            bot.answer_callback_query(call.id, text="Заказ уже отменен.", show_alert=True)
        elif int(status) == 3:
            bot.answer_callback_query(call.id, text="Заказ уже приготовлен.",
                                      show_alert=True)
        elif int(status) == 4:
            bot.answer_callback_query(call.id, text="Заказ уже доставлен.",
                                      show_alert=True)
    elif call.data.startswith('confirm_done:'):
        if int(status) == 2:
            bot.answer_callback_query(call.id, text="Невозможно подтвердить готовность. Заказ был отменен.", show_alert=True)
        if int(status) == 0:
            bot.answer_callback_query(call.id, text="Невозможно подтвердить готовность. Заказ не был принят в работу.", show_alert=True)
        elif int(status) == 1:
            with conn:
                dbf.update("orders", ("status", "готов"), ("order_id", order_id))
                bot.answer_callback_query(call.id, text="Заказ готов!", show_alert=True)
                status = 3
            # Отправляем уведомление об успешном подтверждении заказа
            notify_admins_about_order(order_id, address, status, message_id=call.message.message_id, chat_id=chat_id)
        elif int(status) == 4:
            bot.answer_callback_query(call.id, text="Заказ уже доставлен.",
                                      show_alert=True)
    elif call.data.startswith('confirm_delivery:'):
        if int(status) == 2:
            bot.answer_callback_query(call.id, text="Невозможно подтвердить доставку. Заказ был отменен.",
                                      show_alert=True)
        elif int(status) == 0:
            bot.answer_callback_query(call.id, text="Невозможно подтвердить доставку. Заказ не был принят в работу.",
                                      show_alert=True)
        elif int(status) == 1:
            bot.answer_callback_query(call.id, text="Невозможно подтвердить доставку. Заказ еще не готов.",
                                      show_alert=True)
        elif int(status) == 3:
            with conn:
                dbf.update("orders", ("status", "доставлен"), ("order_id", order_id))
                bot.answer_callback_query(call.id, text="Заказ доставлен!", show_alert=True)
                status = 4
            # Отправляем уведомление об успешном подтверждении заказа
            notify_admins_about_order(order_id, address, status, message_id=call.message.message_id, chat_id=chat_id)
    elif call.data.startswith('back_to_order:'):
        print(status)
        notify_admins_about_order(order_id, address, status, message_id=call.message.message_id, chat_id=chat_id)
    elif call.data.startswith(('confirm_order_info', 'order_actions:')):
        # Получаем информацию о заказе из базы данных
        order_info = dbf.select("orders", "*", "WHERE order_id = ?", (order_id,))
        print(order_info[0][6])
        if order_info[0][6] == 'готовится':
            status = 1
        elif order_info[0][6] == 'Ожидает подтверждения':
            status = 0
        elif order_info[0][6] == 'отменен':
            status = 2

        actions_button = InlineKeyboardButton("Действия с заказом", callback_data=f"order_actions:{order_id}:{status}:{chat_id}")
        back_to_order = InlineKeyboardButton("Назад", callback_data=f"back_to_order:{order_id}:{status}:{chat_id}")
        confirm_button = InlineKeyboardButton("Подтвердить заказ", callback_data=f"confirm_order:{order_id}:{status}:{chat_id}")
        cancel_button = InlineKeyboardButton("Отменить заказ", callback_data=f"cancel_order:{order_id}:{status}:{chat_id}")
        confirm_done_button = InlineKeyboardButton("Заказ готов", callback_data=f"confirm_done:{order_id}:{status}:{chat_id}")
        confirm_delivery_button = InlineKeyboardButton("Заказ доставлен", callback_data=f"confirm_delivery:{order_id}:{status}:{chat_id}")

        if call.data.startswith('confirm_order_info'):
            keyboard = InlineKeyboardMarkup().add(actions_button, back_to_order)
        else:
            keyboard = InlineKeyboardMarkup().add(confirm_button, cancel_button)
            keyboard.row(confirm_done_button, confirm_delivery_button)
            keyboard.row(back_to_order)

        if order_info:
            # Формируем текстовое сообщение с информацией о заказе
            order_text = f"ID заказа: {order_info[0][0]}\n"
            order_text += f"Статус: {order_info[0][6]}\n"
            order_text += f"Адрес доставки: {order_info[0][2]}\n"
            order_text += f"Общая стоимость: {order_info[0][3]} руб.\n"
            order_text += f"Дата заказа: {order_info[0][4]}\n"
            order_text += f"Оцененное время доставки: {order_info[0][5]} мин.\n\n"

            # Отправляем сообщение с информацией о заказе
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=order_text, reply_markup=keyboard)
        else:
            # В случае ошибки или отсутствия информации о заказе отправляем сообщение об этом
            bot.send_message(chat_id, "Ошибка: информация о заказе не найдена.")

# Обработчик действия с комментарием
@bot.callback_query_handler(func=lambda call: call.data.startswith(("access_comment:", "delete_comment:")))
def handle_access_comment(call):
    print(call.data)
    order_id = call.data.split(":")[2]
    message_id = call.data.split(":")[3]
    user_id = call.data.split(":")[1]
    where_from = call.data.split(":")[4]
    if where_from == "dish":
        dish_name = dbf.select("products", "name", "WHERE product_id=?", (order_id,))[0][0]
    # Добавляем комментарий в таблицу order_comments
    if call.data.startswith("access_comment"):
        if where_from == "order":
            dbf.update("order_comments", ("user_id", user_id), ("order_id", order_id))
            dbf.update("orders", ("rated", 1), ("order_id", order_id))
            access_text = f"Комментарий к заказу №{order_id} одобрен."
        else:
            access_text = f"Комментарий к блюду {dish_name} одобрен."
        bot.edit_message_text(chat_id=admin_group_chat_id, text=access_text, message_id=call.message.message_id)
    else:
        if where_from == "order":
            delete_text = f"Комментарий к заказу №{order_id} удален."
            dbf.delete("order_comments", ("order_id", order_id))
        else:
            delete_text = f"Комментарий к блюду {dish_name} удален."
            dbf.delete("dish_comments", ("product_id", order_id))
        bot.edit_message_text(chat_id=admin_group_chat_id, text=delete_text, message_id=call.message.message_id)
        bot.edit_message_text(chat_id=call.from_user.id, message_id=message_id, text="Ваш отзыв был удален по одной из следующих причин:\nОтзыв неинформативен\nОтзыв содержит ненормативную лексику")
@bot.message_handler(func=lambda message: message.text == "Мои заказы")
def handle_order_history(message):
    show_order_history(message.from_user.id)


# Обработчик команды "Оценить блюдо"
@bot.message_handler(func=lambda message: message.text == "Оценить блюдо")
def handle_rate_dish(message):
    user_id = message.from_user.id

    dishes = dbf.select("products", "*", "", ())
    print(dishes)
    # Генерируем клавиатуру с блюдами для оценки
    keyboard = types.InlineKeyboardMarkup()
    for dish in dishes:
        dish_id, dish_name, _, _, _, _, _, _ = dish
        keyboard.add(types.InlineKeyboardButton(f"{dish_name}", callback_data=f"rate_dish:{dish_id}"))

    bot.send_message(user_id, "Выберите блюдо для оценки:", reply_markup=keyboard)

# Обработчик для оценки блюда
@bot.callback_query_handler(func=lambda call: call.data.startswith('rate_dish:'))
def handle_marks_of_dish(call):
    from_user_id = call.from_user.id
    product_id = call.data.split(":")[1]
    message_id = call.message.message_id

    dish_info = dbf.s_product_info(product_id)
    if dish_info:
        dish_id, dish_name, description, dish_price, rating, total_ratings, _, _ = dish_info
    message_text = f"{dish_name}\n{description}\nЦена: {dish_price} руб.\n\n"
    image_path = f"images/{dish_id}.jpg"
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(InlineKeyboardButton("1", callback_data=f"mark_of_dish:{dish_id}:{1}"),
                 InlineKeyboardButton("2", callback_data=f"mark_of_dish:{dish_id}:{2}"),
                 InlineKeyboardButton("3", callback_data=f"mark_of_dish:{dish_id}:{3}"),
                 InlineKeyboardButton("4", callback_data=f"mark_of_dish:{dish_id}:{4}"),
                 InlineKeyboardButton("5", callback_data=f"mark_of_dish:{dish_id}:{5}"))
    keyboard.add(InlineKeyboardButton("Оставить комментарий", callback_data=f"comment_dish:{dish_id}"))
    keyboard.add(InlineKeyboardButton("Назад к блюдам", callback_data=f"back_to_dishes:"))

    try:
        if message_id:
            bot.edit_message_media(chat_id=from_user_id, message_id=message_id,
                                   media=InputMediaPhoto(open(image_path, 'rb'), caption=message_text),
                                   reply_markup=keyboard)
    except:
        bot.send_photo(from_user_id, open(image_path, 'rb'), caption=message_text, reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data.startswith("mark_of_dish:"))
def mark_of_dish(call):
    from_user_id = call.from_user.id
    user_id = dbf.s_user_id(from_user_id)[0]
    dish_id = call.data.split(":")[1]
    new_rating = int(call.data.split(":")[2])

    dish_info = dbf.s_product_info(dish_id)
    if dish_info:
        dish_id, dish_name, _, _, rating, total_ratings, _, _ = dish_info

        user_rating = dbf.select("dish_comments", "rating", "WHERE user_id = ? AND product_id = ?", (user_id, dish_id))
        if user_rating and user_rating[0][0] != None:
            bot.answer_callback_query(callback_query_id=call.id, text=f"Вы уже оценили {dish_name} на {int(user_rating[0][0])} звезд(ы).")
        else:
            # Получаем новую оценку от пользователя
            new_rating = int(call.data.split(":")[2])
            total_ratings += 1
            rating = ((rating * (total_ratings - 1)) + new_rating) / total_ratings

            test_dish = dbf.select("dish_comments", "comment_id", "WHERE product_id=?", (dish_id,))
            if test_dish and test_dish[0][0] != None:
                dbf.update("dish_comments", ("rating", new_rating), ("product_id", dish_id))
            else:
                dbf.insert("dish_comments", "user_id, product_id, rating", (user_id, dish_id, new_rating))
            dbf.update("products", ("rating", rating), ("product_id", dish_id))
            dbf.update("products", ("total_ratings", total_ratings), ("product_id", dish_id))

            bot.answer_callback_query(callback_query_id=call.id, text=f"Спасибо за вашу оценку {dish_name}! Средняя оценка теперь {rating:.2f} звезд(ы).")


@bot.callback_query_handler(func=lambda call: call.data.startswith("comment_dish:"))
def comment_dish(call):
    from_user_id = call.from_user.id
    user_id = dbf.s_user_id(from_user_id)[0]
    dish_id = call.data.split(":")[1]

    dish_info = dbf.s_product_info(dish_id)
    if dish_info:
        dish_id, dish_name, _, _, rating, total_ratings, _, _ = dish_info

    user_comment = dbf.select("dish_comments", "comment_text", "WHERE user_id = ? AND product_id = ?", (user_id, dish_id))
    print(user_comment)
    if user_comment and user_comment[0][0] != None:
        bot.answer_callback_query(callback_query_id=call.id, text=f"Вы уже оставили комментарий к блюду {dish_name}")
    else:
        bot.send_message(from_user_id, "Введите ваш комментарий:")
        bot.register_next_step_handler(call.message, process_comment_dish, dish_id)

def process_comment_dish(message, dish_id):
    # Получить текст отзыва
    comment_text = message.text
    from_user_id = message.from_user.id
    user_id = dbf.s_user_id(from_user_id)[0]
    message_id = int(message.message_id) + 1
    print(message_id)

    if from_user_id:
        # Отправить пользователю его отзыв с кнопками "Сохранить отзыв" и "Изменить отзыв"
        keyboard = types.InlineKeyboardMarkup()
        save_button = types.InlineKeyboardButton("Сохранить отзыв",
                                                 callback_data=f"save_comment:{dish_id}:{message_id}:dish")
        edit_button = types.InlineKeyboardButton("Изменить отзыв",
                                                 callback_data=f"edit_comment:{dish_id}:{message_id}:dish")
        keyboard.add(save_button, edit_button)
        test_dish = dbf.select("dish_comments", "comment_id", "WHERE product_id=?", (dish_id,))
        if test_dish and test_dish[0][0] != None:
            dbf.update("dish_comments", ("comment_text", comment_text), ("product_id", dish_id))
        else:
            dbf.insert("dish_comments", "user_id, product_id, comment_text", (user_id, dish_id, comment_text))


        bot.send_message(from_user_id, f"Ваш отзыв:\n{comment_text}", reply_markup=keyboard)
    else:
        bot.send_message(from_user_id, "Ваш аккаунт не найден. Попробуйте позже.")


#Обработчик возврата к списку блюд на этапе оценки(удалилпрост)
@bot.callback_query_handler(func=lambda call: call.data.startswith("back_to_dishes:"))
def back_to_dishes(call):
    handle_rate_dish(call)


# Запуск бота
print("Ready")
bot.infinity_polling()