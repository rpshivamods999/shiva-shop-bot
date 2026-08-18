from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍️ Shop", callback_data="shop")],
        [InlineKeyboardButton(text="💰 Balance", callback_data="balance"),
         InlineKeyboardButton(text="📦 Orders", callback_data="orders")],
        [InlineKeyboardButton(text="🎟️ Coupon", callback_data="coupon"),
         InlineKeyboardButton(text="👤 Account", callback_data="account")],
        [InlineKeyboardButton(text="🆘 Help", callback_data="help")],
    ])

def variants_menu(variants):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{v.name} — ₹{v.price}",
            callback_data=f"buy:{v.id}"
        )] for v in variants
    ])
