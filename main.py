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
ADMIN_IDS = [440138628]  # ←  ID админки

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
        await db.commit()

# === /start ===
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await db.commit()
    await message.answer("Добро пожаловать в *Магазин*!", parse_mode="Markdown", reply_markup=get_main_keyboard(user_id))

# === АДМИНКА ===
@dp.message(F.text == "Админка")
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("Админ-панель:", reply_markup=get_admin_keyboard())

@dp.message(F.text == "Назад")
async def back_to_main(message: types.Message):
    await message.answer("Главное меню:", reply_markup=get_main_keyboard(message.from_user.id))

# === ТОВАРЫ (СПИСОК) ===
@dp.message(F.text == "Товары")
async def list_products(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT p.id, p.name, p.price, c.name FROM products p JOIN categories c ON p.category_id = c.id")
        rows = await cursor.fetchall()
    if not rows:
        await message.answer("Нет товаров.")
        return
    text = "*Товары в магазине:*\n\n"
    for pid, name, price, cat in rows:
        text += f"ID: `{pid}`\n{name}\nЦена: {price:,.0f} ₽\nКатегория: {cat}\n\n"
    await message.answer(text.replace(",", " "), parse_mode="Markdown", reply_markup=get_admin_keyboard())

# === ИЗМЕНИТЬ ЦЕНУ ===
@dp.message(F.text == "Изменить цену")
async def change_price_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AdminStates.waiting_for_price)
    await message.answer("Введите ID товара и новую цену через пробел:\n\nПример: `7 99990`", parse_mode="Markdown")

@dp.message(AdminStates.waiting_for_price)
async def change_price_process(message: types.Message, state: FSMContext):
    try:
        prod_id, new_price = map(float, message.text.split())
        prod_id = int(prod_id)
        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute("SELECT name FROM products WHERE id = ?", (prod_id,))
            row = await cursor.fetchone()
            if not row:
                await message.answer("Товар не найден.")
                return
            await db.execute("UPDATE products SET price = ? WHERE id = ?", (new_price, prod_id))
            await db.commit()
        await message.answer(f"Цена товара *{row[0]}* изменена на *{new_price:,.0f} ₽*.", parse_mode="Markdown")
    except:
        await message.answer("Неверный формат. Пример: `7 99990`")
    await state.clear()

# === ДОБАВИТЬ ТОВАР ===
@dp.message(F.text == "Добавить товар")
async def add_product_start(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "Формат:\n"
        "/addprod Категория | Название | Описание | Цена\n\n"
        "Пример:\n"
        "/addprod Смартфоны | iPhone 16 | 256 ГБ, синий | 99990"
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
                await message.answer("Категория не найдена! Сначала добавьте: /addcat Название")
                return
            cat_id = row[0]
            await db.execute("INSERT INTO products (category_id, name, description, price) VALUES (?, ?, ?, ?)", (cat_id, name, desc, price))
            await db.commit()
        await message.answer(f"Товар *{name}* добавлен за {price:,.0f} ₽!", parse_mode="Markdown")
    except:
        await message.answer("Формат: /addprod Категория | Название | Описание | Цена")

# === ПРОФИЛЬ (с кнопкой для админа) ===
@dp.message(F.text == "Профиль")
async def profile(message: types.Message):
    user_id = message.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT balance, email FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        balance = row[0] if row else 0.0
        email = row[1] if row and row[1] else "не указана"
    text = f"*Ваш профиль:*\n\nID: `{user_id}`\nБаланс: `{balance:,.2f} ₽`\nПочта: `{email}`".replace(",", " ")
    
    builder = ReplyKeyboardBuilder()
    if is_admin(user_id):
        builder.button(text="Изменить цену")
    builder.button(text="Назад")
    builder.adjust(2)
    
    await message.answer(text, parse_mode="Markdown", reply_markup=builder.as_markup())

# === МАГАЗИН, КОРЗИНА, КАТАЛОГ — БЕЗ ИЗМЕНЕНИЙ ===
# (весь код от Магазина до Поддержки — вставь сюда из предыдущей версии)

# === ЗАПУСК ===
async def main():
    await create_db()
    print("Магазин-бот с админкой и редактированием цен запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
