from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select
from decimal import Decimal
from app.config import settings
from app.db import SessionLocal
from app.models import User, Product, Variant, CustomPrice

router = Router()

def admin_only(message: Message) -> bool:
    return message.from_user.id in settings.admins

@router.message(Command("admin"))
async def admin(message: Message):
    if not admin_only(message):
        return
    await message.answer(
        "👑 Admin commands:\n"
        "/addproduct Name\n"
        "/addvariant PRODUCT_ID | Name | Price | Stock\n"
        "/setprice USER_ID | VARIANT_ID | PRICE\n"
        "/balance USER_ID | AMOUNT\n"
        "/ban USER_ID\n"
        "/unban USER_ID"
    )

@router.message(Command("addproduct"))
async def addproduct(message: Message):
    if not admin_only(message): return
    name = message.text.partition(" ")[2].strip()
    if not name: return await message.answer("Usage: /addproduct Product Name")
    async with SessionLocal() as db:
        p = Product(name=name)
        db.add(p)
        await db.commit()
        await message.answer(f"✅ Product created: #{p.id} {p.name}")

@router.message(Command("addvariant"))
async def addvariant(message: Message):
    if not admin_only(message): return
    try:
        product_id, name, price, stock = [x.strip() for x in message.text.partition(" ")[2].split("|")]
        async with SessionLocal() as db:
            v = Variant(product_id=int(product_id), name=name,
                        price=Decimal(price), stock=int(stock))
            db.add(v)
            await db.commit()
            await message.answer(f"✅ Variant created: #{v.id}")
    except Exception:
        await message.answer("Usage: /addvariant PRODUCT_ID | Name | Price | Stock")

@router.message(Command("setprice"))
async def setprice(message: Message):
    if not admin_only(message): return
    try:
        user_id, variant_id, price = [x.strip() for x in message.text.partition(" ")[2].split("|")]
        async with SessionLocal() as db:
            result = await db.execute(select(CustomPrice).where(
                CustomPrice.telegram_id == int(user_id),
                CustomPrice.variant_id == int(variant_id)
            ))
            cp = result.scalar_one_or_none()
            if cp:
                cp.price = Decimal(price)
            else:
                db.add(CustomPrice(telegram_id=int(user_id), variant_id=int(variant_id),
                                   price=Decimal(price)))
            await db.commit()
        await message.answer("✅ Custom price saved.")
    except Exception:
        await message.answer("Usage: /setprice USER_ID | VARIANT_ID | PRICE")

@router.message(Command("balance"))
async def balance(message: Message):
    if not admin_only(message): return
    try:
        user_id, amount = [x.strip() for x in message.text.partition(" ")[2].split("|")]
        async with SessionLocal() as db:
            result = await db.execute(select(User).where(User.telegram_id == int(user_id)))
            user = result.scalar_one_or_none()
            if not user:
                return await message.answer("User not found.")
            user.balance = Decimal(user.balance) + Decimal(amount)
            await db.commit()
        await message.answer("✅ Balance updated.")
    except Exception:
        await message.answer("Usage: /balance USER_ID | AMOUNT")

@router.message(Command("ban"))
async def ban(message: Message):
    if not admin_only(message): return
    try:
        user_id = int(message.text.partition(" ")[2])
        async with SessionLocal() as db:
            result = await db.execute(select(User).where(User.telegram_id == user_id))
            user = result.scalar_one_or_none()
            if not user: return await message.answer("User not found.")
            user.banned = True
            await db.commit()
        await message.answer("🚫 User banned.")
    except Exception:
        await message.answer("Usage: /ban USER_ID")

@router.message(Command("unban"))
async def unban(message: Message):
    if not admin_only(message): return
    try:
        user_id = int(message.text.partition(" ")[2])
        async with SessionLocal() as db:
            result = await db.execute(select(User).where(User.telegram_id == user_id))
            user = result.scalar_one_or_none()
            if not user: return await message.answer("User not found.")
            user.banned = False
            await db.commit()
        await message.answer("✅ User unbanned.")
    except Exception:
        await message.answer("Usage: /unban USER_ID")
