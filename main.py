import sqlite3
import datetime
import random
import requests
import telebot
import time
import threading
import os
import hashlib
import html
import re
import json
import difflib
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# RG CHEAT SHOP — Complete API Reseller Integration
# API Version: KeyHive / RBS Live Shop Integration

# Telegram Bot API Token
TOKEN = os.getenv('BOT_TOKEN', '8802969772:AAEJlruYDsrrlbvLD4yyWMJgDVk37MphqZM')

# Telegram Numeric Admin IDs
ADMIN_IDS = [6419247159]  

# --- FAMGATEWAY API CONFIGURATION ---
FAM_API_KEY = 'FAM_82B6FA7808EB1F97DFD0789B63EA50BE40C1C9AA'
BASE_GATEWAY_URL = 'https://fampaygateway.site/api'
RECEIVER_UPI = '8158833153@fam'

# --- KEYHIVE / RBS RESELLER API CONFIGURATION ---
RBS_BASE_URL = 'https://rpshivabot-production.up.railway.app/api/v1'
RBS_BEARER_TOKEN = os.getenv('RBS_BEARER_TOKEN', 'bkey_dtL7R_Tvx2AviMCKNnNxLXLU-MtY1vQJ4JvWIhkFccI')

# Support Configuration
WHATSAPP_NUM = '919907224550'
TELEGRAM_USER = 'RGCHEAT99'
UPDATE_CHANNEL_LINK = 'https://t.me/RGCHEATALLFILE'

try:
    bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=32)
except TypeError:
    bot = telebot.TeleBot(TOKEN)

admin_temp_data = {}
active_orders = {}

# FamGateway & API lifecycle settings
FAM_PAYMENT_TIMEOUT = 300
FAM_POLL_INTERVAL = 5
FAM_HTTP_TIMEOUT = 15

# Shared HTTP Session
HTTP_SESSION = requests.Session()
HTTP_SESSION.headers.update({"User-Agent": "RG-Cheat-Shop-Bot/1.0"})

guide_video_url = None

# ==================== RESELLER API ENGINE ====================
def get_api_headers():
    return {
        "Authorization": f"Bearer {RBS_BEARER_TOKEN}",
        "Content-Type": "application/json"
    }

def get_account_me():
    """GET /me — Get reseller account profile & rate limit"""
    try:
        res = HTTP_SESSION.get(f"{RBS_BASE_URL}/me", headers=get_api_headers(), timeout=FAM_HTTP_TIMEOUT)
        return res.json() if res.status_code == 200 else None
    except Exception as e:
        print(f"API /me Error: {e}")
        return None

def get_wallet_balance():
    """GET /balance — Get current wallet balance (USD)"""
    try:
        res = HTTP_SESSION.get(f"{RBS_BASE_URL}/balance", headers=get_api_headers(), timeout=FAM_HTTP_TIMEOUT)
        if res.status_code == 200:
            return res.json().get("balance", "0.00")
        return None
    except Exception as e:
        print(f"API Balance Error: {e}")
        return None

def fetch_api_products():
    """GET /products — Fetch all available products & variants"""
    try:
        res = HTTP_SESSION.get(f"{RBS_BASE_URL}/products", headers=get_api_headers(), timeout=FAM_HTTP_TIMEOUT)
        return res.json() if res.status_code == 200 else None
    except Exception as e:
        print(f"API Products Error: {e}")
        return None

def check_variant_stock(variant_id):
    """GET /stock/{variant_id} — Check keys in stock for a variant"""
    try:
        res = HTTP_SESSION.get(f"{RBS_BASE_URL}/stock/{variant_id}", headers=get_api_headers(), timeout=FAM_HTTP_TIMEOUT)
        return res.json() if res.status_code == 200 else None
    except Exception as e:
        print(f"API Stock Error: {e}")
        return None

def generate_key_from_api(variant_id, quantity=1):
    """POST /generate-key — Buy key(s) from reseller API"""
    url = f"{RBS_BASE_URL}/generate-key"
    payload = {
        "variant_id": int(variant_id),
        "quantity": int(quantity)
    }
    try:
        res = HTTP_SESSION.post(url, headers=get_api_headers(), json=payload, timeout=FAM_HTTP_TIMEOUT)
        if res.status_code == 200:
            data = res.json()
            key = data.get("key") or data.get("license_key") or data.get("keys")
            return {"success": True, "key": key, "raw": data}
        else:
            return {"success": False, "msg": res.text}
    except Exception as e:
        return {"success": False, "msg": str(e)}

def reset_hwid_api(license_key):
    """POST /reset — Reset HWID/devices for a key"""
    url = f"{RBS_BASE_URL}/reset"
    payload = {"license_key": str(license_key).strip()}
    try:
        res = HTTP_SESSION.post(url, headers=get_api_headers(), json=payload, timeout=FAM_HTTP_TIMEOUT)
        if res.status_code == 200:
            return {"success": True, "msg": "HWID successfully reset."}
        return {"success": False, "msg": res.text}
    except Exception as e:
        return {"success": False, "msg": str(e)}

def fetch_recent_orders():
    """GET /orders — Fetch recent orders history"""
    try:
        res = HTTP_SESSION.get(f"{RBS_BASE_URL}/orders", headers=get_api_headers(), timeout=FAM_HTTP_TIMEOUT)
        return res.json() if res.status_code == 200 else None
    except Exception as e:
        print(f"API Orders Error: {e}")
        return None

# ==================== DATABASE SETUP ====================
def init_db():
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            phone_number TEXT,
            country TEXT DEFAULT 'IN',
            balance REAL DEFAULT 0.0,
            ref_balance REAL DEFAULT 0.0,
            orders_count INTEGER DEFAULT 0,
            lifetime_spent REAL DEFAULT 0.0,
            total_deposited REAL DEFAULT 0.0,
            joined_date TEXT,
            is_verified INTEGER DEFAULT 0,
            is_reseller INTEGER DEFAULT 0,
            discount_percent REAL DEFAULT 0.0,
            referred_by INTEGER DEFAULT 0,
            referrals_count INTEGER DEFAULT 0,
            ref_discount_used INTEGER DEFAULT 0
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS order_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            user_id INTEGER,
            product_name TEXT,
            plan_days TEXT,
            price_paid REAL,
            purchased_key TEXT,
            date_time TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    conn.commit()
    conn.close()

init_db()

# ==================== BOT HANDLERS & CORE LOGIC ====================
@bot.message_handler(commands=['start'])
def start_command(message):
    first_name = message.from_user.first_name
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🛒 Buy Products", callback_data="buy_products"),
        InlineKeyboardButton("🔄 HWID Reset", callback_data="hwid_reset")
    )
    markup.add(
        InlineKeyboardButton("💳 Check Reseller Balance", callback_data="check_rbs_bal"),
        InlineKeyboardButton("📢 Updates Channel", url=UPDATE_CHANNEL_LINK)
    )
    
    welcome_text = (
        f"<b>Welcome to RG CHEAT SHOP, {html.escape(first_name)}!</b>\n\n"
        f"⚡ <i>All keys are directly synced with KeyHive API. Instant & Automated delivery!</i>\n\n"
        f"Please select an option below:"
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id

    if call.data == "check_rbs_bal":
        bal = get_wallet_balance()
        if bal is not None:
            bot.answer_callback_query(call.id, f"Current Balance: ${bal}")
            bot.send_message(chat_id, f"💰 <b>Reseller API Wallet Balance:</b> <code>${bal}</code>", parse_mode="HTML")
        else:
            bot.answer_callback_query(call.id, "Failed to connect with API.", show_alert=True)

    elif call.data == "hwid_reset":
        msg = bot.send_message(chat_id, "<b>Please enter the License Key you want to reset HWID for:</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_hwid_reset_input)

    elif call.data.startswith("buy_variant_"):
        variant_id = call.data.replace("buy_variant_", "")
        bot.answer_callback_query(call.id, "Generating key from Reseller API...")
        
        # Key purchasing process via API
        result = generate_key_from_api(variant_id=variant_id, quantity=1)
        if result["success"]:
            license_key = result["key"]
            success_msg = (
                f"✅ <b>Order Completed Successfully!</b>\n\n"
                f"🔑 <b>License Key:</b> <code>{license_key}</code>\n"
                f"📦 <b>Source:</b> KeyHive API\n\n"
                f"<i>Thank you for shopping with RG CHEAT SHOP!</i>"
            )
            bot.send_message(chat_id, success_msg, parse_mode="HTML")
        else:
            bot.send_message(
                chat_id,
                f"❌ <b>Order Failed!</b>\n\n<b>Reason:</b> {result['msg']}\n<i>Please check API balance or stock.</i>",
                parse_mode="HTML"
            )

def process_hwid_reset_input(message):
    license_key = message.text.strip()
    bot.send_message(message.chat.id, "🔄 <i>Processing HWID reset request with Reseller API...</i>", parse_mode="HTML")
    
    res = reset_hwid_api(license_key)
    if res["success"]:
        bot.send_message(message.chat.id, f"✅ <b>Success:</b> {res['msg']} for Key: <code>{license_key}</code>", parse_mode="HTML")
    else:
        bot.send_message(message.chat.id, f"❌ <b>Reset Failed:</b> {res['msg']}", parse_mode="HTML")

# ==================== MAIN STARTUP ====================
if __name__ == '__main__':
    print("RG Cheat Shop Bot connected to KeyHive API is running...")
    bot.infinity_polling(skip_pending=True)
