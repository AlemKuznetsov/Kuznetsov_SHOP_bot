import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_NAME = "shop.db"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def get_main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="Магазин")
    builder.button(text="Поддержка")
    builder.button(text="Профиль")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_shop_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="Каталог")
    builder.button(text="Корзина")
    builder.button(text="Назад")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

async def create_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance REAL DEFAULT 0.0,
                email TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY,
                name TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY,
                category_id INTEGER,
                name TEXT,
                description TEXT,
                price REAL
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS cart (
                user_id INTEGER,
                product_id INTEGER,
                quantity INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, product_id)
            )
        ''')

        await db.execute("DELETE FROM categories")
        await db.execute("DELETE FROM products")

        categories = [(1, "Смартфоны"), (2, "Ноутбуки"), (3, "Аксессуары")]
        for cid, name in categories:
            await db.execute("INSERT OR IGNORE INTO categories (id, name) VALUES (?, ?)", (cid, name))

        products = [
            (1, 1, "iPhone 15", "128 ГБ, черный, OLED 6.1\"", 89990),
            (2, 1, "Samsung S24", "256 ГБ, зеленый, AMOLED 6.2\"", 79990),
            (3, 2, "MacBook Air M2", "8 ГБ / 256 ГБ, серебристый", 119990),
            (4, 2, "Lenovo IdeaPad 3", "16 ГБ / 512 ГБ, серый", 59990),
            (5, 3, "Чехол для iPhone", "Силиконовый, черный", 1990),
            (6, 3, "Кабель USB-C", "1.5 м, плетеный", 990)
        ]
        for pid, cat_id, name, desc, price in products:
            await db.execute("INSERT OR IGNORE INTO products (id, category_id, name, description, price) VALUES (?, ?, ?, ?, ?)",
                           (pid, cat_id, name, desc, price))
        await db.commit()

@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await db.commit()
    await message.answer("Добро пожаловать в *Магазин*!", parse_mode="Markdown", reply_markup=get_main_keyboard())

@dp.message(F.text == "Магазин")
async def shop_menu(message: types.Message):
    await message.answer("Выберите действие:", reply_markup=get_shop_keyboard())

@dp.message(F.text == "Назад")
async def back_to_main(message: types.Message):
    await message.answer("Главное меню:", reply_markup=get_main_keyboard())

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
    builder.adjust(1)
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
        await db.execute("INSERT INTO cart (user_id, product_id) VALUES (?, ?) ON CONFLICT(user_id, product_id) DO UPDATE SET quantity = quantity + 1", (user_id, prod_id))
        await db.commit()
    await callback.answer("Добавлено в корзину!")

@dp.message(F.text == "Корзина")
async def show_cart(message: types.Message):
    user_id = message.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT p.name, p.price, c.quantity FROM cart c JOIN products p ON c.product_id = p.id WHERE c.user_id = ?", (user_id,))
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

@dp.message(F.text == "Поддержка")
async def support(message: types.Message):
    text = "*Поддержка:*\n\nПочта: `akuznetsov348@ya.ru`\nВремя работы: 10:00 – 20:00"
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

@dp.message(F.text == "Профиль")
async def profile(message: types.Message):
    user_id = message.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT balance, email FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        balance = row[0] if row else 0.0
        email = row[1] if row and row[1] else "не указана"
    text = f"*Ваш профиль:*\n\nID: `{user_id}`\nБаланс: `{balance:,.2f} ₽`\nПочта: `{email}`".replace(",", " ")
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def main():
    await create_db()
    print("Магазин-бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
