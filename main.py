import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import os

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_NAME = "shop.db"
ADMIN_IDS = [123456789]  # ← ВСТАВЬ СВОЙ ID ЗДЕСЬ

# === ИНИЦИАЛИЗАЦИЯ ===
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# === FSM ===
class AdminStates(StatesGroup):
    waiting_for_price = State()

# === ПРОВЕРКА АДМИНА ===
def is_admin(user_id):
    return user_id in ADMIN_IDS

# === КЛАВИАТУРЫ ===
def get_main_keyboard(user_id):
    builder = ReplyKeyboardBuilder()
    builder.button(text="Магазин")
    builder.button(text="Поддержка")
    builder.button(text="Профиль")
    if is_admin(user_id):
        builder.button(text="Админка")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_shop_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="Каталог")
    builder.button(text="Корзина")
    builder.button(text="Назад")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_admin_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="Товары")
    builder.button(text="Изменить цену")
    builder.button(text="Добавить товар")
    builder.button(text="Назад")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

# === БД ===
async def create_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0.0, email TEXT)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY AUTOINCREMENT, category_id INTEGER, name TEXT, description TEXT, price REAL)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS cart (user_id INTEGER, product_id INTEGER, quantity INTEGER DEFAULT 1, PRIMARY KEY (user_id, product_id))''')
        
        # Тестовые данные
        await db.execute("INSERT OR IGNORE INTO categories (name) VALUES ('Смартфоны'), ('Ноутбуки'), ('Аксессуары')")
        await db.execute("""
            INSERT OR IGNORE INTO products (category_id, name, description, price) VALUES 
            (1, 'iPhone 15', '128 ГБ, черный, OLED 6.1"', 89990),
            (1, 'Samsung S24', '256 ГБ, зеленый, AMOLED 6.2"', 79990),
            (2, 'MacBook Air M2', '8 ГБ / 256 ГБ, серебристый', 119990)
        """)
        await db.commit()

# === /start ===
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await db.commit()
    await message.answer(
        "Добро пожаловать в *Магазин*!",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(user_id)
    )

# === МАГАЗИН ===
@dp.message(F.text == "Магазин")
async def shop_menu(message: types.Message):
    await message.answer("Выберите действие:", reply_markup=get_shop_keyboard())

@dp.message(F.text == "Назад")
async def back_to_main(message: types.Message):
    await message.answer("Главное меню:", reply_markup=get_main_keyboard(message.from_user.id))

# === КАТАЛОГ ===
@dp.message(F.text == "Каталог")
async def catalog(message: types.Message):
    builder = InlineKeyboardBuilder()
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT id, name FROM categories")
        rows = await cursor.fetchall()
        for cat_id, name in rows:
            builder.button(text=name, callback_data=f"cat_{cat_id}")
    builder.adjust(2)
    await message.answer("Выберите категорию:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("cat_"))
async def show_products(callback: types.CallbackQuery):
    cat_id = int(callback.data.split("_")[1])
    builder = InlineKeyboardBuilder()
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT id, name FROM products WHERE category_id = ?", (cat_id,))
        rows = await cursor.fetchall()
        for prod_id, name in rows:
            builder.button(text=name, callback_data=f"prod_{prod_id}")
    builder.row(types.InlineKeyboardButton(text="Назад", callback_data="back_to_cat"))
    await callback.message.edit_text("Выберите товар:", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "back_to_cat")
async def back_to_catalog(callback: types.CallbackQuery):
    await catalog(callback.message)

@dp.callback_query(F.data.startswith("prod_"))
async def show_product(callback: types.CallbackQuery):
    prod_id = int(callback.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT name, description, price FROM products WHERE id = ?", (prod_id,))
        row = await cursor.fetchone()
        if row:
            name, desc, price = row
            builder = InlineKeyboardBuilder()
            builder.button(text="Добавить в корзину", callback_data=f"add_{prod_id}")
            builder.button(text="Назад", callback_data="back_to_cat")
            text = f"*{name}*\n\n{desc}\n\n*Цена:* {price:,.0f} ₽".replace(",", " ")
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("add_"))
async def add_to_cart(callback: types.CallbackQuery):
    prod_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO cart (user_id, product_id) 
            VALUES (?, ?) 
            ON CONFLICT(user_id, product_id) 
            DO UPDATE SET quantity = quantity + 1
        """, (user_id, prod_id))
        await db.commit()
    await callback.answer("Добавлено в корзину!")

# === КОРЗИНА ===
@dp.message(F.text == "Корзина")
async def show_cart(message: types.Message):
    user_id = message.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT p.name, p.price, c.quantity 
            FROM cart c 
            JOIN products p ON c.product_id = p.id 
            WHERE c.user_id = ?
        """, (user_id,))
        rows = await cursor.fetchall()

    if not rows:
        await message.answer("Корзина пуста.", reply_markup=get_shop_keyboard())
        return

    total = 0
    text = "*Ваша корзина:*\n\n"
    for name, price, qty in rows:
        subtotal = price * qty
        total += subtotal
        text += f"• {name} × {qty} = {subtotal:,.0f} ₽\n".replace(",", " ")
    text += f"\n*Итого:* {total:,.0f} ₽".replace(",", " ")
    builder = InlineKeyboardBuilder()
    builder.button(text="Очистить корзину", callback_data="clear_cart")
    builder.button(text="Назад", callback_data="back_to_shop")
    await message.answer(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "clear_cart")
async def clear_cart(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
        await db.commit()
    await callback.message.edit_text("Корзина очищена!", reply_markup=get_shop_keyboard())

@dp.callback_query(F.data == "back_to_shop")
async def back_to_shop(callback: types.CallbackQuery):
    await shop_menu(callback.message)

# === ПОДДЕРЖКА ===
@dp.message(F.text == "Поддержка")
async def support(message: types.Message):
    text = "*Поддержка:*\n\nПочта: `akuznetsov348@ya.ru`\nВремя работы: 10:00 – 20:00"
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard(message.from_user.id))

# === ПРОФИЛЬ — ИСПРАВЛЕНО! ===
@dp.message(F.text == "Профиль")
async def profile(message: types.Message):
    user_id = message.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT balance, email FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        balance = row[0] if row else 0.0
        email = row[1] if row and row[1] else "не указана"
    text = f"*Ваш профиль:*\n\nID: `{user_id}`\nБаланс: `{balance:,.2f} ₽`\nПочта: `{email}`".replace(",", " ")
    # ← ВОЗВРАЩАЕМ ГЛАВНУЮ КЛАВИАТУРУ БЕЗ "ИЗМЕНИТЬ ЦЕНУ"
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard(user_id))

# === АДМИНКА ===
@dp.message(F.text == "Админка")
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("Админ-панель:", reply_markup=get_admin_keyboard())

@dp.message(F.text == "Товары")
async def list_products(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT p.id, p.name, p.price, c.name FROM products p JOIN categories c ON p.category_id = c.id")
        rows = await cursor.fetchall()
    if not rows:
        await message.answer("Нет товаров.", reply_markup=get_admin_keyboard())
        return
    text = "*Товары в магазине:*\n\n"
    for pid, name, price, cat in rows:
        text += f"ID: `{pid}`\n{name}\nЦена: {price:,.0f} ₽\nКатегория: {cat}\n\n"
    await message.answer(text.replace(",", " "), parse_mode="Markdown", reply_markup=get_admin_keyboard())

@dp.message(F.text == "Изменить цену")
async def change_price_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AdminStates.waiting_for_price)
    await message.answer("Введите ID товара и новую цену:\n\nПример: `7 99990`", parse_mode="Markdown", reply_markup=get_admin_keyboard())

@dp.message(AdminStates.waiting_for_price)
async def change_price_process(message: types.Message, state: FSMContext):
    try:
        prod_id, new_price = map(float, message.text.split())
        prod_id = int(prod_id)
        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute("SELECT name FROM products WHERE id = ?", (prod_id,))
            row = await cursor.fetchone()
            if not row:
                await message.answer("Товар не найден.", reply_markup=get_admin_keyboard())
                return
            await db.execute("UPDATE products SET price = ? WHERE id = ?", (new_price, prod_id))
            await db.commit()
        await message.answer(f"Цена товара *{row[0]}* изменена на *{new_price:,.0f} ₽*.", parse_mode="Markdown", reply_markup=get_admin_keyboard())
    except:
        await message.answer("Неверный формат. Пример: `7 99990`", reply_markup=get_admin_keyboard())
    await state.clear()

@dp.message(F.text == "Добавить товар")
async def add_product_start(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "Формат:\n/addprod Категория | Название | Описание | Цена\n\n"
        "Пример:\n/addprod Смартфоны | iPhone 16 | 256 ГБ | 99990",
        reply_markup=get_admin_keyboard()
    )

@dp.message(Command("addprod"))
async def add_product(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    try:
        parts = message.text.replace("/addprod ", "").strip().split(" | ")
        cat_name, name, desc, price = parts[0], parts[1], parts[2], float(parts[3])
        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute("SELECT id FROM categories WHERE name = ?", (cat_name,))
            row = await cursor.fetchone()
            if not row:
                await message.answer("Категория не найдена! Сначала добавьте: /addcat Название", reply_markup=get_admin_keyboard())
                return
            cat_id = row[0]
            await db.execute("INSERT INTO products (category_id, name, description, price) VALUES (?, ?, ?, ?)", (cat_id, name, desc, price))
            await db.commit()
        await message.answer(f"Товар *{name}* добавлен за {price:,.0f} ₽!", parse_mode="Markdown", reply_markup=get_admin_keyboard())
    except:
        await message.answer("Формат: /addprod Категория | Название | Описание | Цена", reply_markup=get_admin_keyboard())

# === ЗАПУСК ===
async def main():
    await create_db()
    print("Магазин-бот с админкой запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
