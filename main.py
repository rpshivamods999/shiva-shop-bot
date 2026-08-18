Import sqlite3
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

# QR styling/decoding dependencies. The payment gateway and verification flow
# remain unchanged; these libraries are used only to render the QR beautifully.
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers.pil import RoundedModuleDrawer, SquareModuleDrawer
from qrcode.image.styles.colormasks import SolidFillColorMask
from PIL import Image, ImageDraw
import cv2
import numpy as np

# RP TEST SHOP — feature-preserving UI/emoji/price-list update
# Version: 2026-08-18 — Add Balance UI/keypad/live-balance fix; existing checkout logic preserved
# ID input safety patch: Telegram commands can no longer be saved as Product/Valid IDs.

# Telegram Bot API Token
TOKEN = '8802969772:AAGf3O-ufGto5H3QyUPaQhdNMjIjR0dT0yY'

# Telegram Numeric Admin ID (Supports multiple admins if needed)
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
    # Compatibility with older pyTelegramBotAPI releases.
    bot = telebot.TeleBot(TOKEN)
admin_temp_data = {}

# Active Order Tracking Dictionary for In-Bot Verification
active_orders = {}

# Per-user Add Balance keypad state.
topup_keypad_state = {}

# Shared HTTP session reduces connection setup overhead for provider/gateway requests.
HTTP_SESSION = requests.Session()
HTTP_SESSION.headers.update({"User-Agent": "RG-Cheat-Shop-Bot/1.0"})

# Dynamic Guide Link Variable
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
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_new_server_plan_product ON new_server_plan_ids(product_name)")
    except Exception:
        pass

    # Multi New-API Server registry. Existing new_server_* tables are preserved
    # for backward compatibility; these tables add per-server mappings without
    # deleting or rewriting any existing products, plans or settings.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_name TEXT NOT NULL,
            api_key TEXT NOT NULL DEFAULT '',
            server_url TEXT NOT NULL DEFAULT '',
            enabled INTEGER DEFAULT 0,
            created_at TEXT,
            last_connected_at TEXT DEFAULT '',
            account_name TEXT DEFAULT '',
            account_username TEXT DEFAULT '',
            account_user_id TEXT DEFAULT ''
        )
    ''')
    # Connection/account metadata is additive only; all existing server rows are preserved.
    for column_sql in (
        "ALTER TABLE api_servers ADD COLUMN last_connected_at TEXT DEFAULT ''",
        "ALTER TABLE api_servers ADD COLUMN account_name TEXT DEFAULT ''",
        "ALTER TABLE api_servers ADD COLUMN account_username TEXT DEFAULT ''",
        "ALTER TABLE api_servers ADD COLUMN account_user_id TEXT DEFAULT ''",
    ):
        try:
            cursor.execute(column_sql)
        except Exception:
            pass

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_server_products (
            server_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            product_id TEXT NOT NULL DEFAULT '',
            updated_at TEXT,
            PRIMARY KEY(server_id, product_name)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_server_plan_ids (
            server_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            plan_id INTEGER NOT NULL,
            valid_id TEXT NOT NULL DEFAULT '',
            plan_days TEXT NOT NULL DEFAULT '',
            updated_at TEXT,
            PRIMARY KEY(server_id, product_name, plan_id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS product_server_selection (
            product_name TEXT PRIMARY KEY,
            server_id INTEGER NOT NULL,
            updated_at TEXT
        )
    ''')
    for index_sql in (
        "CREATE INDEX IF NOT EXISTS idx_api_servers_enabled ON api_servers(enabled)",
        "CREATE INDEX IF NOT EXISTS idx_api_server_products_product ON api_server_products(product_name)",
        "CREATE INDEX IF NOT EXISTS idx_api_server_plans_product ON api_server_plan_ids(product_name)",
    ):
        try:
            cursor.execute(index_sql)
        except Exception:
            pass
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hack_server_plan_product ON hack_server_plan_ids(product_name)")
    except Exception:
        pass
    
    try:
        cursor.execute("ALTER TABLE products ADD COLUMN tg_group_link TEXT DEFAULT ''")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE products ADD COLUMN is_out_of_stock INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN ref_discount_used INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE products ADD COLUMN require_device_id INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE products ADD COLUMN display_order INTEGER DEFAULT 0")
    except Exception:
        pass
    
    # Performance indexes: preserve all existing data/logic while making
    # product/plan/stock lookups much faster for every Telegram user.
    for index_sql in (
        "CREATE INDEX IF NOT EXISTS idx_products_name_id ON products(name, id)",
        "CREATE INDEX IF NOT EXISTS idx_products_name_order ON products(name, display_order)",
        "CREATE INDEX IF NOT EXISTS idx_panels_name_days_sold ON panels(panel_name, validity_days, is_sold)",
        "CREATE INDEX IF NOT EXISTS idx_orders_user ON order_history(user_id, id)",
    ):
        try:
            cursor.execute(index_sql)
        except Exception:
            pass

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


def _hack_server_config(product_name):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    try:
        cur=conn.cursor(); cur.execute('SELECT product_name, api_key, server_url, product_id, updated_at FROM hack_server_configs WHERE product_name=?',(str(product_name),)); return cur.fetchone()
    finally: conn.close()

def _hack_server_plan_valid_id(product_name, plan_id):
    conn=sqlite3.connect('shop_data.db',timeout=15)
    try:
        cur=conn.cursor(); cur.execute('SELECT valid_id FROM hack_server_plan_ids WHERE product_name=? AND plan_id=?',(str(product_name),int(plan_id))); row=cur.fetchone(); return str(row[0]).strip() if row and row[0] else ''
    finally: conn.close()

def _save_hack_server_config(product_name, api_key, server_url, remote_product_id):
    conn=sqlite3.connect('shop_data.db',timeout=15)
    try:
        conn.execute('''INSERT INTO hack_server_configs(product_name,api_key,server_url,product_id,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(product_name) DO UPDATE SET api_key=excluded.api_key,server_url=excluded.server_url,product_id=excluded.product_id,updated_at=excluded.updated_at''',(str(product_name),str(api_key).strip(),str(server_url).strip(),str(remote_product_id).strip(),datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))); conn.commit()
    finally: conn.close()

def _save_hack_server_plan_valid_id(product_name, plan_id, plan_days, valid_id):
    conn=sqlite3.connect('shop_data.db',timeout=15)
    try:
        conn.execute('''INSERT INTO hack_server_plan_ids(product_name,plan_id,valid_id,plan_days,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(product_name,plan_id) DO UPDATE SET valid_id=excluded.valid_id,plan_days=excluded.plan_days,updated_at=excluded.updated_at''',(str(product_name),int(plan_id),str(valid_id).strip(),str(plan_days),datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))); conn.commit()
    finally: conn.close()

def _get_hack_server_status(product_name):
    cfg=_hack_server_config(product_name)
    if not cfg: return None
    return {'api_key':cfg[1],'server_url':cfg[2],'product_id':cfg[3],'updated_at':cfg[4]}

def _resolve_api_route(product_name, plan_id=None, local_pid_id=None, duration=None):
    new_cfg=_new_server_config(product_name) if product_name else None
    if new_cfg and new_cfg[1] and new_cfg[2] and new_cfg[3]:
        new_valid_id=_new_server_plan_valid_id(product_name,plan_id) if plan_id is not None else ''
        if plan_id is None or new_valid_id:
            return {'url':new_cfg[2],'api_key':new_cfg[1],'product_id':new_cfg[3],'valid_id':new_valid_id,'server_type':'new'}
    cfg=_hack_server_config(product_name)
    if cfg and cfg[1] and cfg[2]:
        return {'url':cfg[2],'api_key':cfg[1],'product_id':cfg[3] or str(local_pid_id or ''),'valid_id':_hack_server_plan_valid_id(product_name,plan_id) if plan_id else '','server_type':'legacy_hack'}
    return {'url':get_setting('server_api_url') or RESELLER_API_URL,'api_key':get_setting('server_api_key') or RESELLER_API_KEY,'product_id':str(local_pid_id or ''),'valid_id':'','server_type':'legacy'}


# ==================== NEW SERVER API SYSTEM ====================
def _new_server_config(product_name):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    try:
        cur = conn.cursor(); cur.execute('SELECT product_name, api_key, server_url, product_id, updated_at FROM new_server_configs WHERE product_name=?', (str(product_name),)); return cur.fetchone()
    finally: conn.close()

def _new_server_plan_valid_id(product_name, plan_id):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    try:
        cur = conn.cursor(); cur.execute('SELECT valid_id FROM new_server_plan_ids WHERE product_name=? AND plan_id=?', (str(product_name), int(plan_id))); row = cur.fetchone(); value = str(row[0]).strip() if row and row[0] is not None else ''
        return '' if value.startswith('/') else value
    finally: conn.close()

def _save_new_server_config(product_name, api_key, server_url, remote_product_id):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    try:
        conn.execute('''INSERT INTO new_server_configs(product_name,api_key,server_url,product_id,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(product_name) DO UPDATE SET api_key=excluded.api_key,server_url=excluded.server_url,product_id=excluded.product_id,updated_at=excluded.updated_at''', (str(product_name),str(api_key).strip(),str(server_url).strip(),str(remote_product_id).strip(),datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))); conn.commit()
    finally: conn.close()

def _save_new_server_plan_valid_id(product_name, plan_id, plan_days, valid_id):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    try:
        conn.execute('''INSERT INTO new_server_plan_ids(product_name,plan_id,valid_id,plan_days,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(product_name,plan_id) DO UPDATE SET valid_id=excluded.valid_id,plan_days=excluded.plan_days,updated_at=excluded.updated_at''', (str(product_name),int(plan_id),str(valid_id),str(plan_days),datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))); conn.commit()
    finally: conn.close()

def _new_server_is_configured(product_name, plan_id=None):
    cfg=_new_server_config(product_name)
    if not cfg or not cfg[1] or not cfg[2] or not cfg[3]: return False
    return plan_id is None or bool(_new_server_plan_valid_id(product_name,plan_id))

def _new_server_hack_by_hash(value):
    for product_name in get_unique_products():
        if _ui_hash(product_name)==str(value): return product_name
    return None

def _new_server_hacks_markup():
    markup=types.InlineKeyboardMarkup()
    for prod in get_unique_products():
        status='🟢' if _new_server_is_configured(prod) else '⚪'
        markup.add(types.InlineKeyboardButton(f'{status} {prod}',callback_data=f'new_server_hack_{_ui_hash(prod)}'))
    markup.add(types.InlineKeyboardButton('🔙 Back',callback_data='admin_api_system'))
    return markup

def _new_server_plans_markup(product_name):
    markup=types.InlineKeyboardMarkup(); cfg=_new_server_config(product_name); pid=cfg[3] if cfg else '—'
    for plan in get_product_plans(product_name):
        plan_id=int(plan[0]); days=str(plan[2]); valid_id=_new_server_plan_valid_id(product_name,plan_id); status='🟢' if valid_id else '⚪'
        label=f'{status} {days} | PID:{pid} | VID:{valid_id or "—"}'
        markup.add(types.InlineKeyboardButton(label[:60],callback_data=f'new_server_plan_{_ui_hash(product_name)}_{plan_id}'))
    markup.add(types.InlineKeyboardButton('🔙 Hack List',callback_data='new_server_api'))
    return markup

def _new_server_status_text():
    return '🟢 CONNECTED' if str(get_setting(NEW_SERVER_ENABLED_KEY) or '0')=='1' else '🔴 NOT CONNECTED'

def _new_server_test_connection():
    try:
        res=HTTP_SESSION.post(NEW_SERVER_API_URL,data={'api_key':NEW_SERVER_API_KEY,'action':'balance'},headers={'Content-Type':'application/x-www-form-urlencoded','x-master-key':RESELLER_MASTER_KEY},timeout=8)
        return res.status_code==200,res.text[:300]
    except Exception as exc: return False,str(exc)[:300]

# ==================== GLOBAL PRICE-LIST / EMOJI TEMPLATE ====================
GLOBAL_PRICE_LIST_TEMPLATE_KEY = 'global_price_list_template'

def get_global_price_list_template():
    return get_setting(GLOBAL_PRICE_LIST_TEMPLATE_KEY)

def set_global_price_list_template(template):
    if template is None:
        template = ''
    set_setting(GLOBAL_PRICE_LIST_TEMPLATE_KEY, str(template).strip())


# ==================== PREMIUM PRICE-LIST MODE ====================
# When enabled, the saved master price-list template is used for every product.
# Live plans/prices/stock/discounts are still generated from the database.
PRICE_LIST_PREMIUM_MODE_KEY = 'price_list_premium_mode'


def get_price_list_premium_mode():
    return str(get_setting(PRICE_LIST_PREMIUM_MODE_KEY) or '0') == '1'


def set_price_list_premium_mode(enabled):
    set_setting(PRICE_LIST_PREMIUM_MODE_KEY, '1' if enabled else '0')


# ==================== PLAN TEXT ADD — PREMIUM HEADER OVERRIDE ====================
# This is the simple admin-controlled text shown above the live plan buttons.
# It intentionally overrides older price-list/header text without deleting any
# product, plan, price, stock, discount or checkout data. Premium custom emojis
# are stored as Telegram <tg-emoji> HTML and are rendered exactly as sent.
PLAN_TEXT_ADD_KEY = 'plan_text_add_template'

def get_plan_text_add():
    return get_setting(PLAN_TEXT_ADD_KEY) or ''

def set_plan_text_add(template):
    set_setting(PLAN_TEXT_ADD_KEY, str(template or '').strip())


# ==
