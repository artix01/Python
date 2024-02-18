import telebot
from telebot import types
import sqlite3
import json
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


# Глобальная переменная для хранения категорий блюд
categories = []
current_category = None
g_dishes = None
# Обработчик команды "Меню"
@bot.message_handler(func=lambda message: message.text == "Меню")
def handle_menu(message):
    global categories
    user_id = message.from_user.id

    with conn:
        # Получаем список категорий из базы данных
        cursor.execute("SELECT DISTINCT categories FROM products")
        categories = cursor.fetchall()

        if categories:
            # Формируем клавиатуру с кнопками для переключения между категориями
            category_buttons = InlineKeyboardMarkup(row_width=2)
            for category in categories:
                category_name = category[0]
                category_buttons.add(InlineKeyboardButton(category_name, callback_data=f"category:{category_name}"))

            # Отправляем сообщение с кнопками категорий
            bot.send_message(user_id, "Выберите категорию:", reply_markup=category_buttons)
        else:
            bot.send_message(user_id, "Извините, меню временно недоступно.")

# Обработчик нажатия на кнопку переключения между блюдами
@bot.callback_query_handler(func=lambda call: call.data.startswith("next_dish:") or call.data.startswith("prev_dish:"))
def handle_dish_switch_callback(call):
    global current_category, g_dishes
    print("handle_dish_switch_callback", current_category)
    user_id = call.from_user.id
    print(call.data)
    action, dish_index, total_dishes = call.data.split(":")

    dish_index = int(dish_index)
    total_dishes = int(total_dishes)

    with conn:
        cursor.execute("SELECT * FROM products WHERE categories=?", (current_category,))
        dishes = cursor.fetchall()
        g_dishes = dishes
        print("dishes", dishes, "current dish index", dish_index)

        if total_dishes == 1:
            # Если в категории всего одно блюдо, игнорируем запрос
            bot.answer_callback_query(callback_query_id=call.id, text="В данной категории только одно блюдо")
            return

        # Отправляем сообщение с карточкой следующего блюда
        if action == "next_dish":
            next_dish_index = (dish_index + 1) % total_dishes
        else:
            next_dish_index = (dish_index - 1) % total_dishes

        send_dish_card(user_id, dishes[next_dish_index], next_dish_index, total_dishes, current_category, call.message.message_id)

# Обработчик нажатия на кнопку переключения категории (следующая или предыдущая)
@bot.callback_query_handler(func=lambda call: call.data.startswith("next_category:") or call.data.startswith("prev_category:"))
def handle_category_switch_callback(call):
    global current_category, g_dishes
    user_id = call.from_user.id
    action, current_category_name = call.data.split(":")
    print(current_category_name)
    print(categories)
    current_category_index = categories.index((current_category_name,))
    print(current_category_index)
    categories_count = len(categories)

    if action == "next_category":
        next_category_index = (current_category_index + 1) % categories_count
    else:
        next_category_index = (current_category_index - 1) % categories_count

    next_category_name = categories[next_category_index][0]  # Получаем только имя категории
    current_category = next_category_name  # Обновляем текущую категорию

    with conn:
        cursor.execute("SELECT * FROM products WHERE categories=?", (next_category_name,))
        dishes = cursor.fetchall()
        g_dishes = dishes
        if dishes:
            send_dish_card(user_id, dishes[0], 0, len(dishes), next_category_name, call.message.message_id)
        else:
            bot.send_message(user_id, "В данной категории нет блюд.")

# Обработчик нажатия на кнопку категории
@bot.callback_query_handler(func=lambda call: call.data.startswith("category:"))
def handle_category_callback(call):
    global current_category, g_dishes
    category_name = call.data.split(":")[1]
    user_id = call.from_user.id

    with conn:
        cursor.execute("SELECT * FROM products WHERE categories=?", (category_name,))
        dishes = cursor.fetchall()

        if dishes:
            send_dish_card(user_id, dishes[0], 0, len(dishes), category_name, call.message.message_id)
            current_category = category_name
            g_dishes= dishes
            print("current_category", current_category, "dishes[0]", dishes[0])
        else:
            bot.send_message(user_id, "В данной категории нет блюд.")

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
    user_id = call.from_user.id
    quantity = int(call.data.split(":")[1]) + 1  # Увеличиваем количество на 1
    current_index = int(call.data.split(":")[2])
    print("cat", g_dishes[current_index][6])
    send_dish_card(user_id, g_dishes[current_index], current_index, len(g_dishes), g_dishes[current_index][6], call.message.message_id, quantity=quantity)

# Обработчик нажатия кнопки "-"
@bot.callback_query_handler(func=lambda call: call.data.startswith("decrease_quantity:"))
def handle_decrease_quantity(call):
    user_id = call.from_user.id
    quantity = int(call.data.split(":")[1]) - 1  # Уменьшаем количество на 1
    current_index = int(call.data.split(":")[2])

    if quantity < 1:
        # Если количество стало меньше 1, игнорируем запрос
        bot.answer_callback_query(callback_query_id=call.id, text="Количество не может быть меньше 1")
        return
    # Переотправляем сообщение с карточкой блюда с обновленным количеством
    send_dish_card(user_id, g_dishes[current_index], current_index, len(g_dishes), g_dishes[current_index][6], call.message.message_id, quantity=quantity)

# Обработчик нажатия кнопки "Добавить в корзину"
@bot.callback_query_handler(func=lambda call: call.data.startswith("add_to_basket:"))
def handle_add_to_cart(call):
    user_id = call.from_user.id
    quantity = int(call.data.split(":")[1])
    current_index = int(call.data.split(":")[2])
    product_id = g_dishes[current_index][0]  # Получаем id продукта из данных кнопки

    # Получаем информацию о выбранном блюде из базы данных
    with conn:
        cursor.execute("SELECT * FROM products WHERE product_id=?", (product_id,))
        product = cursor.fetchone()

        if product:
            # Получаем корзину пользователя из базы данных
            cursor.execute("SELECT basket FROM users WHERE user_id=?", (user_id,))
            basket_data = cursor.fetchone()

            if basket_data:
                # Если корзина не пуста, загружаем её из JSON
                basket = json.loads(basket_data[0])
            else:
                # Если корзина пуста, создаем новую
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
            cursor.execute("UPDATE users SET basket=? WHERE user_id=?", (json.dumps(basket), user_id))
            conn.commit()

            # Отправляем пользователю сообщение о добавлении в корзину
            bot.answer_callback_query(callback_query_id=call.id, text=f"{product[1]} добавлен в корзину")

        else:
            bot.answer_callback_query(callback_query_id=call.id, text="Произошла ошибка при добавлении в корзину")


# Обработчик команды "Корзина"
@bot.message_handler(func=lambda message: message.text == "Корзина")
def handle_cart_menu(message):
    user_id = message.from_user.id

    send_basket_dish_card(user_id)

def send_basket_dish_card(user_id, message_id=None, current_index=0):
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

    # Переменная для хранения инлайн клавиатуры
    keyboard = InlineKeyboardMarkup(row_width=3)

    # Переменная для хранения данных о корзине
    total_items = len(basket)

    # Получаем информацию о текущем товаре в корзине
    current_item = basket[current_index]
    product_id = current_item['product_id']
    quantity = current_item['quantity']
    print("index", current_index)
    # Получаем информацию о товаре из базы данных
    cursor.execute("SELECT name, price FROM products WHERE product_id=?", (product_id,))
    product_info = cursor.fetchone()

    if product_info:
        dish_name = product_info[0]
        dish_price = product_info[1]
        image_path = f"images/{product_id}.jpg"
        cart_message = f"{dish_name} (количество: {quantity}, цена: {dish_price} руб.)"
        cart_message += f"\nБлюдо {current_index + 1} из {total_items}"

        # Создаем кнопки для управления количеством товара и кнопку удаления товара
        increase_button = InlineKeyboardButton("+", callback_data=f"cart_item:increase:{current_index}:{quantity}")
        decrease_button = InlineKeyboardButton("-", callback_data=f"cart_item:decrease:{current_index}:{quantity}")
        delete_button = InlineKeyboardButton(f"Удалить {dish_name}", callback_data=f"cart_item:delete:{product_id}")

        # Создаем кнопки для переключения между товарами в корзине
        prev_button = InlineKeyboardButton("◀️", callback_data=f"prev_cart_item:{current_index}:{total_items}")
        next_button = InlineKeyboardButton("▶️", callback_data=f"next_cart_item:{current_index}:{total_items}")
        keyboard.row(prev_button, decrease_button, increase_button, next_button)
        keyboard.add(delete_button)

        if message_id:
            bot.edit_message_media(chat_id=user_id, message_id=message_id,
                                   media=InputMediaPhoto(open(image_path, 'rb'), caption=cart_message),
                                   reply_markup=keyboard)
        else:
            bot.send_photo(user_id, open(image_path, 'rb'), caption=cart_message, reply_markup=keyboard)

# Обработчик нажатия кнопок изменения quantity(basket) и удаления товара из корзины
@bot.callback_query_handler(func=lambda call: call.data.startswith("cart_item:"))
def handle_change_quantity(call):
    user_id = call.from_user.id
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
            cursor.execute("SELECT basket FROM users WHERE user_id=?", (user_id,))
            user_data = cursor.fetchone()

            if user_data:
                basket = json.loads(user_data[0]) if user_data[0] else []  # Разбираем JSON, если корзина не пуста
            else:
                basket = []

            # Удаляем товар из корзины по его идентификатору
            new_basket = [item for item in basket if item['product_id'] != product_id]

            # Обновляем корзину пользователя в базе данных
            cursor.execute("UPDATE users SET basket=? WHERE user_id=?", (json.dumps(new_basket), user_id))
            conn.commit()

        # Отправляем обновленную информацию о корзине пользователю
        send_basket_dish_card(user_id, call.message.message_id)
        return

    # Получаем текущую корзину пользователя из базы данных
    with conn:
        cursor.execute("SELECT basket FROM users WHERE user_id=?", (user_id,))
        user_data = cursor.fetchone()

        if user_data:
            basket = json.loads(user_data[0]) if user_data[0] else []  # Разбираем JSON, если корзина не пуста
        else:
            basket = []

        # Обновляем количество товара в корзине
        basket[current_index]['quantity'] = new_quantity

        # Обновляем корзину пользователя в базе данных
        cursor.execute("UPDATE users SET basket=? WHERE user_id=?", (json.dumps(basket), user_id))
        conn.commit()

    # Отправляем обновленную информацию о корзине пользователю
    send_basket_dish_card(user_id, call.message.message_id, current_index=current_index)



# Обработчик нажатия кнопок переключения между товарами в корзине
@bot.callback_query_handler(func=lambda call: call.data.startswith("prev_cart_item") or call.data.startswith("next_cart_item"))
def handle_change_cart_item(call):
    user_id = call.from_user.id

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

    send_basket_dish_card(user_id, call.message.message_id, next_index)

# Обработчик команды "Оформить заказ"
@bot.callback_query_handler(func=lambda call: call.data == "checkout")
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
            cursor.execute("UPDATE users SET basket = ? WHERE user_id = ?", (json.dumps([]), user_id))
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