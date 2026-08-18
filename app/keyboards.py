from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_user_main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🛍️ Open Store", callback_data="open_store")],
        [InlineKeyboardButton(text="💰 Top Up", callback_data="top_up"), InlineKeyboardButton(text="📦 Orders", callback_data="my_orders")],
        [InlineKeyboardButton(text="👤 My Account", callback_data="my_account"), InlineKeyboardButton(text="🎁 Invite & Earn", callback_data="invite_earn")],
        [InlineKeyboardButton(text="📑 Guides", url="https://t.me/rpshivalivetutorial/198"), InlineKeyboardButton(text="🎰 Spin & Win", callback_data="spin_win")],
        [InlineKeyboardButton(text="🗣️ Tell Friends", callback_data="tell_friends"), InlineKeyboardButton(text="🎧 Help Desk", url="https://t.me/RGCHEAT99")]
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton(text="⚙️ Open Admin Control Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_store_products() -> InlineKeyboardMarkup:
    products = [
        ("🛒 8 Ball Drip Client Android", "prod_8ball"),
        ("🛒 Br Mods - Root", "prod_brmods"),
        ("🛒 Bala Mod Menu Pro Non Root", "prod_bala"),
        ("🛒 Drip Client Apk - Non Root", "prod_drip"),
        ("🛒 Fluorite 8 Ball Pool iOS", "prod_fluorite"),
        ("🛒 HaxxCker Pro - Root", "prod_haxx")
    ]
    buttons = [[InlineKeyboardButton(text=name, callback_data=code)] for name, code in products]
    buttons.append([InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_product_plans() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🛒 Buy 1 DAYS - $1.00", callback_data="buy_v25_1d")],
        [InlineKeyboardButton(text="🛒 Buy 7 DAYS - $2.50", callback_data="buy_v25_7d")],
        [InlineKeyboardButton(text="🛒 Buy 1 MONTH - $5.50", callback_data="buy_v25_1m")],
        [InlineKeyboardButton(text="⬅️ Back to Store", callback_data="open_store")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Products", callback_data="adm_products"), InlineKeyboardButton(text="🔑 Keys", callback_data="adm_keys")],
        [InlineKeyboardButton(text="🏷️ LM Import", callback_data="adm_lm_import"), InlineKeyboardButton(text="📡 API Health", callback_data="adm_api_health")],
        [InlineKeyboardButton(text="👥 Users", callback_data="adm_users"), InlineKeyboardButton(text="⭐ Resellers", callback_data="adm_resellers")],
        [InlineKeyboardButton(text="❌ Close", callback_data="close_admin")]
    ])
