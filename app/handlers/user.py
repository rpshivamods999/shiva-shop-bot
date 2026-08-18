from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from app.keyboards import get_user_main_menu, get_store_products, get_product_plans
from app.config import ADMIN_IDS
from app.services.shop import generate_rbs_key

user_router = Router()

@user_router.message(CommandStart())
async def cmd_start(message: Message):
    is_admin = message.from_user.id in ADMIN_IDS
    welcome_text = (
        f"⚙️ — <b>RP SHIVA LIVE SHOP</b> — ⚙️\n\n"
        f"👋 <i>Hello, {message.from_user.first_name}!</i>\n\n"
        f"<b>— SHOP FEATURES —</b>\n"
        f"🔑 Premium Cheats Keys\n"
        f"⚡ Instant Delivery 24/7\n"
        f"🛡️ 100% Secure Payment\n"
        f"🏆 Best Prices Guaranteed\n\n"
        f"🚀 <b>Click Shop Now to Start!</b>"
    )
    await message.answer(welcome_text, reply_markup=get_user_main_menu(is_admin), parse_mode="HTML")

@user_router.callback_query(F.data == "open_store")
async def cb_open_store(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text(
        "<b>⭐ Available Products</b>\n\nChoose your product below 👇\n<i>Tap any item to see plans & prices.</i>",
        reply_markup=get_store_products(),
        parse_mode="HTML"
    )

@user_router.callback_query(F.data == "prod_8ball")
async def cb_prod_detail(call: CallbackQuery):
    await call.answer()
    plan_text = (
        "🛒 <b>8 BALL DRIP CLIENT ANDROID</b>\n\n"
        "📊 <b>STOCK & PRICING:</b>\n\n"
        "✅ <b>1 Days</b>\n └ 📦 Stock: In Stock\n └ 💰 Price: $1.00\n\n"
        "✅ <b>7 Days</b>\n └ 📦 Stock: In Stock\n └ 💰 Price: $2.50\n\n"
        "✅ <b>1 Month</b>\n └ 📦 Stock: In Stock\n └ 💰 Price: $5.50\n\n"
        "🎯 <b>SELECT YOUR PLAN:</b>"
    )
    await call.message.edit_text(plan_text, reply_markup=get_product_plans(), parse_mode="HTML")

@user_router.callback_query(F.data.startswith("buy_v"))
async def cb_buy_key(call: CallbackQuery):
    await call.answer("Connecting to API for Key...")
    res = await generate_rbs_key(variant_id=25)
    if res["success"]:
        await call.message.answer(f"✅ <b>Order Successful!</b>\n\n🔑 Key: <code>{res['key']}</code>", parse_mode="HTML")
    else:
        await call.message.answer(f"❌ <b>Order Failed:</b> {res['msg']}", parse_mode="HTML")

@user_router.callback_query(F.data == "main_menu")
async def cb_main_menu(call: CallbackQuery):
    await call.answer()
    is_admin = call.from_user.id in ADMIN_IDS
    await call.message.delete()
    await cmd_start(call.message)
  
