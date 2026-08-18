from decimal import Decimal
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select
from app.db import SessionLocal
from app.models import User, Product, Variant, Order
from app.keyboards import main_menu, variants_menu
from app.services.shop import effective_price

router = Router()

async def get_or_create_user(tg):
    async with SessionLocal() as db:
        result = await db.execute(select(User).where(User.telegram_id == tg.id))
        user = result.scalar_one_or_none()
        if not user:
            user = User(telegram_id=tg.id, username=tg.username)
            db.add(user)
            await db.commit()
        return user

@router.message(CommandStart())
async def start(message: Message):
    user = await get_or_create_user(message.from_user)
    if user.banned:
        return await message.answer("🚫 Your account is banned.")
    await message.answer(
        "🛍️ Welcome to the Shop Bot!\n\nChoose an option:",
        reply_markup=main_menu()
    )

@router.callback_query(F.data == "shop")
async def shop(callback: CallbackQuery):
    async with SessionLocal() as db:
        result = await db.execute(select(Product).where(Product.active.is_(True)))
        products = result.scalars().all()
    if not products:
        return await callback.message.edit_text("No products available right now.")
    buttons = [[{"text": p.name, "callback_data": f"product:{p.id}"}] for p in products]
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(**b[0])] for b in buttons
    ])
    await callback.message.edit_text("🛍️ Select a product:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("product:"))
async def product(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])
    async with SessionLocal() as db:
        result = await db.execute(select(Variant).where(
            Variant.product_id == product_id, Variant.active.is_(True)
        ))
        variants = result.scalars().all()
        prices = [(v, await effective_price(db, callback.from_user.id, v)) for v in variants]
    if not prices:
        return await callback.answer("No variants available.", show_alert=True)
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{v.name} — ₹{price}", callback_data=f"buy:{v.id}")]
        for v, price in prices
    ])
    await callback.message.edit_text("Choose a plan:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("buy:"))
async def buy(callback: CallbackQuery):
    variant_id = int(callback.data.split(":")[1])
    async with SessionLocal() as db:
        result = await db.execute(select(Variant).where(Variant.id == variant_id))
        variant = result.scalar_one_or_none()
        if not variant or not variant.active:
            return await callback.answer("Product unavailable.", show_alert=True)
        if variant.stock <= 0:
            return await callback.answer("Out of stock.", show_alert=True)
        price = await effective_price(db, callback.from_user.id, variant)
        order = Order(telegram_id=callback.from_user.id, variant_id=variant.id,
                      amount=price, status="pending")
        db.add(order)
        await db.commit()
        order_id = order.id
    await callback.message.edit_text(
        f"🧾 Order #{order_id}\n\n"
        f"📦 {variant.name}\n"
        f"💰 Amount: ₹{price}\n\n"
        "Payment gateway modules will be connected here."
    )
    await callback.answer()

@router.callback_query(F.data == "balance")
async def balance(callback: CallbackQuery):
    user = await get_or_create_user(callback.from_user)
    await callback.message.edit_text(f"💰 Your balance: ₹{user.balance}")
    await callback.answer()

@router.callback_query(F.data == "account")
async def account(callback: CallbackQuery):
    user = await get_or_create_user(callback.from_user)
    await callback.message.edit_text(
        f"👤 Account\n\n🆔 {user.telegram_id}\n"
        f"💰 Balance: ₹{user.balance}\n"
        f"📅 Joined: {user.created_at:%Y-%m-%d}"
    )
    await callback.answer()

@router.callback_query(F.data == "orders")
async def orders(callback: CallbackQuery):
    async with SessionLocal() as db:
        result = await db.execute(select(Order).where(
            Order.telegram_id == callback.from_user.id
        ).order_by(Order.id.desc()).limit(10))
        rows = result.scalars().all()
    text = "📦 Your latest orders:\n\n"
    text += "\n".join(f"#{o.id} — ₹{o.amount} — {o.status}" for o in rows) or "No orders yet."
    await callback.message.edit_text(text)
    await callback.answer()

@router.callback_query(F.data == "coupon")
async def coupon(callback: CallbackQuery):
    await callback.message.edit_text("🎟️ Coupon system is ready for the next step.")
    await callback.answer()

@router.callback_query(F.data == "help")
async def help_menu(callback: CallbackQuery):
    await callback.message.edit_text("🆘 Please contact support.")
    await callback.answer()
