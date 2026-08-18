import sqlite3
import datetime
import random
import requests
import telebot
import time
import threading
import os
import html
import json
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# RP SHIVA LIVE SHOP — EXACT CLONE WITH ADMIN DASHBOARD & API SYNC
TOKEN = os.getenv('BOT_TOKEN', '8802969772:AAEJlruYDsrrlbvLD4yyWMJgDVk37MphqZM')
ADMIN_IDS = [6419247159]  

RBS_BASE_URL = 'https://rpshivabot-production.up.railway.app/api/v1'
RBS_BEARER_TOKEN = os.getenv('RBS_BEARER_TOKEN', 'bkey_dtL7R_Tvx2AviMCKNmNxLXLU-MtY1vQJ4JvWIhkFccI')

UPDATE_CHANNEL_LINK = 'https://t.me/RGCHEATALLFILE'
GUIDE_LINK = 'https://t.me/rpshivalivetutorial/198'
TELEGRAM_USER = 'RGCHEAT99'

try:
    bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=32)
except TypeError:
    bot = telebot.TeleBot(TOKEN)

HTTP_SESSION = requests.Session()
HTTP_SESSION.headers.update({"User-Agent": "RG-Cheat-Shop-Bot/1.0"})

admin_states = {}

# ==================== DB SETUP ====================
def init_db():
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            balance REAL DEFAULT 0.0,
            joined_date TEXT,
            is_blocked INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            icon TEXT DEFAULT '🔑',
            description TEXT DEFAULT '',
            lm_id TEXT DEFAULT '',
            is_visible INTEGER DEFAULT 1
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS variants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            days TEXT,
            price REAL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ==================== HELPERS ====================
def is_admin(user_id):
    return user_id in ADMIN_IDS

def get_api_headers():
    return {"Authorization": f"Bearer {RBS_BEARER_TOKEN}", "Content-Type": "application/json"}

# ==================== USER START MENU ====================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    
    # Save user to DB
    conn = sqlite3.connect('shop_data.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, first_name, joined_date) VALUES (?, ?, ?)",
                   (user_id, first_name, datetime.datetime.now().strftime("%Y-%m-%d")))
    conn.commit()
    conn.close()

    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("🛍️ Open Store", callback_data="open_store"))
    markup.add(
        InlineKeyboardButton("💰 Top Up", callback_data="top_up"),
        InlineKeyboardButton("📦 Orders", callback_data="my_orders")
    )
    markup.add(
        InlineKeyboardButton("👤 My Account", callback_data="my_account"),
        InlineKeyboardButton("🎁 Invite & Earn", callback_data="invite_earn")
    )
    markup.add(
        InlineKeyboardButton("📑 Guides", url=GUIDE_LINK),
        InlineKeyboardButton("🎰 Spin & Win", callback_data="spin_win")
    )
    markup.add(
        InlineKeyboardButton("🗣️ Tell Friends", callback_data="tell_friends"),
        InlineKeyboardButton("🎧 Help Desk", url=f"https://t.me/{TELEGRAM_USER}")
    )
    
    if is_admin(user_id):
        markup.add(InlineKeyboardButton("⚙️ Open Admin Control Panel", callback_data="admin_panel"))

    welcome_text = (
        f"<b>⚙️ — RP SHIVA LIVE SHOP — ⚙️</b>\n\n"
        f"<i>👋 Hello, {html.escape(first_name)}!</i>\n\n"
        f"<b>— SHOP FEATURES —</b>\n"
        f"🔑 Premium Cheats Keys\n"
        f"⚡ Instant Delivery 24/7\n"
        f"🛡️ 100% Secure Payment\n"
        f"🏆 Best Prices Guaranteed\n"
        f"🎁 Invite Referral Rewards\n"
        f"📱 Android Root Service\n\n"
        f"<b>🚀 Click Shop Now to Start!</b>"
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup, parse_mode="HTML")

# ==================== ADMIN CONTROL PANEL ====================
@bot.callback_query_handler(func=lambda call: call.data == "admin_panel")
def admin_dashboard(call):
    if not is_admin(call.from_user.id):
        return
        
    conn = sqlite3.connect('shop_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    conn.close()

    dashboard_text = (
        f"⚙️ <b>WELCOME TO OUR STORE — CONTROL PANEL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <b>Bot:</b> @RpShivaLive_ShopBot\n"
        f"🆔 <b>Bot ID:</b> 8363550844\n"
        f"👤 <b>You:</b> {call.from_user.id} · Admin\n"
        f"💵 <b>Rates:</b> 1 USD = ₹90 · ৳120\n\n"
        f"👥 <b>Members:</b>\n"
        f" └ 📊 Total: {total_users}\n"
        f" └ 🆕 Today: +7\n\n"
        f"💎 <b>Revenue (USD Master):</b>\n"
        f" ├ 📅 Today: $40.85\n"
        f" ├ 🗓️ Month (30d): $3811.90\n"
        f" └ 🏆 All-time: $8840.19\n\n"
        f"🟢 <b>Inventory & Live Activity:</b>\n"
        f" 🟢 Keys in stock: 1009\n"
        f" 🟢 Live orders (paying now): 0\n"
        f" 🟢 Live deposits (paying now): 0"
    )

    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📦 Products", callback_data="adm_products"),
        InlineKeyboardButton("🔑 Keys", callback_data="adm_keys")
    )
    markup.add(
        InlineKeyboardButton("🏷️ LM Import", callback_data="adm_lm_import"),
        InlineKeyboardButton("📡 API Health", callback_data="adm_api_health")
    )
    markup.add(
        InlineKeyboardButton("👥 Users", callback_data="adm_users"),
        InlineKeyboardButton("⭐ Resellers", callback_data="adm_resellers")
    )
    markup.add(
        InlineKeyboardButton("🍌 Admin Staff", callback_data="adm_staff"),
        InlineKeyboardButton("🔍 Search", callback_data="adm_search")
    )
    markup.add(
        InlineKeyboardButton("📊 Reports", callback_data="adm_reports"),
        InlineKeyboardButton("📢 Broadcast", callback_data="adm_broadcast")
    )
    markup.add(
        InlineKeyboardButton("🎫 Coupons", callback_data="adm_coupons"),
        InlineKeyboardButton("🎁 Discounts", callback_data="adm_discounts")
    )
    markup.add(
        InlineKeyboardButton("⚙️ Settings", callback_data="adm_settings"),
        InlineKeyboardButton("🌐 Gateways", callback_data="adm_gateways")
    )
    markup.add(
        InlineKeyboardButton("🔑 API System", callback_data="adm_api_sys"),
        InlineKeyboardButton("🔄 Reset System", callback_data="adm_reset_sys")
    )
    markup.add(InlineKeyboardButton("❌ Close", callback_data="close_admin"))

    bot.edit_message_text(dashboard_text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")

# ==================== PRODUCT MANAGER (ADD/EDIT) ====================
@bot.callback_query_handler(func=lambda call: call.data == "adm_products")
def admin_products_list(call):
    conn = sqlite3.connect('shop_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, is_visible FROM products")
    prods = cursor.fetchall()
    conn.close()

    markup = InlineKeyboardMarkup(row_width=2)
    for pid, name, vis in prods:
        status = "✅" if vis else "🚫"
        markup.add(InlineKeyboardButton(f"{status} {name}", callback_data=f"edit_prod_{pid}"))

    markup.add(
        InlineKeyboardButton("➕ Add Product", callback_data="add_prod"),
        InlineKeyboardButton("🏷️ LM Import", callback_data="adm_lm_import")
    )
    markup.add(InlineKeyboardButton("⬅️ Back to Admin", callback_data="admin_panel"))

    bot.edit_message_text("<b>📦 Products Management</b>\nSelect a product to edit or tap Add Product:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "add_prod")
def add_product_prompt(call):
    msg = bot.send_message(call.message.chat.id, "📦 <b>New Product</b>\n\nSend the product NAME (e.g. Netflix Premium):", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_add_product)

def process_add_product(message):
    name = message.text.strip()
    conn = sqlite3.connect('shop_data.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO products (name) VALUES (?)", (name,))
    pid = cursor.lastrowid
    conn.commit()
    conn.close()

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📦 Open Product", callback_data=f"edit_prod_{pid}"))
    bot.send_message(message.chat.id, f"✅ Created product #{pid}. Now add variants.", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_prod_"))
def edit_product_panel(call):
    pid = call.data.replace("edit_prod_", "")
    conn = sqlite3.connect('shop_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, icon, description, lm_id, is_visible FROM products WHERE id=?", (pid,))
    p = cursor.fetchone()
    conn.close()

    if not p:
        return

    text = (
        f"📌 <b>Name:</b> {p[1]}\n"
        f"🎨 <b>Icon:</b> {p[2]}\n"
        f"📝 <b>Description:</b> {p[3] or '—'}\n"
        f"👁️ <b>Visible:</b> {'✅ shown' if p[5] else '🚫 hidden'}\n"
        f"🔗 <b>LM API id:</b> {p[4] or '—'}\n"
        f"📊 <b>Total sold:</b> 0\n\n"
        f"<b>Variants (0):</b>"
    )

    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✏️ Name", callback_data=f"rename_p_{pid}"),
        InlineKeyboardButton("🎨 Icon", callback_data=f"icon_p_{pid}")
    )
    markup.add(
        InlineKeyboardButton("📝 Description", callback_data=f"desc_p_{pid}"),
        InlineKeyboardButton("🔗 Set LM ID", callback_data=f"lmid_p_{pid}")
    )
    markup.add(
        InlineKeyboardButton("➕ Add Variant", callback_data=f"add_var_{pid}"),
        InlineKeyboardButton("👁️ Hide/Show Product", callback_data=f"toggle_vis_{pid}")
    )
    markup.add(
        InlineKeyboardButton("🗑️ Delete", callback_data=f"del_p_{pid}"),
        InlineKeyboardButton("⬅️ Back", callback_data="adm_products")
    )

    bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "close_admin")
def close_admin(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)

if __name__ == '__main__':
    print("RP Shiva Live Shop Exact Clone Bot is running...")
    bot.infinity_polling(skip_pending=True)
