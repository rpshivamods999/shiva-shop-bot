from aiogram import Router, F
from aiogram.types import CallbackQuery
from app.keyboards import get_admin_panel
from app.config import ADMIN_IDS
from app.services.shop import fetch_rbs_balance

admin_router = Router()

@admin_router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Unauthorized!", show_alert=True)
        return
    
    await call.answer()
    bal = await fetch_rbs_balance()
    admin_text = (
        f"⚙️ <b>WELCOME TO OUR STORE — CONTROL PANEL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <b>Bot:</b> @RpShivaLive_ShopBot\n"
        f"👤 <b>Admin:</b> {call.from_user.id}\n"
        f"🌐 <b>API Wallet Balance:</b> ${bal}\n\n"
        f"Select an admin option below:"
    )
    await call.message.edit_text(admin_text, reply_markup=get_admin_panel(), parse_mode="HTML")

@admin_router.callback_query(F.data == "close_admin")
async def cb_close_admin(call: CallbackQuery):
    await call.answer()
    await call.message.delete()
  
