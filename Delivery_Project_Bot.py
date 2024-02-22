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

# Подключение к базе данных SQLite
conn = sqlite3.connect('bot_database.db', check_same_thread=False)
cursor = conn.cursor()


# Основное меню
main_menu = types.ReplyKeyboardMarkup(resize_keyboard=True)
main_menu.add(types.KeyboardButton("Меню"))
main_menu.add(types.KeyboardButton("Корзина"))
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
g_dishes = None

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
    dish_id, dish_name, dish_description, dish_price, dish_rating, total_ratings, category = dish
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
            user_data = dbf.select("customers", "name, email, address", ("user_id", user_id))
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
    user_id = message.from_user.id

    if step == 'name':
        # Обрабатываем шаг с именем
        name = message.text
        dbf.update("customers", ("name", name), ("user_id", user_id))

        # Переходим к следующему шагу
        bot.send_message(user_id, "Отлично! Теперь укажите ваш email:")
        bot.register_next_step_handler(message, lambda msg: process_step(msg, 'email'))

    elif step == 'email':
        # Обрабатываем шаг с email
        email = message.text
        dbf.update("customers", ("email", email), ("user_id", user_id))

        # После получения email, запрашиваем адрес
        bot.send_message(user_id, "Теперь укажите ваш адрес:")
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

# Обработка шага "address_choice"
def address_step(message, step):
    user_id = dbf.s_user_id(message.from_user.id)[0]
    basket = []

    if step == 'address_choice':
        address = message.text
        dbf.update("customers", ("address", address), ("user_id", user_id))

        # Получаем данные о корзине пользователя
        with conn:
            user_data = dbf.s_basket(user_id)

            if user_data:
                basket = json.loads(user_data[0]) if user_data[0] else []

        # Вычисляем общую стоимость заказа
        total_price = calculate_total_price(basket)

        # Вставляем запись в таблицу orders
        with conn:
            cursor.execute("INSERT INTO orders (user_id, address, total_price, estimated_delivery_time, basket) "
                           "VALUES (?, ?, ?, ?, ?)",
                           (user_id, address, total_price, 30, json.dumps(basket)))
            conn.commit()

            # Очищаем корзину пользователя
            dbf.update("basket", ("basket_data", "[]"), ("user_id", user_id))
        # Отправляем пользователю примерное время ожидания
        estimated_delivery_time = 30  # в минутах
        bot.send_message(message.from_user.id, f"Спасибо! Ваш заказ принят. Ожидайте доставку по адресу: {address}. "
                                   f"Примерное время ожидания: {estimated_delivery_time} минут.", reply_markup=main_menu)


# Запуск бота
print("Ready")
bot.infinity_polling()