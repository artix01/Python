import sqlite3

# Подключение к базе данных SQLite
conn = sqlite3.connect('bot_database.db', check_same_thread=False)
cursor = conn.cursor()

def select(table: str, columns: str, condition: str, params: tuple):
    with conn:
        cursor.execute(f"SELECT {columns} FROM {table} {condition}", params)
        return cursor.fetchall()

def insert(table: str, columns: str, data: tuple[any]):
    quastions = ""
    for i in data:
        if quastions == "":
            quastions += "?"
        else:
            quastions += ", ?"
    print(quastions)
    query = f"INSERT INTO {table} ({columns}) VALUES ({quastions})"

    with conn:
        cursor.execute(query, data)
        conn.commit()


def s_user_id(telegram_id : int):
    cursor.execute("SELECT user_id FROM customers WHERE telegram_id = ?", (telegram_id,))
    return cursor.fetchone()

def s_categories():
    """
    Получает список категорий из базы данных.
    """
    cursor.execute("SELECT DISTINCT categories FROM products")
    return cursor.fetchall()

def s_products_from_category(category_name: str):
    """
    Получает список блюд из выбранной категории.

    Args:
        category_name (str): Название категории.

    Returns:
        list: Список блюд из указанной категории.
    """
    cursor.execute("SELECT * FROM products WHERE categories=?", (category_name,))
    return cursor.fetchall()

def s_product_info(product_id: int, column_names: str = "*"):
    """
    Получает информацию о выбранном блюде по его идентификатору из базы данных.

    Args:
        product_id (int): Идентификатор продукта.

    Returns:
        tuple: Кортеж с информацией о продукте.
    """
    cursor.execute(f"SELECT {column_names} FROM products WHERE product_id=?", (product_id,))
    return cursor.fetchone()

def s_basket(user_id: int):
    """
    Получает корзину пользователя из базы данных по его идентификатору.

    Args:
        user_id (int): Идентификатор пользователя.

    Returns:
        tuple: Кортеж с данными о корзине пользователя.
    """
    cursor.execute("SELECT basket_data FROM basket WHERE user_id=?", (user_id,))
    return cursor.fetchone()

def update(table: str, column_data: tuple[str, any], identifier: tuple[str, any]):
    """
    Обновляет данные в указанной таблице.

    Args:
        table (str): Имя таблицы, в которой нужно обновить данные.
        column_data (tuple): Кортеж, содержащий данные для обновления (новое значение и имя столбца).
        identifier (tuple): Кортеж, содержащий идентификатор для поиска записи (имя столбца и значение идентификатора).
    """
    query = f"UPDATE {table} SET {column_data[0]}=? WHERE {identifier[0]}=?"

    with conn:
        cursor.execute(query, (column_data[1], identifier[1]))
        conn.commit()

def delete(table: str, identifier: tuple[str, any]):
    """
    Удаляет запись из указанной таблицы по заданному идентификатору.

    Args:
        table (str): Имя таблицы, из которой нужно удалить запись.
        identifier (tuple): Кортеж, содержащий идентификатор для удаления записи (имя столбца и значение идентификатора).
    """
    query = f"DELETE FROM {table} WHERE {identifier[0]} = ?"

    with conn:
        cursor.execute(query, (identifier[1],))
        conn.commit()
