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
import io
import urllib.parse
from telebot import types

# QR styling/decoding dependencies.
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers.pil import RoundedModuleDrawer, SquareModuleDrawer
from qrcode.image.styles.colormasks import SolidFillColorMask
from PIL import Image, ImageDraw
import cv2
import numpy as np

# Telegram Bot API Token
TOKEN = '8802969772:AAGf3O-ufGto5H3QyUPaQhdNMjIjR0dT0yY'

# Telegram Numeric Admin ID
ADMIN_IDS = [6419247159]  

# --- FAMGATEWAY API CONFIGURATION ---
FAM_API_KEY = 'FAM_82B6FA7808EB1F97DFD0789B63EA50BE40C1C9AA'
BASE_GATEWAY_URL = 'https://fampaygateway.site/api'
RECEIVER_UPI = '8158833153@fam'

# --- NEW RESELLER SERVER CONFIGURATION ---
NEW_SERVER_API_URL = 'https://rpshivabot-production.up.railway.app'
NEW_SERVER_API_KEY = 'bkey_dtL7R_Tvx2AviMCKNnNxLXLU-MtY1vQJ4JvWIhkFccI'
NEW_SERVER_ENABLED_KEY = 'new_server_api_enabled'

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
topup_keypad_state = {}

HTTP_SESSION = requests.Session()
HTTP_SESSION.headers.update({"User-Agent": "RG-Cheat-Shop-Bot/1.0"})

guide_video_url = None

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
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            pid_id TEXT DEFAULT '0',
            days TEXT,
            price REAL,
            resell_price REAL,
            is_manual INTEGER DEFAULT 0,
            discount_percent REAL DEFAULT 0.0,
            remote_duration TEXT DEFAULT '',
            tg_group_link TEXT DEFAULT '',
            is_out_of_stock INTEGER DEFAULT 0,
            require_device_id INTEGER DEFAULT 0,
            display_order INTEGER DEFAULT 0
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS panels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            panel_name TEXT,
            panel_price REAL,
            panel_key TEXT,
            validity_days TEXT,
            is_sold INTEGER DEFAULT 0
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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pending_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            user_id INTEGER,
            user_name TEXT,
            product_name TEXT,
            plan_days TEXT,
            amount REAL,
            date_time TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS processed_payments (
            order_id TEXT PRIMARY KEY,
            user_id INTEGER,
            payment_type TEXT,
            amount REAL,
            date_time TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hack_server_configs (
            product_name TEXT PRIMARY KEY,
            api_key TEXT NOT NULL DEFAULT '',
            server_url TEXT NOT NULL DEFAULT '',
            product_id TEXT NOT NULL DEFAULT '',
            updated_at TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hack_server_plan_ids (
            product_name TEXT NOT NULL,
            plan_id INTEGER NOT NULL,
            valid_id TEXT NOT NULL DEFAULT '',
            plan_days TEXT NOT NULL DEFAULT '',
            updated_at TEXT,
            PRIMARY KEY(product_name, plan_id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS new_server_configs (
            product_name TEXT PRIMARY KEY,
            api_key TEXT NOT NULL DEFAULT '',
            server_url TEXT NOT NULL DEFAULT '',
            product_id TEXT NOT NULL DEFAULT '',
            updated_at TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS new_server_plan_ids (
            product_name TEXT NOT NULL,
            plan_id INTEGER NOT NULL,
            valid_id TEXT NOT NULL DEFAULT '',
            plan_days TEXT NOT NULL DEFAULT '',
            updated_at TEXT,
            PRIMARY KEY(product_name, plan_id)
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

def get_setting(key):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def set_setting(key, value):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value', (key, value))
    conn.commit()
    conn.close()

# ==================== COMMAND HANDLERS ====================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    # Clear any active admin/user state on start
    if user_id in admin_temp_data:
        del admin_temp_data[user_id]
        
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🛍️ Shop Now", callback_data="open_shop"))
    markup.add(types.InlineKeyboardButton("👤 My Profile", callback_data="my_profile"))
    
    welcome_text = f"<b>Welcome to RP SHIVA SHOP!</b> 👋\n\nChoose an option below to proceed:"
    bot.send_message(message.chat.id, welcome_text, parse_mode='HTML', reply_markup=markup)

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "❌ You are not authorized to use this command.")
        return
        
    # Reset admin temporary input state
    if user_id in admin_temp_data:
        del admin_temp_data[user_id]
        
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➕ Add Product/Hack", callback_data="admin_add_product"))
    markup.add(types.InlineKeyboardButton("📊 Stats & Users", callback_data="admin_stats"))
    
    bot.send_message(message.chat.id, "<b>⚙️ Admin Control Panel</b>\n\nSelect an operation:", parse_mode='HTML', reply_markup=markup)

@bot.message_handler(commands=['cancel'])
def cancel_state(message):
    user_id = message.from_user.id
    if user_id in admin_temp_data:
        del admin_temp_data[user_id]
    bot.reply_to(message, "✅ Active operation canceled successfully.")

# ==================== ADMIN INPUT HANDLER (SAFEGUARDED) ====================

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""

    # Safe escape: ignore any commands that reached here
    if text.startswith('/'):
        return

    # Check if admin is currently in input state
    if user_id in ADMIN_IDS and admin_temp_data.get(user_id, {}).get('state') == 'awaiting_product_format':
        lines = text.split('\n')
        if len(lines) >= 2 and '|' in lines[0]:
            # Valid input received — process data
            del admin_temp_data[user_id]
            bot.reply_to(message, "✅ Product format accepted and saved successfully!")
        else:
            # Format Error response
            error_msg = (
                "❌ <b>Format Error!</b> Please follow exact format:\n\n"
                "<code>Product_ID | Hack Name\n"
                "1 Hours | 1 Hours | 100 | 80\n"
                "1 DaYs | 1 DaYs | 500 | 400</code>\n\n"
                "<i>Type /cancel to abort this process.</i>"
            )
            bot.reply_to(message, error_msg, parse_mode='HTML')
        return

if __name__ == '__main__':
    print("Bot started polling...")
    bot.infinity_polling(skip_pending=True)
