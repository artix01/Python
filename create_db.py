import sqlite3



# Подключение к базе данных SQLite
conn = sqlite3.connect('bot_database.db')
cursor = conn.cursor()


# Создание таблицы пользователей
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT    
                )''')

cursor.execute('''CREATE TABLE IF NOT EXISTS basket (
                    user_id INTEGER PRIMARY KEY,
                    basket TEXT,
                    time TIMESTAMP
                )''')

# Создание таблицы для администраторов
cursor.execute('''CREATE TABLE IF NOT EXISTS administrators (
                    admin_id INTEGER PRIMARY KEY,
                    user_id INTEGER,
                    admin_level INTEGER     
                )''')

# Создание таблицы клиентов
cursor.execute('''CREATE TABLE IF NOT EXISTS customers (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    email TEXT,
                    address TEXT,
                    payment_method TEXT,
                    telegram_id INTEGER,
                    vk_id INTEGER
                )''')

# Создание таблицы заказов
cursor.execute('''CREATE TABLE IF NOT EXISTS orders (
                    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    address TEXT,
                    total_price REAL NOT NULL,
                    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    estimated_delivery_time INTEGER,
                    status TEXT DEFAULT 'в ожидании',  
                    basket TEXT,    
                    rated INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )''')

# Создание таблицы продуктов
cursor.execute('''CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY,
    name TEXT,
    description TEXT,
    price REAL,
    rating REAL DEFAULT 4.0,
    total_ratings INTEGER DEFAULT 0,
    categories TEXT
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS dish_comments (
    comment_id INTEGER PRIMARY KEY,
    user_id INTEGER,
    product_id INTEGER,
    comment_text TEXT,
    rating REAL
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS order_comments (
    comment_id INTEGER PRIMARY KEY,
    user_id INTEGER,
    order_id INTEGER,
    comment_text TEXT
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS admin_users (
    user_id INTEGER PRIMARY KEY,
    admin_id INTEGER,
    admin_level INTEGER
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS admin_panels (
    admin_id INTEGER PRIMARY KEY,
    panel_name TEXT
)''')


conn.commit()