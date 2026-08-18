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

# QR styling/decoding dependencies. The payment gateway and verification flow
# remain unchanged; these libraries are used only to render the QR beautifully.
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers.pil import RoundedModuleDrawer, SquareModuleDrawer
from qrcode.image.styles.colormasks import SolidFillColorMask
from PIL import Image, ImageDraw
import cv2
import numpy as np

# RG CHEAT SHOP — feature-preserving UI/emoji/price-list update
# Version: 2026-08-18 — Add Balance UI/keypad/live-balance fix; existing checkout logic preserved

# Telegram Bot API Token
TOKEN = '8839947716:AAEWF9a3uymFB6LOFfVXzSK8k6dXoqN61qM'

# Telegram Numeric Admin ID (Supports multiple admins if needed)
ADMIN_IDS = [8781522303, 6739795427]  

# --- FAMGATEWAY API CONFIGURATION ---
FAM_API_KEY = 'FAM_82B6FA7808EB1F97DFD0789B63EA50BE40C1C9AA'
BASE_GATEWAY_URL = 'https://fampaygateway.site/api'
RECEIVER_UPI = '8158833153@fam'

# --- EXACT RESELLER API CONFIGURATION (PHP CONVERTED) ---
RESELLER_API_URL = 'https://xyzcheats.com/api/reseller_v1.php'
RESELLER_API_KEY = '55c24b72eea0f65267f231e4ab6a6754'
RESELLER_MASTER_KEY = 'a7f3e8b2c9d1f4a6b8c2d5e9f1a3b6c8'

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


# ==================== PER-PRODUCT PLAN TEXT + PREMIUM EMOJI ====================
PLAN_TEXT_PRODUCT_PREFIX = 'plan_text_product_'
PLAN_TEXT_PRODUCT_LAST_KEY = 'plan_text_product_last'
PLAN_TEXT_PRODUCT_LAST_NAME_KEY = 'plan_text_product_last_name'
PLAN_TEXT_PRODUCT_NAMES_KEY = 'plan_text_product_names'

def _plan_text_product_key(product_name):
    return PLAN_TEXT_PRODUCT_PREFIX + _ui_hash(product_name)

def _normalize_product_template_name(value):
    # Normalization is only for matching a saved design to a renamed/display-name
    # product. It never changes the actual product name in the database.
    value = str(value or '').lower()
    value = re.sub(r'[^a-z0-9]+', ' ', value)
    return ' '.join(value.split())

def _get_saved_product_template_names():
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cur = conn.cursor()
    try:
        cur.execute("SELECT key FROM settings WHERE key LIKE ?", (PLAN_TEXT_PRODUCT_PREFIX + '%',))
        rows = cur.fetchall()
    finally:
        conn.close()
    names = []
    prefix = PLAN_TEXT_PRODUCT_PREFIX
    for (key,) in rows:
        if key in (PLAN_TEXT_PRODUCT_LAST_KEY, PLAN_TEXT_PRODUCT_LAST_NAME_KEY):
            continue
        # Names are not stored in the key, so recover them from the saved catalog
        # only through the explicit last-name mapping. Exact lookup remains primary.
    return names

def get_plan_text_product(product_name):
    # 1. Exact product-name match (normal path).
    exact = get_setting(_plan_text_product_key(product_name)) or ''
    if exact:
        return exact

    wanted = _normalize_product_template_name(product_name)
    if not wanted:
        return ''

    # 2. Scan the saved-name map so a product can safely keep its design after
    # an admin renames the product. This does not alter the database product name.
    try:
        name_map = json.loads(get_setting(PLAN_TEXT_PRODUCT_NAMES_KEY) or '{}')
    except Exception:
        name_map = {}

    best_template = ''
    best_score = 0.0
    for saved_hash, saved_name in name_map.items():
        saved_name = str(saved_name or '')
        saved = _normalize_product_template_name(saved_name)
        if not saved:
            continue
        template = get_setting(PLAN_TEXT_PRODUCT_PREFIX + str(saved_hash)) or ''
        if not template:
            continue
        if saved == wanted:
            return template
        wanted_tokens = set(wanted.split())
        saved_tokens = set(saved.split())
        overlap = len(wanted_tokens & saved_tokens)
        ratio = difflib.SequenceMatcher(None, wanted, saved).ratio()
        score = ratio + min(overlap, 4) * 0.08
        if overlap >= 2 and ratio >= 0.45 and score > best_score:
            best_score = score
            best_template = template

    if best_template:
        return best_template

    # 3. Legacy migration fallback: if there is exactly one real saved product
    # design, use it for an unmatched product. Exclude the migration metadata
    # keys themselves from the count.
    last_template = get_setting(PLAN_TEXT_PRODUCT_LAST_KEY) or ''
    if last_template:
        conn = sqlite3.connect('shop_data.db', timeout=15)
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT COUNT(*) FROM settings WHERE key LIKE ? "
                "AND key NOT IN (?, ?, ?) AND value IS NOT NULL AND value != ''",
                (PLAN_TEXT_PRODUCT_PREFIX + '%',
                 PLAN_TEXT_PRODUCT_LAST_KEY,
                 PLAN_TEXT_PRODUCT_LAST_NAME_KEY,
                 PLAN_TEXT_PRODUCT_NAMES_KEY)
            )
            count = int(cur.fetchone()[0] or 0)
        finally:
            conn.close()
        if count == 1:
            return last_template

    return ''

def set_plan_text_product(product_name, template):
    cleaned = _repair_premium_emoji_markup(str(template or '').strip())
    product_name = str(product_name or '').strip()
    key_hash = _ui_hash(product_name)

    # Preserve the exact per-product design.
    set_setting(_plan_text_product_key(product_name), cleaned)

    # Keep a name map for safe rename/migration matching. Existing settings,
    # products, prices, stock and checkout data are never deleted.
    try:
        name_map = json.loads(get_setting(PLAN_TEXT_PRODUCT_NAMES_KEY) or '{}')
    except Exception:
        name_map = {}
    name_map[str(key_hash)] = product_name
    set_setting(PLAN_TEXT_PRODUCT_NAMES_KEY, json.dumps(name_map, ensure_ascii=False))

    # Keep a migration-safe last-template copy as a final legacy fallback.
    set_setting(PLAN_TEXT_PRODUCT_LAST_NAME_KEY, product_name)
    set_setting(PLAN_TEXT_PRODUCT_LAST_KEY, cleaned)

def _render_plan_text_product(template, live_rows, product_name):
    """Render the admin's custom design while injecting LIVE days/stock/price.

    The admin may write either explicit placeholders ({days}/{stock}/{price}) or
    simply write labels such as ``Validity:``, ``Stock:``, and ``Price:`` in the
    first sample row.  The first complete Validity/Stock/Price block is repeated
    once for every real plan; old copied plan rows are discarded.
    """
    if not template:
        return ''

    text = _repair_premium_emoji_markup(str(template).strip())
    lines = text.splitlines()
    tokens = ('{days}', '{stock}', '{stock_status}', '{price}', '{price_text}', '{validity}')

    # Find the first dynamic/sample plan block. This supports both placeholder
    # templates and the user's screenshot style where only {days} is dynamic and
    # Stock:/Price: are left blank for the bot to fill.
    first = None
    first_stock = None
    first_price = None
    for i, line in enumerate(lines):
        plain = re.sub(r'<[^>]+>', '', line).strip().lower()
        if first is None and (any(t in line for t in tokens) or re.search(r'\bvalidity\b', plain)):
            first = i
            continue
        if first is not None and first_stock is None and re.search(r'\bstock\b', plain):
            first_stock = i
            continue
        if first_stock is not None and first_price is None and re.search(r'\bprice\b', plain):
            first_price = i
            break

    # If there is no complete dynamic block, preserve the admin text exactly.
    if first is None or first_stock is None or first_price is None:
        return text

    block_end = first_price
    header = lines[:first]
    sample = lines[first:block_end + 1]
    footer_lines = lines[block_end + 1:]

    # Remove copied/generated plan rows after the sample. Keep the user's real
    # footer, especially CHOOSE A PLAN and any custom text after it.
    footer = []
    after_choose = False
    for line in footer_lines:
        plain = re.sub(r'<[^>]+>', '', line).strip().lower()
        if re.search(r'\b(choose a plan|select your plan)\b', plain):
            footer.append(line)
            after_choose = True
            continue
        is_plan_line = (
            re.search(r'\bvalidity\b[^:\n]*[:：]', plain)
            or re.search(r'\bstock\b[^:\n]*[:：]', plain)
            or re.search(r'\bprice\b[^:\n]*[:：]', plain)
            or (re.search(r'\b\d+\s*days(?:\s*days)?\b', plain)
                and (any(mark in plain for mark in ('📊', '❌', '├', '└', 'stock', 'price')) or after_choose))
        )
        if is_plan_line:
            continue
        footer.append(line)

    def replace_label(line, label, value):
        # Replace the value after the label's colon, preserving Premium emoji,
        # HTML formatting and all text before the colon.
        pat = re.compile(r'(\b' + re.escape(label) + r'\b[^:\n]*[:：]\s*)(.*)$', re.I)
        return pat.sub(lambda m: m.group(1) + str(value), line, count=1)

    rendered_blocks = []
    for row in live_rows:
        days = _clean_plan_days(row.get('days', ''))
        vals = {
            'days': days,
            'validity': f'{days} DAYS',
            'stock': str(row.get('stock_status', 'Out of Stock')),
            'stock_status': str(row.get('stock_status', 'Out of Stock')),
            'price': str(row.get('price_text', '')),
            'price_text': str(row.get('price_text', '')),
        }
        out = []
        for line in sample:
            line2 = replace_label(line, 'Validity', vals['validity'])
            line2 = replace_label(line2, 'Stock', vals['stock'])
            line2 = replace_label(line2, 'Price', vals['price'])
            for key, value in vals.items():
                line2 = line2.replace('{' + key + '}', value)
            out.append(line2)
        rendered_blocks.append('\n'.join(out))

    parts = []
    if header:
        parts.append('\n'.join(header).strip())
    if rendered_blocks:
        parts.append('\n\n'.join(rendered_blocks))
    if footer:
        parts.append('\n'.join(footer).strip())
    return _repair_premium_emoji_markup('\n\n'.join(x for x in parts if x).strip())


# ==================== PER-HACK PRICE LIST DESIGN ====================
# Each hack can have its own top title + 2 Premium header emojis + 1 Premium
# day/validity emoji. Live plans, prices, stock and discounts remain untouched.
HACK_PRICE_UI_PREFIX = 'hack_price_ui_'

def _hack_price_ui_key(product_name):
    return HACK_PRICE_UI_PREFIX + _ui_hash(product_name)

def get_hack_price_ui(product_name):
    raw = get_setting(_hack_price_ui_key(product_name))
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        if data.get('template'):
            return data
        if not data.get('title') or not data.get('day_emoji'):
            return None
        return data
    except Exception:
        return None

def set_hack_price_ui(product_name, title, header_emoji_1, header_emoji_2, day_emoji):
    data = {
        'title': str(title).strip(),
        'header_emoji_1': str(header_emoji_1).strip(),
        'header_emoji_2': str(header_emoji_2).strip(),
        'day_emoji': str(day_emoji).strip(),
    }
    set_setting(_hack_price_ui_key(product_name), json.dumps(data, ensure_ascii=False))


def set_hack_price_ui_template(product_name, template):
    """Save the admin's per-hack price-list design exactly as sent.

    The template is presentation-only. At render time the live DB plans, prices,
    stock state and discounts are injected into the Validity/Stock/Price rows.
    """
    data = get_hack_price_ui(product_name) or {}
    data['template'] = str(template or '').strip()
    # Keep legacy fields when present; they are no longer required for new designs.
    set_setting(_hack_price_ui_key(product_name), json.dumps(data, ensure_ascii=False))


def _clean_plan_days(raw_days):
    """Return only the numeric/day value, preventing outputs like '1DAYS DAYS'."""
    value = str(raw_days or '').strip()
    value = re.sub(r'\s*DAYS?\s*$', '', value, flags=re.I).strip()
    return value


def _render_hack_price_ui_template(template, pricing_rows, product_name):
    """Render one clean per-hack Premium price-list design.

    The admin may send a message copied from an older price list.  Only the
    FIRST Validity/Stock/Price sample is used as the reusable block.  Any
    additional Validity/Stock/Price rows in the saved template are discarded,
    so live plans can never appear twice.
    """
    if not template:
        return None

    template = _repair_premium_emoji_markup(template)
    lines = str(template).splitlines()
    first_validity = first_stock = first_price = None

    # Locate the first complete sample block.
    for i, line in enumerate(lines):
        plain = re.sub(r'<[^>]+>', '', line).strip().lower()
        if first_validity is None and re.search(r'\bvalidity\b', plain):
            first_validity = i
            continue
        if first_validity is not None and first_stock is None and re.search(r'\bstock\b', plain):
            first_stock = i
            continue
        if first_stock is not None and first_price is None and re.search(r'\bprice\b', plain):
            first_price = i
            break

    if first_validity is None or first_stock is None or first_price is None:
        return None

    block_end = max(first_validity, first_stock, first_price)
    header = lines[:first_validity]
    block = lines[first_validity:block_end + 1]
    footer = lines[block_end + 1:]

    # IMPORTANT: if the admin copied an old full price list, its remaining
    # plan rows may use either the explicit Validity/Stock/Price labels or an
    # older compact generated layout such as "❌ 📊 1 DAYS" followed by Stock
    # and Price lines. Remove those legacy generated rows so the live rows are
    # rendered exactly once. Keep the user's real footer (especially CHOOSE A PLAN).
    cleaned_footer = []
    after_choose = False
    for line in footer:
        plain = re.sub(r'<[^>]+>', '', line).strip().lower()

        if re.search(r'\b(choose a plan|select your plan)\b', plain):
            cleaned_footer.append(line)
            after_choose = True
            continue

        is_labeled_plan_line = (
            re.search(r'\bvalidity\b[^:\n]*[:：]', plain) or
            re.search(r'\bstock\b[^:\n]*[:：]', plain) or
            re.search(r'\bprice\b[^:\n]*[:：]', plain)
        )

        # Legacy compact plan rows have no "Validity:" label. They usually
        # contain a day count plus DAYS, often with 📊/❌/├/└, followed by
        # Stock/Price lines. Treat those as generated rows too.
        is_compact_plan_line = (
            re.search(r'\b\d+\s*days(?:\s*days)?\b', plain) and
            (any(mark in plain for mark in ('📊', '❌', '├', '└', 'stock', 'price')) or after_choose)
        )

        if is_labeled_plan_line or is_compact_plan_line:
            continue

        # Once CHOOSE A PLAN has been followed by a legacy generated block,
        # discard only blank lines belonging to that block; preserve unrelated
        # custom footer text if the admin added any.
        cleaned_footer.append(line)
    footer = cleaned_footer

    # Do not allow the old generated "STOCK & PRICING" section to be appended
    # when it was copied into the admin template. The admin's own heading stays.
    # This only removes the exact legacy heading text, not arbitrary custom text.
    header = [
        line for line in header
        if re.sub(r'<[^>]+>', '', line).strip().lower()
        not in ('stock & pricing :', 'stock & pricing:', 'stock & pricing')
    ]

    def replace_line_value(line, label, value):
        # Replace everything after the label's colon. Premium <tg-emoji>
        # wrappers before the label remain untouched.
        pat = re.compile(
            r'(\b' + re.escape(label) + r'\b[^:\n]*[:：]\s*)(.*)$',
            re.I
        )
        return pat.sub(lambda m: m.group(1) + str(value), line, count=1)

    rendered_blocks = []
    for row in pricing_rows:
        days = _clean_plan_days(row.get('days', ''))
        validity = f'{days} DAYS'
        vals = {
            'Validity': validity,
            'Stock': str(row.get('stock_status', 'Out of Stock')),
            'Price': str(row.get('price_text', '')),
        }

        out_lines = []
        for line in block:
            line2 = replace_line_value(line, 'Validity', vals['Validity'])
            line2 = replace_line_value(line2, 'Stock', vals['Stock'])
            line2 = replace_line_value(line2, 'Price', vals['Price'])

            # Support placeholders without adding a second DAYS suffix.
            line2 = (line2
                     .replace('{days}', days)
                     .replace('{validity}', vals['Validity'])
                     .replace('{stock}', vals['Stock'])
                     .replace('{price}', vals['Price']))
            out_lines.append(line2)

        rendered_blocks.append('\n'.join(out_lines))

    if not rendered_blocks:
        return '\n'.join(header + footer).strip()

    # Exactly ONE generated block per real DB plan. No old price-list rows are
    # appended, so 1/3/7/15/30 will never become 1/3/7/15/30 + 3/7/15/30.
    rendered = '\n'.join(header + ['\n\n'.join(rendered_blocks)] + footer).strip()
    return _repair_premium_emoji_markup(rendered)


def _premium_emoji_html(emoji_id, fallback='✨'):
    """Build Telegram HTML for a Premium custom emoji."""
    if not emoji_id:
        return html.escape(str(fallback or '✨'), quote=False)
    safe_id = html.escape(str(emoji_id).strip(), quote=True)
    safe_fallback = html.escape(str(fallback or '✨'), quote=False)
    return f'<tg-emoji emoji-id="{safe_id}">{safe_fallback}</tg-emoji>'


def _repair_premium_emoji_markup(text):
    """Repair escaped/canonicalize Premium <tg-emoji> wrappers only."""
    if not text:
        return text
    value = str(text)
    value = re.sub(
        r'&lt;(/?tg-emoji\b[^&]*)&gt;',
        lambda m: '<' + html.unescape(m.group(1)) + '>',
        value,
        flags=re.I,
    )

    def normalize_open(match):
        emoji_id = match.group(1).strip()
        return f'<tg-emoji emoji-id="{html.escape(emoji_id, quote=True)}">'

    value = re.sub(
        r'<tg-emoji\s+emoji-id\s*=\s*["\']([^"\']+)["\']\s*>',
        normalize_open,
        value,
        flags=re.I,
    )
    return value


def _premium_emoji_ids_from_template(template, unique=True):
    """Return Premium custom-emoji IDs from a saved template.

    ``unique=True`` is kept for legacy callers. Order History persistence uses
    ``unique=False`` because exact occurrence order is meaningful and duplicate
    IDs at different visual positions must not be collapsed.
    """
    if not template:
        return []
    ids = []
    for match in re.finditer(
        r'<tg-emoji\s+emoji-id\s*=\s*["\']([^"\']+)["\']\s*>',
        str(template),
        flags=re.I,
    ):
        emoji_id = str(match.group(1)).strip()
        if not emoji_id:
            continue
        if unique:
            if emoji_id not in ids:
                ids.append(emoji_id)
        else:
            ids.append(emoji_id)
    return ids


def _get_product_button_keys():
    return [f"hack:{product_name}" for product_name in get_unique_products()]


def _get_price_button_keys():
    keys = []
    for product_name in get_unique_products():
        for plan in get_product_plans(product_name):
            keys.append(f"price:{product_name}:{plan[0]}")
    return keys


def set_bulk_button_emoji(button_keys, emoji_id):
    """Apply one Premium custom emoji to every button in a dynamic group."""
    clean_id = str(emoji_id).strip()
    for key in button_keys:
        set_button_emoji(key, clean_id)


def get_bulk_emoji_status(button_keys):
    values = [get_button_emoji(key) for key in button_keys]
    values = [v for v in values if v]
    if not values:
        return None
    if len(values) == len(button_keys) and len(set(values)) == 1:
        return values[0]
    return "mixed"


# ==================== UI CUSTOMIZATION HELPERS ====================
# Telegram Bot API supports button styles: danger=red, primary=blue, success=green.
# Premium custom-emoji icons on buttons require a recent pyTelegramBotAPI.
BUTTON_STYLE_MAP = {
    "red": "danger",
    "blue": "primary",
    "green": "success",
    "default": None,
}

def _ui_hash(value):
    return hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:20]

def _style_setting_key(button_key):
    return f"button_style_{_ui_hash(button_key)}"

def _emoji_setting_key(button_key):
    return f"button_emoji_{_ui_hash(button_key)}"

def get_button_style(button_key, default=None):
    saved = get_setting(_style_setting_key(button_key))
    if saved in BUTTON_STYLE_MAP:
        return BUTTON_STYLE_MAP[saved]
    return default

def set_button_style(button_key, color):
    if color not in BUTTON_STYLE_MAP:
        color = "default"
    set_setting(_style_setting_key(button_key), color)

def get_button_emoji(button_key, default=None):
    return get_setting(_emoji_setting_key(button_key)) or default

def set_button_emoji(button_key, emoji_id):
    set_setting(_emoji_setting_key(button_key), str(emoji_id).strip())

def _strip_leading_normal_emoji(text):
    """Remove normal leading emoji when a Premium custom emoji icon is active.

    Telegram renders icon_custom_emoji_id to the left of button text. If the old
    text still starts with a normal emoji, users see two icons. This helper removes
    only leading emoji/variation-selector/ZWJ characters and keeps the actual label.
    """
    if not text:
        return text
    value = str(text).strip()
    # Remove common Unicode emoji blocks at the beginning, including emoji joined
    # with variation selectors, skin-tone modifiers and ZWJ sequences.
    emoji_chars = []
    for ch in value:
        cp = ord(ch)
        cat = __import__('unicodedata').category(ch)
        is_emoji = (
            0x1F000 <= cp <= 0x1FAFF or
            0x2600 <= cp <= 0x27BF or
            0x2300 <= cp <= 0x23FF or
            0x2B00 <= cp <= 0x2BFF or
            0x2190 <= cp <= 0x21FF or
            0xFE0F <= cp <= 0xFE0F or
            0x200D <= cp <= 0x200D or
            cat in ('So', 'Sk')
        )
        if is_emoji:
            emoji_chars.append(ch)
            continue
        if ch in ('\ufe0e', '\ufe0f', '\u200d'):
            emoji_chars.append(ch)
            continue
        break
    if emoji_chars:
        value = value[len(''.join(emoji_chars)):].lstrip()
    return value


def make_ui_button(text, callback_data=None, url=None, button_key=None,
                   default_color="default", default_emoji_id=None):
    """Create an InlineKeyboardButton with saved color/custom-emoji settings.
    Falls back to a normal button if an old library version rejects the new fields.
    When a Premium custom emoji is configured, any old leading normal emoji in the
    text is removed so Telegram shows exactly one icon.
    """
    style = get_button_style(button_key, BUTTON_STYLE_MAP.get(default_color)) if button_key else BUTTON_STYLE_MAP.get(default_color)
    emoji_id = get_button_emoji(button_key, default_emoji_id) if button_key else default_emoji_id
    display_text = _strip_leading_normal_emoji(text) if emoji_id else text
    kwargs = {}
    if callback_data is not None:
        kwargs["callback_data"] = callback_data
    if url is not None:
        kwargs["url"] = url
    if style:
        kwargs["style"] = style
    if emoji_id:
        kwargs["icon_custom_emoji_id"] = str(emoji_id)
    try:
        return types.InlineKeyboardButton(text=display_text, **kwargs)
    except TypeError:
        # Compatibility with old pyTelegramBotAPI versions.
        fallback_kwargs = {}
        if callback_data is not None:
            fallback_kwargs["callback_data"] = callback_data
        if url is not None:
            fallback_kwargs["url"] = url
        btn = types.InlineKeyboardButton(text=display_text, **fallback_kwargs)
        if style:
            try:
                btn.style = style
            except Exception:
                pass
        if emoji_id:
            try:
                btn.icon_custom_emoji_id = str(emoji_id)
            except Exception:
                pass
        return btn



def _repair_telegram_html_markup(text):
    """Repair unbalanced Telegram HTML while preserving Premium custom emojis."""
    if not text:
        return text

    value = str(text)
    allowed = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "code", "pre", "blockquote", "tg-emoji", "a"}
    tag_re = re.compile(r"</?([A-Za-z][A-Za-z0-9-]*)(?:\s+[^<>]*?)?/?>", re.S)
    out = []
    stack = []
    pos = 0

    for m in tag_re.finditer(value):
        out.append(value[pos:m.start()])
        raw = m.group(0)
        name = m.group(1).lower()
        closing = raw.startswith("</")
        self_closing = raw.endswith("/>")

        if name not in allowed:
            pos = m.end()
            continue
        if self_closing:
            out.append(raw)
            pos = m.end()
            continue

        if closing:
            if name not in stack:
                pos = m.end()
                continue
            while stack and stack[-1] != name:
                out.append(f"</{stack.pop()}>")
            if stack and stack[-1] == name:
                out.append(raw)
                stack.pop()
            pos = m.end()
            continue

        out.append(raw)
        stack.append(name)
        pos = m.end()

    out.append(value[pos:])
    while stack:
        out.append(f"</{stack.pop()}>")
    return "".join(out)


def _send_payment_success_safely(chat_id, text, reply_markup=None):
    """Send payment success without allowing malformed custom HTML to break checkout."""
    try:
        return bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=reply_markup)
    except Exception as first_error:
        repaired = _repair_telegram_html_markup(_repair_premium_emoji_markup(str(text)))
        try:
            return bot.send_message(chat_id, repaired, parse_mode="HTML", reply_markup=reply_markup)
        except Exception:
            plain = re.sub(r"<tg-emoji\b[^>]*>(.*?)</tg-emoji>", lambda m: m.group(1), str(repaired), flags=re.I | re.S)
            plain = re.sub(r"<[^>]+>", "", plain)
            plain = html.unescape(plain)
            try:
                return bot.send_message(chat_id, plain, reply_markup=reply_markup)
            except Exception:
                raise first_error

def _message_html_text(message):
    """Return Telegram message text as HTML while preserving every custom emoji.

    Telegram sends Premium/custom emoji as ``custom_emoji`` MessageEntity
    objects. Some pyTelegramBotAPI versions serialize them correctly as
    ``<tg-emoji>`` while others return only their visible Unicode fallback.
    The old implementation repaired missing entities by ``str.find()`` on the
    visible emoji, which is unsafe when the same fallback emoji appears more
    than once: the wrong Premium ID could be attached to the wrong position.

    This version maps each Telegram UTF-16 entity offset to the corresponding
    visible character range inside the generated HTML and inserts the exact
    ``<tg-emoji>`` wrapper at that position. Thus Premium IDs and their visual
    positions are preserved exactly as the admin sent them.
    """
    source_text = getattr(message, "text", None) or ""
    entities = list(getattr(message, "entities", None) or [])

    html_text = None
    try:
        value = getattr(message, "html_text", None)
        if value:
            html_text = value
    except Exception:
        pass

    if not html_text:
        try:
            from telebot import formatting
            html_text = formatting.apply_html_entities(source_text, entities)
        except Exception:
            html_text = html.escape(source_text)

    html_text = str(html_text)

    custom_entities = [
        ent for ent in entities
        if getattr(ent, "type", None) == "custom_emoji"
        and getattr(ent, "custom_emoji_id", None)
    ]
    if not custom_entities:
        return _repair_premium_emoji_markup(html_text)

    def utf16_to_char_index(value, offset):
        """Convert a Telegram UTF-16 code-unit offset to a Python char index."""
        raw = value.encode("utf-16-le")
        offset = max(0, min(int(offset or 0), len(raw) // 2))
        return len(raw[:offset * 2].decode("utf-16-le", errors="ignore"))

    def html_visible_map(value):
        """Map visible-character indexes to raw HTML character spans.

        HTML tags are ignored. HTML entities such as ``&amp;`` count as their
        decoded visible character(s), so the mapping still lines up with the
        original Telegram message text.
        """
        mapping = []
        i = 0
        n = len(value)
        while i < n:
            if value[i] == "<":
                close = value.find(">", i + 1)
                if close < 0:
                    close = n - 1
                i = close + 1
                continue

            if value[i] == "&":
                semi = value.find(";", i + 1)
                if semi >= 0 and semi - i <= 32:
                    token = value[i:semi + 1]
                    decoded = html.unescape(token)
                    if decoded != token:
                        for ch in decoded:
                            mapping.append((i, semi + 1, ch))
                        i = semi + 1
                        continue

            mapping.append((i, i + 1, value[i]))
            i += 1
        return mapping

    visible_map = html_visible_map(html_text)

    # Count already serialized IDs so repeated use of the same Premium emoji ID
    # is handled by occurrence, not by a simple "ID exists" test.
    existing_counts = {}
    for m in re.finditer(r'<tg-emoji\s+emoji-id\s*=\s*["\']([^"\']+)["\']\s*>',
                         html_text, flags=re.I):
        eid = str(m.group(1)).strip()
        existing_counts[eid] = existing_counts.get(eid, 0) + 1
    seen_entities = {}

    insertions = []
    for ent in sorted(custom_entities, key=lambda e: int(getattr(e, "offset", 0) or 0)):
        emoji_id = str(getattr(ent, "custom_emoji_id", "") or "").strip()
        if not emoji_id:
            continue

        seen_entities[emoji_id] = seen_entities.get(emoji_id, 0) + 1
        # If html_text already contains this occurrence, leave it untouched.
        if seen_entities[emoji_id] <= existing_counts.get(emoji_id, 0):
            continue

        source_start = utf16_to_char_index(source_text, getattr(ent, "offset", 0))
        source_end = utf16_to_char_index(
            source_text,
            int(getattr(ent, "offset", 0) or 0) + int(getattr(ent, "length", 0) or 0),
        )
        if source_end <= source_start:
            continue

        # The HTML conversion must preserve visible source text. Use the source
        # character indexes directly rather than searching for the emoji string,
        # so duplicate visible emoji can never steal each other's Premium ID.
        if source_end > len(visible_map):
            continue

        raw_start = visible_map[source_start][0]
        raw_end = visible_map[source_end - 1][1]

        visible = source_text[source_start:source_end]
        tag = (
            f'<tg-emoji emoji-id="{html.escape(emoji_id, quote=True)}">'
            f'{html.escape(visible, quote=False)}</tg-emoji>'
        )
        insertions.append((raw_start, raw_end, tag))

    # Insert from right to left so the raw spans from the HTML mapping never
    # shift under us. Overlapping custom-emoji entities are invalid in Telegram,
    # but sorting defensively keeps this safe.
    for raw_start, raw_end, tag in sorted(insertions, key=lambda x: x[0], reverse=True):
        html_text = html_text[:raw_start] + tag + html_text[raw_end:]

    return _repair_premium_emoji_markup(html_text)


# ==================== QR PAYMENT CAPTION CUSTOM TEXT ====================
# Admin-editable text shown directly below the QR image. This is presentation-only:
# product/plan/price/order-id/date remain live per purchase and are never stored in
# this shared template. Premium Telegram custom emojis are preserved via
# _message_html_text() + _repair_premium_emoji_markup().
QR_PAYMENT_TEXT_KEY = "qr_payment_text"
QR_PAYMENT_TEXT_DEFAULT = (
    "🇮🇳 <b>UPI SCAN & PAY — IN BOT</b>\n"
    "────────────────────────"
)

def get_qr_payment_text():
    return get_setting(QR_PAYMENT_TEXT_KEY) or QR_PAYMENT_TEXT_DEFAULT

def set_qr_payment_text(template):
    cleaned = _repair_premium_emoji_markup(str(template or '').strip())
    set_setting(QR_PAYMENT_TEXT_KEY, cleaned)


def _has_custom_qr_payment_text():
    """True only after the admin has saved a QR-below custom template."""
    saved = get_setting(QR_PAYMENT_TEXT_KEY)
    return bool(str(saved or '').strip())


def _render_qr_payment_text(template, prod_name, prod_days, amount, order_id,
                            purchase_date, device_id=None):
    """Render the admin QR template with live per-purchase values.

    Supports explicit placeholders and ordinary labelled lines such as
    "Amount:" and "Order ID:". Premium custom-emoji markup is preserved.
    """
    if not template:
        return ''

    values = {
        "hack": html.escape(str(prod_name), quote=False),
        "product_name": html.escape(str(prod_name), quote=False),
        "plan": html.escape(str(prod_days), quote=False),
        "amount": f"₹{float(amount):.2f} INR",
        "order_id": html.escape(str(order_id), quote=False),
        "date": html.escape(str(purchase_date), quote=False),
        "purchase_date": html.escape(str(purchase_date), quote=False),
        "device_id": html.escape(str(device_id), quote=False) if device_id else "",
    }

    rendered = _repair_premium_emoji_markup(str(template).strip())
    rendered = _safe_format_custom_text(rendered, **values)

    # Also update normal label rows even when the admin did not use placeholders.
    rendered = _inject_labeled_user_values(
        rendered,
        {
            "product_name": values["product_name"],
            "plan": values["plan"],
            "amount": values["amount"],
            "order_id": values["order_id"],
            "date": values["date"],
            "device_id": values["device_id"],
        }
    )

    return _repair_premium_emoji_markup(rendered).strip()



# ==================== WALLET/UPI PAYMENT SUCCESS PREMIUM EMOJI TEMPLATE ====================
# Presentation-only template for successful product delivery. The admin can send the
# existing success message with Premium custom emojis placed exactly where desired.
# The saved design is rendered with LIVE user/order/product/plan/method/amount/key values.
WALLET_PAYMENT_EMOJI_TEMPLATE_KEY = "wallet_payment_emoji_template"
UPI_PAYMENT_EMOJI_TEMPLATE_KEY = "upi_payment_emoji_template"

# Separate Add Balance/Wallet Top-Up success template. This is intentionally
# independent from the product-checkout Wallet Payment template above.
WALLET_TOPUP_SUCCESS_EMOJI_TEMPLATE_KEY = "wallet_topup_success_emoji_template"

DEFAULT_WALLET_TOPUP_SUCCESS_EMOJI_TEMPLATE = (
    "💰 <b>PAYMENT SUCCESSFUL</b> 💰\n"
    "<i>Wallet Balance Added Successfully!</i>\n\n"
    "🧾 <b>TOP-UP DETAILS</b>\n"
    "├── 👤 <b>Username:</b> {name}\n"
    "├── 🆔 <b>Telegram ID:</b> <code>{user_id}</code>\n"
    "├── 🧾 <b>Order ID:</b> <code>{order_id}</code>\n"
    "├── 💵 <b>Amount Added:</b> {amount}\n"
    "├── 🏷️ <b>UTR:</b> <code>{utr}</code>\n"
    "└── 💼 <b>Current Balance:</b> {current_balance}\n\n"
    "✨ <i>Your wallet has been updated instantly.</i>"
)

DEFAULT_WALLET_PAYMENT_EMOJI_TEMPLATE = (
    "💰 <b>{payment_title}</b> 💰\n"
    "<i>Instant Key Delivery!</i>\n\n"
    "📋 <b>ORDER DETAILS</b>\n"
    "├── 👤 <b>User ID:</b> <code>{user_id}</code>\n"
    "├── 🆔 <b>Order ID:</b> <code>{order_id}</code>\n"
    "├── 🛒 <b>Product ID:</b> <code>{product_id}</code>\n"
    "├── 🎮 <b>Product:</b> {product_name}\n"
    "├── ⏱️ <b>Plan:</b> {plan}\n"
    "├── 💳 <b>Method:</b> {method}\n"
    "{device_line}"
    "└── 💵 <b>Paid:</b> {amount}\n\n"
    "🔑 <b>YOUR KEY:</b>\n"
    "<code>{key}</code>\n\n"
    "💡 <i>Tap the key above to copy instantly.</i>"
)

# Separate UPI design. It uses the exact same live fields as Wallet, but has
# its own admin-saved Premium Emoji/Text template so the two designs never
# overwrite each other.
DEFAULT_UPI_PAYMENT_EMOJI_TEMPLATE = (
    "🎉 <b>{payment_title}</b> 🎉\n"
    "<i>Instant Key Delivery!</i>\n\n"
    "📋 <b>ORDER DETAILS</b>\n"
    "├── 👤 <b>User ID:</b> <code>{user_id}</code>\n"
    "├── 🆔 <b>Order ID:</b> <code>{order_id}</code>\n"
    "├── 🛒 <b>Product ID:</b> <code>{product_id}</code>\n"
    "├── 🎮 <b>Product:</b> {product_name}\n"
    "├── ⏱️ <b>Plan:</b> {plan}\n"
    "├── 💳 <b>Method:</b> {method}\n"
    "{device_line}"
    "└── 💵 <b>Paid:</b> {amount}\n\n"
    "🔑 <b>YOUR KEY:</b>\n"
    "<code>{key}</code>\n\n"
    "💡 <i>Tap the key above to copy instantly.</i>"
)

def get_wallet_payment_emoji_template():
    return get_setting(WALLET_PAYMENT_EMOJI_TEMPLATE_KEY) or ""

def set_wallet_payment_emoji_template(template):
    cleaned = _repair_premium_emoji_markup(str(template or "").strip())
    set_setting(WALLET_PAYMENT_EMOJI_TEMPLATE_KEY, cleaned)

def get_upi_payment_emoji_template():
    return get_setting(UPI_PAYMENT_EMOJI_TEMPLATE_KEY) or DEFAULT_UPI_PAYMENT_EMOJI_TEMPLATE

def set_upi_payment_emoji_template(template):
    cleaned = _repair_premium_emoji_markup(str(template or "").strip())
    set_setting(UPI_PAYMENT_EMOJI_TEMPLATE_KEY, cleaned)


def get_wallet_topup_success_emoji_template():
    return (
        get_setting(WALLET_TOPUP_SUCCESS_EMOJI_TEMPLATE_KEY)
        or DEFAULT_WALLET_TOPUP_SUCCESS_EMOJI_TEMPLATE
    )


def set_wallet_topup_success_emoji_template(template):
    cleaned = _repair_premium_emoji_markup(str(template or "").strip())
    set_setting(WALLET_TOPUP_SUCCESS_EMOJI_TEMPLATE_KEY, cleaned)


def _render_wallet_topup_success_emoji_template(
    template, user_id, user_name, order_id, amount, utr, current_balance
):
    """Render the Add Balance success design with live transaction values."""
    if not template:
        template = DEFAULT_WALLET_TOPUP_SUCCESS_EMOJI_TEMPLATE

    try:
        amount_value = float(amount)
    except (TypeError, ValueError):
        amount_value = 0.0

    try:
        balance_value = float(current_balance)
    except (TypeError, ValueError):
        balance_value = 0.0

    live_username = _get_live_telegram_username(user_id)
    values = {
        "name": html.escape(str(user_name or "User"), quote=False),
        "first_name": html.escape(str(user_name or "User"), quote=False),
        "user": html.escape(str(user_name or "User"), quote=False),
        "username": html.escape(str(live_username or ""), quote=False),
        "username_at": html.escape(
            f"@{live_username}" if live_username else "", quote=False
        ),
        "user_id": str(user_id),
        "telegram_id": str(user_id),
        "amount": f"₹{amount_value:.2f} INR",
        "add_amount": f"₹{amount_value:.2f} INR",
        "topup_amount": f"₹{amount_value:.2f} INR",
        "order_id": html.escape(str(order_id), quote=False),
        "utr": html.escape(str(utr or "N/A"), quote=False),
        "balance": f"{balance_value:.2f}",
        "current_balance": f"₹{balance_value:.2f} INR",
        "date": html.escape(
            datetime.datetime.now().strftime("%A, %d %b %Y %H:%M:%S"),
            quote=False,
        ),
    }

    rendered = _repair_premium_emoji_markup(str(template).strip())
    rendered = _safe_format_custom_text(rendered, **values)

    # Replace labelled fields too, so an admin can paste the screenshot/sample
    # with old values and the bot will still inject the current transaction.
    rendered = _inject_labeled_user_values(
        rendered,
        {
            "name": values["name"],
            "username": values["username"],
            "user_id": values["user_id"],
            "telegram_id": values["telegram_id"],
            "amount": values["amount"],
            "add_amount": values["add_amount"],
            "topup_amount": values["topup_amount"],
            "order_id": values["order_id"],
            "utr": values["utr"],
            "balance": values["balance"],
            "current_balance": values["current_balance"],
            "date": values["date"],
        },
    )

    # Extra common Add Balance labels; preserve the admin's surrounding design.
    rendered = re.sub(
        r'(?im)^([^\n]*\b(?:Add\s+Amount|Amount\s+Added|Amount\s+Adding|Top[- ]?up\s+Amount|Amount)\b[^:\n]*:\s*)[^\n]*$',
        lambda m: m.group(1) + values["amount"],
        rendered,
    )
    rendered = re.sub(
        r'(?im)^([^\n]*\b(?:Current\s+Balance|Wallet\s+Balance|Your\s+Balance|Balance)\b[^:\n]*:\s*)[^\n]*$',
        lambda m: m.group(1) + values["current_balance"],
        rendered,
    )
    rendered = re.sub(
        r'(?im)^([^\n]*\b(?:UTR|Transaction\s+UTR)\b[^:\n]*:\s*)[^\n]*$',
        lambda m: m.group(1) + f'<code>{values["utr"]}</code>',
        rendered,
    )
    rendered = re.sub(
        r'(?im)^([^\n]*\bOrder\s+ID\b[^:\n]*:\s*)[^\n]*$',
        lambda m: m.group(1) + f'<code>{values["order_id"]}</code>',
        rendered,
    )
    rendered = re.sub(
        r'(?im)^([^\n]*\b(?:Telegram\s+ID|User\s+ID)\b[^:\n]*:\s*)[^\n]*$',
        lambda m: m.group(1) + f'<code>{values["user_id"]}</code>',
        rendered,
    )

    return _repair_telegram_html_markup(
        _repair_premium_emoji_markup(rendered).strip()
    )


def _render_wallet_payment_emoji_template(
    template, user_id, order_id, product_id, product_name, plan,
    amount, key_val, pay_type="wallet", device_id=None
):
    """Render the saved payment-success design while keeping every transaction field live."""
    if not template:
        template = DEFAULT_WALLET_PAYMENT_EMOJI_TEMPLATE

    method = "Wallet Method" if str(pay_type).lower() == "wallet" else "UPI Method"
    title = "WALLET PAYMENT SUCCESSFUL" if str(pay_type).lower() == "wallet" else "PAYMENT SUCCESSFUL"
    purchase_date = datetime.datetime.now().strftime("%A, %d %b %Y %H:%M:%S")
    device_line = (
        f"├── 📱 <b>Device ID:</b> <code>{html.escape(str(device_id), quote=False)}</code>\n"
        if device_id else ""
    )

    values = {
        "payment_title": title,
        "user_id": str(user_id),
        "telegram_id": str(user_id),
        "order_id": html.escape(str(order_id), quote=False),
        "product_id": html.escape(str(product_id), quote=False),
        "product_name": html.escape(str(product_name), quote=False),
        "product": html.escape(str(product_name), quote=False),
        "hack": html.escape(str(product_name), quote=False),
        "plan": html.escape(str(plan), quote=False),
        "method": html.escape(method, quote=False),
        "amount": f"₹{float(amount):.2f} INR",
        "paid": f"₹{float(amount):.2f} INR",
        "key": html.escape(str(key_val), quote=False),
        "date": html.escape(purchase_date, quote=False),
        "purchase_date": html.escape(purchase_date, quote=False),
        "device_id": html.escape(str(device_id), quote=False) if device_id else "",
        "device_line": device_line,
    }

    rendered = _repair_premium_emoji_markup(str(template).strip())
    rendered = _safe_format_custom_text(rendered, **values)

    # Keep the transaction fields live even when the admin sent a sample message
    # containing old values instead of placeholders.
    rendered = _inject_labeled_user_values(
        rendered,
        {
            "user_id": str(user_id),
            "telegram_id": str(user_id),
            "product_id": str(product_id),
            "product_name": values["product_name"],
            "plan": values["plan"],
            "method": method,
            "amount": values["amount"],
            "paid": values["paid"],
            "order_id": values["order_id"],
            "key": values["key"],
            "date": values["date"],
            "device_id": values["device_id"],
        }
    )

    # If the same saved visual design is used for UPI, do not leave a misleading
    # "WALLET PAYMENT SUCCESSFUL" heading.
    if str(pay_type).lower() != "wallet":
        rendered = re.sub(
            r"WALLET PAYMENT SUCCESSFUL",
            "PAYMENT SUCCESSFUL",
            rendered,
            flags=re.I,
        )

    return _repair_telegram_html_markup(_repair_premium_emoji_markup(rendered).strip())

def get_custom_text(key, default_val):
    return get_setting(f"custom_text_{key}") or default_val

def get_custom_btn(key, default_val):
    return get_setting(f"custom_btn_{key}") or default_val

def _safe_format_custom_text(template, **values):
    """Replace known placeholders without using str.format().

    This keeps old custom texts safe while allowing live per-user values such as
    name, phone number, Telegram ID and live pricing to be inserted automatically.
    Unknown placeholders are intentionally left untouched instead of crashing.
    """
    import re
    if not template:
        return ""

    aliases = {
        "user": "name",
        # Keep Username separate from display name. This prevents an admin's
        # username from becoming part of a shared custom-text template.
        "username": "username",
        "telegram_username": "username",
        "telegram_id": "user_id",
        "uid": "user_id",
        "number": "phone",
        "phone_number": "phone",
        "hack_name": "hack",
        "product": "product_name",
        "price_list": "pricing_info",
        "prices": "pricing_info",
    }

    def repl(match):
        key = match.group(1)
        lookup = aliases.get(key, key)
        return str(values.get(lookup, match.group(0)))

    return re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", repl, template)

def _get_live_telegram_username(user_id, fallback=None):
    """Return the current Telegram @username for this user.

    Usernames are intentionally fetched live and are never stored inside a
    shared custom-text template. If Telegram does not expose a username, an
    empty value is returned.
    """
    candidate = str(fallback or '').strip().lstrip('@')
    if candidate:
        return candidate
    try:
        chat = bot.get_chat(int(user_id))
        candidate = str(getattr(chat, 'username', '') or '').strip().lstrip('@')
        return candidate
    except Exception:
        return ''


def _get_user_template_values(user_id, first_name=None, phone_number=None, username=None):
    """Build one consistent LIVE placeholder dictionary for user-facing text.

    Only presentation text/emojis are shared in settings. Account-specific
    fields (name, username, Telegram ID, balance, etc.) are resolved every time
    the message is rendered, so one user's values can never leak into another
    user's message.
    """
    user = get_user(user_id) if user_id else None
    name = first_name or (user[1] if user and len(user) > 1 else "User") or "User"
    phone = phone_number if phone_number is not None else (user[2] if user and len(user) > 2 else "")
    phone = phone or "N/A"
    country = user[3] if user and len(user) > 3 else "IN"
    balance = user[4] if user and len(user) > 4 else 0.0
    ref_balance = user[5] if user and len(user) > 5 else 0.0
    orders = user[6] if user and len(user) > 6 else 0
    lifetime = user[7] if user and len(user) > 7 else 0.0
    deposited = user[8] if user and len(user) > 8 else 0.0
    joined = user[9] if user and len(user) > 9 else "N/A"
    live_username = _get_live_telegram_username(user_id, username)
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return {
        "name": html.escape(str(name), quote=False),
        "first_name": html.escape(str(name), quote=False),
        "username": html.escape(str(live_username), quote=False),
        "username_at": html.escape(f"@{live_username}" if live_username else "", quote=False),
        "user_id": str(user_id),
        "telegram_id": str(user_id),
        "phone": html.escape(str(phone), quote=False),
        "country": html.escape(str(country or "IN"), quote=False),
        "balance": f"{float(balance):.2f}",
        "ref_balance": f"{float(ref_balance):.2f}",
        "orders": str(int(orders or 0)),
        "lifetime": f"{float(lifetime):.2f}",
        "deposited": f"{float(deposited):.2f}",
        "joined": html.escape(str(joined or "N/A"), quote=False),
        "date": now,
    }


def _replace_live_greeting_name(text, name):
    """Replace hard-coded names in common greeting lines with the CURRENT user's name.

    Admin text templates are presentation-only, so an admin may save a previously
    rendered message such as ``Welcome, RG!``. Placeholder/label replacement cannot
    see that name because it is not a labeled field. This helper updates only
    greeting phrases and leaves the rest of the design/text untouched.
    """
    if not text:
        return text

    live_name = html.escape(str(name or "User"), quote=False)
    greeting_re = re.compile(
        r'(?i)(\b(?:welcome(?:\s+back)?|hello)\s*,\s*)'
        r'([^<>\n!]+?)(\s*!?)'
        r'(?=(?:<[^>]+>)*\s*(?:\n|$))'
    )

    def repl(match):
        old_name = match.group(2).strip()
        if not old_name:
            return match.group(0)
        return match.group(1) + live_name + match.group(3)

    return greeting_re.sub(repl, str(text))


def _inject_labeled_user_values(text, values):
    """Replace LIVE values after known labels while preserving the admin's design.

    This is the important anti-leak layer for the text editor: if an admin
    copies a previously rendered message containing e.g. ``Balance: ₹504`` or
    another user's Telegram ID and then saves it as a template, the old value is
    replaced at render time with the current user's live value. Premium
    <tg-emoji> markup and the rest of the line remain untouched.
    """
    if not text:
        return text

    import re

    def replace_label_value(value_text, labels, value, wrap_code=False, allow_empty=False):
        if value is None:
            return value_text
        value = str(value)
        if not allow_empty and value == "":
            return value_text
        label_alt = "|".join(re.escape(x) for x in labels)
        # Replace everything after the matching label's colon on that line.
        # This works whether the label is plain text or wrapped in <b> tags.
        pattern = re.compile(
            r'(?im)^([^\n]*?\b(?:' + label_alt + r')\b[^\n:]*:\s*)([^\n]*)$'
        )
        replacement_value = f'<code>{value}</code>' if wrap_code else value

        def _line_repl(match):
            old_value = match.group(2)
            # Preserve trailing HTML closing tags such as </b> / </i> that were
            # part of the admin's visual design. Only the actual old value is
            # replaced.
            suffix_match = re.search(r'(\s*(?:</[^>]+>\s*)+)$', old_value)
            suffix = suffix_match.group(1) if suffix_match else ''
            return match.group(1) + replacement_value + suffix

        return pattern.sub(_line_repl, value_text)

    # Identity fields
    text = replace_label_value(text, ["Name", "User Name", "First Name"], values.get("name"))
    username = values.get("username") or ""
    username_at = values.get("username_at") or (f"@{username}" if username else "")
    text = replace_label_value(text, ["Username", "Telegram Username"], username_at, allow_empty=False)
    text = replace_label_value(text, ["User ID", "Telegram ID", "Telegram User ID", "Account ID"], values.get("user_id"), wrap_code=True)
    text = replace_label_value(text, ["Phone", "Phone Number", "Mobile Number"], values.get("phone"), wrap_code=True)
    text = replace_label_value(text, ["Country"], values.get("country"))

    # Wallet/profile fields
    text = replace_label_value(text, ["Current Balance", "Wallet Balance", "Your Balance", "Balance"], f'₹{values.get("balance", "0.00")} INR')
    text = replace_label_value(text, ["Ref Balance", "Referral Balance", "Referral Earnings", "Ref Earnings"], f'₹{values.get("ref_balance", "0.00")} INR')
    text = replace_label_value(text, ["Orders", "Order Count", "Total Orders"], values.get("orders"))
    text = replace_label_value(text, ["Lifetime spent", "Lifetime Spent", "Total Spent"], f'₹{values.get("lifetime", "0.00")} INR')
    text = replace_label_value(text, ["Total deposited", "Total Deposited", "Deposited"], f'₹{values.get("deposited", "0.00")} INR')
    text = replace_label_value(text, ["Joined", "Joined Date", "Join Date"], values.get("joined"))

    # Optional transaction/order fields. They are only changed when the caller
    # supplies the corresponding live value.
    for labels, key in [
        (["Product ID", "Product ID Number"], "product_id"),
        (["Product", "Product Name", "Hack", "Hack Purchased"], "product_name"),
        (["Plan", "Plan Days", "Validity"], "plan"),
        (["Order ID", "Order No", "Order Number"], "order_id"),
        (["Price Paid", "Unit Price", "Price", "Amount", "Paid", "Paid Amount"], "amount"),
        (["Method", "Payment Method"], "method"),
        (["Device ID"], "device_id"),
        (["UTR"], "utr"),
        (["Key", "Your Key", "Purchased Key"], "key"),
        (["Date", "Date/Time", "Time"], "date"),
    ]:
        if key in values:
            val = values.get(key)
            if val is not None and str(val) != "":
                text = replace_label_value(text, labels, val, wrap_code=(key in {"order_id", "device_id", "utr", "key"}))

    # Some existing QR templates use ``Order:`` instead of ``Order ID:``.
    # Update only an exact ``Order:`` label so ``Order Details:`` is never touched.
    if "order_id" in values and str(values.get("order_id") or "") != "":
        order_value = str(values.get("order_id"))
        order_pattern = re.compile(r'(?im)^([^\n]*?\bOrder\s*:\s*)([^\n]*)$')

        def _order_repl(match):
            old_value = match.group(2)
            suffix_match = re.search(r'(\s*(?:</[^>]+>\s*)+)$', old_value)
            suffix = suffix_match.group(1) if suffix_match else ''
            return match.group(1) + order_value + suffix

        text = order_pattern.sub(_order_repl, text)

    return text

# Default styles requested for the shop UI.
DEFAULT_MAIN_BUTTON_COLORS = {
    "open_store": "red",
    "top_up": "green",
    "orders": "green",
    "my_account": "green",
    "invite_earn": "green",
    "how_to_use": "green",
    "all_update": "red",
    "help_desk": "red",
}

# ==================== USER PANEL BUTTON COLOR CATALOG ====================
# This catalog contains every user-facing button that is built through
# make_ui_button(), including dynamic Hack and Price/Plan buttons.
# Dynamic items are generated from the current database, so newly added
# hacks/plans automatically appear here without editing this code again.

def get_user_panel_button_catalog():
    """Return every user-facing button key used by the bot.

    Dynamic products/plans are read from the database, so newly added hacks and
    plans automatically appear in the Admin color/emoji panels.
    """
    items = [
        # Main menu
        ("🛍️ Open Store", "main:open_store"),
        ("💰 Top Up", "main:top_up"),
        ("📜 Orders", "main:orders"),
        ("👤 My Account", "main:my_account"),
        ("🎁 Invite & Earn", "main:invite_earn"),
        ("🎬 How To Use", "main:how_to_use"),
        ("📢 All Update File", "main:all_update"),
        ("📞 Help Desk", "main:help_desk"),

        # Top-up
        ("💰 ₹100 Top-up", "topup:100"),
        ("💰 ₹250 Top-up", "topup:250"),
        ("💰 ₹500 Top-up", "topup:500"),
        ("💰 ₹1000 Top-up", "topup:1000"),
        ("💰 ₹2000 Top-up", "topup:2000"),
        ("💰 ₹5000 Top-up", "topup:5000"),
        ("✏️ Custom Top-up", "topup:custom"),

        # Payments
        ("💳 Wallet Payment", "payment:wallet"),
        ("🇮🇳 UPI Payment", "payment:upi"),

        # Navigation
        ("⬅️ Back to Main", "nav:back_main"),
        ("⬅️ Back to Store", "nav:back_store"),
        ("🔙 Back from Top-up", "nav:back_topup"),
        ("🔙 Back from QR", "nav:back_qr"),
        ("🏠 Success Main Menu", "nav:success_main_menu"),

        # Support / links
        ("💬 Telegram Support", "link:telegram_support"),
        ("📱 WhatsApp Support", "link:whatsapp_support"),
        ("📩 Referral Share", "link:referral_share"),
        ("▶️ Guide Video", "link:guide"),
        ("🔗 Telegram Group", "link:telegram_group"),
    ]

    for product_name in get_unique_products():
        items.append((f"🛒 {product_name}", f"hack:{product_name}"))
        for plan in get_product_plans(product_name):
            p_id = plan[0]
            days = plan[2]
            items.append((f"🛒 Buy {days}", f"price:{product_name}:{p_id}"))

    seen = set()
    unique_items = []
    for title, key in items:
        if key not in seen:
            seen.add(key)
            unique_items.append((title, key))
    return unique_items

def _button_color_name(button_key):
    """Return the saved logical color name for a button key."""
    saved = get_setting(_style_setting_key(button_key))
    if saved in ("red", "blue", "green"):
        return saved
    return None


def show_user_panel_button_emoji_catalog(chat_id, message_id=None):
    """Show every user-facing button and let the admin assign one Premium emoji."""
    items = get_user_panel_button_catalog()
    if not items:
        bot.send_message(chat_id, "⚠️ <b>No user panel buttons found.</b>", parse_mode="HTML")
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    catalog = {}
    for title, key in items:
        h = _ui_hash(key)
        catalog[h] = key
        current = bool(get_button_emoji(key))
        icon = "✨" if current else "⚪"
        markup.add(types.InlineKeyboardButton(f"{icon} {title}", callback_data=f"abe_select_{h}"))

    admin_temp_data.setdefault(chat_id, {})
    admin_temp_data[chat_id]["all_button_emoji_catalog"] = catalog
    panel_text = (
        "✨ <b>ALL BUTTON EMOJI</b>\n\n"
        "Every User Panel button is listed below.\n"
        "Tap a button → send exactly one Premium custom emoji.\n"
        "The old normal leading emoji is automatically hidden.\n\n"
        f"📦 <b>Total buttons:</b> {len(items)}"
    )
    if message_id:
        try:
            bot.edit_message_text(panel_text, chat_id, message_id, parse_mode="HTML", reply_markup=markup)
            return
        except Exception:
            pass
    bot.send_message(chat_id, panel_text, parse_mode="HTML", reply_markup=markup)

def show_user_panel_button_color_catalog(chat_id, message_id=None):
    """Show every user-facing button, then let admin choose Red/Blue/Green."""
    items = get_user_panel_button_catalog()

    if not items:
        bot.send_message(
            chat_id,
            "⚠️ <b>No user panel buttons found.</b>",
            parse_mode="HTML"
        )
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    catalog = {}

    for title, key in items:
        h = _ui_hash(key)
        catalog[h] = key

        current = _button_color_name(key)
        current_icon = {
            "red": "🔴",
            "blue": "🔵",
            "green": "🟢",
        }.get(current, "⚪")

        markup.add(
            types.InlineKeyboardButton(
                f"{current_icon} {title}",
                callback_data=f"upc_select_{h}"
            )
        )

    # Keep the mapping in admin_temp_data without deleting other admin state.
    admin_temp_data.setdefault(chat_id, {})
    admin_temp_data[chat_id]["user_panel_color_catalog"] = catalog

    panel_text = (
        "🎨 <b>USER PANEL BUTTON COLORS</b>\n\n"
        "All user-facing buttons are listed below.\n"
        "Tap any button → choose <b>Red</b>, <b>Green</b> or <b>Blue</b>.\n"
        "The selected color is saved immediately and will be used after the screen is refreshed.\n\n"
        f"📦 <b>Total buttons:</b> {len(items)}"
    )

    if message_id:
        try:
            bot.edit_message_text(
                panel_text,
                chat_id,
                message_id,
                parse_mode="HTML",
                reply_markup=markup
            )
            return
        except Exception:
            pass

    bot.send_message(
        chat_id,
        panel_text,
        parse_mode="HTML",
        reply_markup=markup
    )

server_api_url = get_setting('server_api_url') or RESELLER_API_URL
server_api_key = get_setting('server_api_key') or RESELLER_API_KEY
guide_video_url = get_setting('guide_url')

# ==================== DATABASE HELPERS ====================
def record_pending_payment(order_id, user_id, user_name, product_name, plan_days, amount):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    date_now = datetime.datetime.now().strftime("%b %d · %H:%M IST")
    cursor.execute('''
        INSERT INTO pending_payments (order_id, user_id, user_name, product_name, plan_days, amount, date_time)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (order_id, user_id, user_name, product_name, plan_days, amount, date_now))
    conn.commit()
    conn.close()

def get_all_pending_payments():
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('SELECT order_id, user_id, user_name, product_name, plan_days, amount, date_time FROM pending_payments ORDER BY id DESC LIMIT 20')
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_user(user_id):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_all_users():
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, first_name, phone_number, balance FROM users WHERE is_verified = 1')
    users = cursor.fetchall()
    conn.close()
    return users

def save_or_update_user(user_id, first_name, phone_number=None, verified=0, referred_by=0):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    today_date = datetime.datetime.now().strftime("%Y-%m-%d IST")
    cursor.execute('''
        INSERT INTO users (user_id, first_name, phone_number, joined_date, is_verified, referred_by)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            first_name = excluded.first_name,
            phone_number = COALESCE(excluded.phone_number, users.phone_number),
            is_verified = CASE WHEN excluded.is_verified = 1 THEN 1 ELSE users.is_verified END
    ''', (user_id, first_name, phone_number, today_date, verified, referred_by))
    conn.commit()
    conn.close()

def reset_user_completely_db(user_id):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return success

def set_reseller_status(user_id, status=1):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_reseller = ? WHERE user_id = ?', (status, user_id))
    conn.commit()
    conn.close()

def reward_referrer_discount(referrer_id):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET referrals_count = referrals_count + 1, balance = balance + 2.0, ref_balance = ref_balance + 2.0 WHERE user_id = ?', (referrer_id,))
    conn.commit()
    conn.close()

def mark_ref_discount_used(user_id):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET discount_percent = 0.0, ref_discount_used = 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def claim_processed_payment(order_id, user_id, payment_type, amount):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO processed_payments (order_id, user_id, payment_type, amount, date_time) VALUES (?, ?, ?, ?, ?)',
            (str(order_id), int(user_id), str(payment_type), float(amount), datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        conn.rollback()
        return False
    finally:
        conn.close()

def add_user_balance(user_id, amount):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET balance = balance + ?, total_deposited = total_deposited + ? WHERE user_id = ?', (amount, amount, user_id))
    conn.commit()
    conn.close()

def deduct_user_balance(user_id, amount):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?', (amount, user_id, amount))
    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return success

def modify_user_balance_manual(user_id, amount, is_add=True):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    if is_add:
        cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    else:
        cursor.execute('UPDATE users SET balance = MAX(0.0, balance - ?) WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()

def add_product_db(name, pid_id, days, price, resell_price, is_manual=0, remote_duration=''):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('SELECT MAX(display_order) FROM products')
    max_ord = cursor.fetchone()[0]
    next_order = (max_ord + 1) if max_ord is not None else 0
    cursor.execute('INSERT INTO products (name, pid_id, days, price, resell_price, is_manual, remote_duration, display_order) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (name, pid_id, days, price, resell_price, is_manual, remote_duration, next_order))
    conn.commit()
    conn.close()

def update_product_price_db(plan_id, new_price, new_resell_price):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('UPDATE products SET price = ?, resell_price = ? WHERE id = ?', (new_price, new_resell_price, plan_id))
    conn.commit()
    conn.close()

def update_product_api_mapping(plan_id, pid_id, remote_duration):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('UPDATE products SET pid_id = ?, remote_duration = ? WHERE id = ?', (str(pid_id), str(remote_duration), plan_id))
    conn.commit()
    conn.close()

def set_hack_tg_group(product_name, group_link):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('UPDATE products SET tg_group_link = ? WHERE name = ?', (group_link, product_name))
    conn.commit()
    conn.close()

def set_plan_stock_status(plan_id, is_out_of_stock):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('UPDATE products SET is_out_of_stock = ? WHERE id = ?', (is_out_of_stock, plan_id))
    conn.commit()
    conn.close()

def set_plan_device_id_status(plan_id, require_device_id):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('UPDATE products SET require_device_id = ? WHERE id = ?', (require_device_id, plan_id))
    conn.commit()
    conn.close()

def add_key_db(panel_name, days_plan, panel_key):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO panels (panel_name, panel_price, panel_key, validity_days) VALUES (?, 0, ?, ?)', (panel_name, panel_key, days_plan))
    conn.commit()
    conn.close()

def delete_entire_hack_db(name):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM products WHERE name = ?', (name,))
    conn.commit()
    conn.close()

def delete_product_plan_db(plan_id):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM products WHERE id = ?', (plan_id,))
    conn.commit()
    conn.close()

def set_user_discount_db(user_id, percent):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET discount_percent = ?, ref_discount_used = 0 WHERE user_id = ?', (percent, user_id))
    conn.commit()
    conn.close()

def set_global_discount_db(percent):
    try:
        percent = max(0.0, min(100.0, float(percent)))
    except Exception:
        percent = 0.0
    set_setting('global_discount', str(percent))
    if percent == 0.0:
        # A 0% global discount is the explicit reset requested by the admin:
        # clear per-hack discounts too, then return every product/plan button to blue.
        conn = sqlite3.connect('shop_data.db', timeout=15)
        cursor = conn.cursor()
        cursor.execute('UPDATE products SET discount_percent = 0.0')
        conn.commit()
        conn.close()
    # Global discount controls the default product/price color for every hack.
    sync_all_product_button_colors()

def set_product_discount_db(product_name, percent):
    try:
        percent = max(0.0, min(100.0, float(percent)))
    except Exception:
        percent = 0.0
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('UPDATE products SET discount_percent = ? WHERE name = ?', (percent, product_name))
    conn.commit()
    conn.close()
    # Green when this hack has an active discount; blue again at 0% unless a
    # global discount is still active.
    sync_product_button_colors(product_name)

def get_unique_products():
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('SELECT name, MIN(display_order) as ord FROM products GROUP BY name ORDER BY ord ASC, name ASC')
    products = cursor.fetchall()
    conn.close()
    return [p[0] for p in products]

def move_hack_order(product_name, direction):
    products = get_unique_products()
    if product_name not in products:
        return
    idx = products.index(product_name)
    if direction == "up" and idx > 0:
        other_name = products[idx - 1]
    elif direction == "down" and idx < len(products) - 1:
        other_name = products[idx + 1]
    else:
        return

    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('SELECT MIN(display_order) FROM products WHERE name = ?', (product_name,))
    order1 = cursor.fetchone()[0] or 0
    cursor.execute('SELECT MIN(display_order) FROM products WHERE name = ?', (other_name,))
    order2 = cursor.fetchone()[0] or 0

    if order1 == order2:
        order1, order2 = idx, (idx - 1 if direction == "up" else idx + 1)

    cursor.execute('UPDATE products SET display_order = ? WHERE name = ?', (order2, product_name))
    cursor.execute('UPDATE products SET display_order = ? WHERE name = ?', (order1, other_name))
    conn.commit()
    conn.close()

def get_product_plans(name):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('SELECT id, pid_id, days, price, resell_price, is_manual, discount_percent, remote_duration, tg_group_link, is_out_of_stock, require_device_id FROM products WHERE name = ? ORDER BY id ASC', (name,))
    plans = cursor.fetchall()
    conn.close()
    return plans

def get_product_by_id(product_id):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, pid_id, days, price, resell_price, is_manual, discount_percent, remote_duration, tg_group_link, is_out_of_stock, require_device_id FROM products WHERE id = ?', (product_id,))
    product = cursor.fetchone()
    conn.close()
    return product

def get_key_stock_count(product_name, days_plan):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM panels WHERE panel_name = ? AND validity_days = ? AND is_sold = 0', (product_name, days_plan))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_key_stock_counts(product_name, days_plans):
    """Return manual unsold-key counts for all requested plans in one query.
    This avoids one SQLite connection/query per plan when rendering a price list.
    """
    days_plans = [str(x) for x in days_plans]
    if not days_plans:
        return {}
    conn = sqlite3.connect('shop_data.db', timeout=15)
    try:
        placeholders = ",".join("?" for _ in days_plans)
        cursor = conn.cursor()
        cursor.execute(
            f'''SELECT validity_days, COUNT(*) FROM panels
                WHERE panel_name = ? AND validity_days IN ({placeholders})
                  AND is_sold = 0
                GROUP BY validity_days''',
            [product_name] + days_plans
        )
        return {str(days): int(count) for days, count in cursor.fetchall()}
    finally:
        conn.close()

def fetch_and_claim_manual_key(product_name, days_plan):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('SELECT id, panel_key FROM panels WHERE panel_name = ? AND validity_days = ? AND is_sold = 0 ORDER BY id ASC LIMIT 1', (product_name, days_plan))
    key_row = cursor.fetchone()
    if key_row:
        key_id, key_val = key_row
        cursor.execute('UPDATE panels SET is_sold = 1 WHERE id = ?', (key_id,))
        conn.commit()
        conn.close()
        return key_val
    conn.close()
    return None

def get_user_orders(user_id):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    cursor.execute('SELECT order_id, product_name, plan_days, price_paid, purchased_key, date_time FROM order_history WHERE user_id = ? ORDER BY id DESC', (user_id,))
    orders = cursor.fetchall()
    conn.close()
    return orders

# ==================== EXACT PHP cURL TO PYTHON CONVERSION ====================
def fetch_key_from_api(pid_id, duration, android_id=None):
    curr_api_url = get_setting('server_api_url') or RESELLER_API_URL
    curr_api_key = get_setting('server_api_key') or RESELLER_API_KEY
    
    if not pid_id or pid_id == '0' or (str(pid_id).isdigit() and int(pid_id) < 10):
        pid_id = '133'

    if not duration or duration == '0':
        duration = '1 Hours'

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'x-master-key': RESELLER_MASTER_KEY
    }
    
    payload = {
        'api_key': str(curr_api_key).strip(),
        'action': 'buy',
        'product_id': str(pid_id).strip(),
        'duration': str(duration).strip()
    }

    if android_id:
        payload['android_id'] = str(android_id).strip()

    try:
        response = HTTP_SESSION.post(curr_api_url, data=payload, headers=headers, timeout=15)
        raw_resp = response.text.strip()
        print(f"DEBUG PROVIDER API RESPONSE: {raw_resp}")

        try:
            res_json = response.json()
            if isinstance(res_json, dict):
                for field in ['key', 'license', 'serial', 'code', 'key_value', 'licence']:
                    if field in res_json and res_json[field]:
                        return str(res_json[field]).strip()
                
                if 'data' in res_json and isinstance(res_json['data'], dict):
                    for field in ['key', 'license', 'serial', 'code', 'key_value']:
                        if field in res_json['data'] and res_json['data'][field]:
                            return str(res_json['data'][field]).strip()
                        
                if 'data' in res_json and isinstance(res_json['data'], str) and len(res_json['data']) > 3:
                    return str(res_json['data']).strip()
        except Exception:
            pass

        if raw_resp and not raw_resp.startswith('{') and len(raw_resp) < 120:
            return raw_resp

    except Exception as e:
        print(f"API Request Error: {e}")
    return None

def notify_admins_topup(user_id, u_name, order_id, amount, new_balance, utr=None):
    """Notify every admin immediately after a wallet top-up is verified."""
    now_text = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    default_topup_text = (
        f"💰 <b>WALLET TOP-UP SUCCESSFUL</b> 💰\n\n"
        f"👤 <b>Username:</b> {html.escape(str(u_name or 'User'))}\n"
        f"🆔 <b>Telegram ID:</b> <code>{user_id}</code>\n"
        f"💵 <b>Amount Added:</b> ₹{amount:.2f} INR\n"
        f"💼 <b>New Balance:</b> ₹{new_balance:.2f} INR\n"
        f"🧾 <b>Order ID:</b> <code>{order_id}</code>\n"
        f"🏷️ <b>UTR:</b> <code>{html.escape(str(utr or 'N/A'))}</code>\n"
        f"🕒 <b>Time:</b> {now_text}"
    )
    live_username = _get_live_telegram_username(user_id, u_name)
    admin_topup_text = _safe_format_custom_text(
        get_custom_text("topup_notification", "{default_topup}"),
        user=u_name or 'User',
        name=u_name or 'User',
        username=live_username,
        telegram_username=live_username,
        user_id=user_id,
        telegram_id=user_id,
        amount=f"{amount:.2f}",
        balance=f"{new_balance:.2f}",
        order_id=order_id,
        utr=utr or 'N/A',
        date=now_text,
        time=now_text,
        default_topup=default_topup_text
    )
    admin_topup_text = _inject_labeled_user_values(
        admin_topup_text,
        {
            "name": html.escape(str(u_name or 'User'), quote=False),
            "username": html.escape(str(live_username), quote=False),
            "username_at": html.escape(f"@{live_username}" if live_username else "", quote=False),
            "user_id": str(user_id),
            "balance": f"{new_balance:.2f}",
            "amount": f"₹{amount:.2f} INR",
            "order_id": order_id,
            "utr": utr or 'N/A',
            "date": now_text,
        }
    )
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(admin_id, admin_topup_text, parse_mode="HTML")
        except Exception:
            pass

def notify_admins_purchase(user_id, u_name, order_id, prod_name, prod_days, amount, device_id=None):
    user = get_user(user_id)
    phone = user[2] if user and len(user) > 2 else "N/A"
    country = user[3] if user and len(user) > 3 else "IN"
    dev_str = f"\n📱 <b>Device ID:</b> <code>{device_id}</code>" if device_id else ""
    default_purchase_text = (
        f"🚨 <b>NEW HACK PURCHASE NOTIFICATION!</b> 🚨\n\n"
        f"👤 <b>User:</b> {u_name} (<code>{user_id}</code>)\n"
        f"📱 <b>Phone:</b> <code>{phone or 'N/A'}</code>\n"
        f"🌐 <b>Country:</b> {country or 'IN'}\n"
        f"🎮 <b>Hack Purchased:</b> {prod_name}\n"
        f"⏱️ <b>Plan Days:</b> {prod_days}\n"
        f"💰 <b>Price Paid:</b> ₹{amount:.2f} INR\n"
        f"🆔 <b>Order ID:</b> <code>{order_id}</code>{dev_str}\n"
        f"📅 <b>Date:</b> {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    purchase_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    live_username = _get_live_telegram_username(user_id, u_name)
    admin_purchase_text = _safe_format_custom_text(
        get_custom_text("purchase_notification", "{default_purchase}"),
        user=u_name,
        name=u_name,
        username=live_username,
        telegram_username=live_username,
        user_id=user_id,
        telegram_id=user_id,
        phone=phone or "N/A",
        number=phone or "N/A",
        country=country or "IN",
        hack=prod_name,
        product_name=prod_name,
        plan=prod_days,
        amount=f"{amount:.2f}",
        order_id=order_id,
        device_id=device_id or "",
        date=purchase_time,
        default_purchase=default_purchase_text
    )
    admin_purchase_text = _inject_labeled_user_values(
        admin_purchase_text,
        {
            "name": html.escape(str(u_name or 'User'), quote=False),
            "username": html.escape(str(live_username), quote=False),
            "username_at": html.escape(f"@{live_username}" if live_username else "", quote=False),
            "user_id": str(user_id),
            "phone": html.escape(str(phone or 'N/A'), quote=False),
            "country": html.escape(str(country or 'IN'), quote=False),
            "product_name": html.escape(str(prod_name), quote=False),
            "plan": html.escape(str(prod_days), quote=False),
            "amount": f"₹{amount:.2f} INR",
            "order_id": order_id,
            "device_id": device_id or "",
            "date": purchase_time,
        }
    )
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(admin_id, admin_purchase_text, parse_mode="HTML")
        except Exception:
            pass

def record_order(order_id, user_id, product_name, plan_days, price_paid, key_val):
    conn = sqlite3.connect('shop_data.db', timeout=15)
    cursor = conn.cursor()
    date_now = datetime.datetime.now().strftime("%b %d · %H:%M IST")
    cursor.execute('''
        INSERT INTO order_history (order_id, user_id, product_name, plan_days, price_paid, purchased_key, date_time)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (order_id, user_id, product_name, plan_days, price_paid, key_val, date_now))
    cursor.execute('UPDATE users SET orders_count = orders_count + 1, lifetime_spent = lifetime_spent + ? WHERE user_id = ?', (price_paid, user_id))
    conn.commit()
    conn.close()

# ==================== FAMGATEWAY AUTO-CHECK LOGIC ====================

# ==================== FAMGATEWAY AUTO-CHECK LOGIC ====================

def _build_stylish_qr_image(payload, size=900):
    """Render the exact payment payload as a premium, scan-friendly QR.

    The payment payload is never changed by the styling. Error correction H,
    a generous quiet zone, rounded modules, and a small center logo are used
    so common UPI apps can still scan it reliably.
    """
    payload = str(payload or "").strip()
    if not payload:
        raise ValueError("Empty QR payload")

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=16,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)

    qr_img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=RoundedModuleDrawer(),
        eye_drawer=SquareModuleDrawer(),
        color_mask=SolidFillColorMask(
            front_color=(18, 18, 22),
            back_color=(255, 255, 255),
        ),
    ).convert("RGB")

    qr_img = qr_img.resize((size, size), Image.Resampling.NEAREST)

    # Premium center logo inspired by the supplied reference image.
    logo_size = int(size * 0.17)
    logo = Image.new("RGBA", (logo_size, logo_size), (255, 255, 255, 0))
    ld = ImageDraw.Draw(logo)

    pad = max(8, logo_size // 14)
    ld.ellipse(
        (pad, pad, logo_size - pad, logo_size - pad),
        fill=(255, 255, 255, 255),
    )

    inner = pad + max(5, logo_size // 28)
    ld.ellipse(
        (inner, inner, logo_size - inner, logo_size - inner),
        fill=(255, 165, 0, 255),
    )

    # Simple white abstract leaf mark matching the visual idea of the reference.
    cx = logo_size / 2
    cy = logo_size / 2
    leaf_w = logo_size * 0.23
    leaf_h = logo_size * 0.48

    ld.ellipse(
        (
            cx - leaf_w * 0.15,
            cy - leaf_h * 0.58,
            cx + leaf_w * 0.65,
            cy + leaf_h * 0.05,
        ),
        fill=(255, 255, 255, 255),
    )
    ld.polygon(
        [
            (cx - leaf_w * 0.02, cy - leaf_h * 0.05),
            (cx + leaf_w * 0.65, cy - leaf_h * 0.58),
            (cx + leaf_w * 0.25, cy + leaf_h * 0.05),
            (cx - leaf_w * 0.30, cy + leaf_h * 0.35),
        ],
        fill=(255, 255, 255, 255),
    )
    ld.ellipse(
        (
            cx - leaf_w * 0.72,
            cy - leaf_h * 0.22,
            cx - leaf_w * 0.05,
            cy + leaf_h * 0.30,
        ),
        fill=(255, 255, 255, 255),
    )

    pos = ((size - logo_size) // 2, (size - logo_size) // 2)
    qr_img.paste(logo, pos, logo)

    output = io.BytesIO()
    output.name = "rg_cheat_shop_upi_qr.png"
    qr_img.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output


def _decode_qr_payload_from_url(qr_url):
    """Recover the gateway QR's exact encoded payload before restyling it."""
    if not qr_url or not isinstance(qr_url, str):
        return None

    try:
        if qr_url.startswith("data:image/"):
            _, encoded = qr_url.split(",", 1)
            import base64
            raw = base64.b64decode(encoded)
            arr = np.frombuffer(raw, dtype=np.uint8)
        elif qr_url.startswith(("http://", "https://")):
            res = HTTP_SESSION.get(qr_url, timeout=8)
            res.raise_for_status()
            arr = np.frombuffer(res.content, dtype=np.uint8)
        else:
            return None

        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            return None

        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(image)
        data = str(data or "").strip()
        return data or None
    except Exception as e:
        print(f"Gateway QR decode warning: {e}")
        return None


def _extract_gateway_qr_payload(data, qr_url, order_id, amount):
    """Prefer the gateway's own payload; otherwise decode its QR image."""
    if isinstance(data, dict):
        for key in (
            "upi_uri",
            "upi_url",
            "upi",
            "qr_data",
            "qr_string",
            "payment_uri",
            "payment_url",
            "deeplink",
        ):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    decoded = _decode_qr_payload_from_url(qr_url)
    if decoded:
        return decoded

    # Same receiver/order/amount fields as the original fallback QR.
    return (
        f"upi://pay?pa={urllib.parse.quote(RECEIVER_UPI, safe='@')}"
        f"&pn={urllib.parse.quote('RG CHEAT SHOP')}"
        f"&am={float(amount):.2f}&cu=INR"
        f"&tn={urllib.parse.quote(str(order_id))}"
    )


def create_fam_qr(amount):
    """Create a FAM order and return a styled QR image + the same order id.

    The gateway still creates the real order and verify_fam_order() still checks
    that exact order id. Only the visual QR image is changed.
    """
    amount = float(amount)
    create_url = f"{BASE_GATEWAY_URL}/create_order.php"

    try:
        res = HTTP_SESSION.get(
            create_url,
            params={"amount": f"{amount:.2f}", "api_key": FAM_API_KEY},
            timeout=10,
        )
        res.raise_for_status()
        res_json = res.json()
        data = res_json.get("data") or {}

        if res_json.get("status") == "success" or res_json.get("status") is True:
            qr_url = data.get("qr_url") or data.get("qr")
            order_id = data.get("order_id")

            if qr_url and order_id:
                payload = _extract_gateway_qr_payload(
                    data, qr_url, order_id, amount
                )
                try:
                    return _build_stylish_qr_image(payload), str(order_id)
                except Exception as style_error:
                    print(f"Styled QR warning: {style_error}")

                # Absolute final fallback: keep the original gateway QR.
                return qr_url, str(order_id)

    except Exception as e:
        print(f"Gateway QR Error: {e}")

    # Original direct-UPI fallback retained for gateway/API outages.
    order_id = (
        "FAM"
        + datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        + str(random.randint(1000, 9999))
    )
    upi_uri = (
        f"upi://pay?pa={urllib.parse.quote(RECEIVER_UPI, safe='@')}"
        f"&pn={urllib.parse.quote('RG CHEAT SHOP')}"
        f"&am={amount:.2f}&cu=INR&tn={urllib.parse.quote(order_id)}"
    )

    try:
        return _build_stylish_qr_image(upi_uri), order_id
    except Exception as style_error:
        print(f"Fallback styled QR warning: {style_error}")
        fallback_qr = (
            "https://api.qrserver.com/v1/create-qr-code/"
            f"?size=500x500&data={urllib.parse.quote(upi_uri, safe='')}"
        )
        return fallback_qr, order_id

def verify_fam_order(order_id):
    verify_url = f"{BASE_GATEWAY_URL}/verify.php?order_id={order_id}&api_key={FAM_API_KEY}"
    try:
        res = HTTP_SESSION.get(verify_url, timeout=10)
        res_json = res.json()
        if res_json.get('status') == 'success' or res_json.get('status') is True:
            utr = res_json.get('data', {}).get('utr', 'N/A')
            sender = res_json.get('data', {}).get('sender_name', 'UPI User')
            return True, utr, sender
    except Exception as e:
        pass
    return False, None, None

def process_successful_payment(chat_id, user_id, message_id, order_id, amount, pay_type, utr, product_id=0, device_id=None):
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass
    
    user = get_user(user_id)
    u_name = user[1] if user else "User"

    if pay_type == "topup":
        if not claim_processed_payment(order_id, user_id, "topup", amount):
            return
        add_user_balance(user_id, amount)
        updated_user = get_user(user_id)
        new_bal = updated_user[4] if updated_user else amount
        notify_admins_topup(user_id, u_name, order_id, amount, new_bal, utr)

        # Add Balance success uses a separate admin-editable Premium Emoji/Text
        # template. Balance crediting happens before rendering, so Current Balance
        # is always the real post-credit balance.
        success_template = get_wallet_topup_success_emoji_template()
        success_msg = _render_wallet_topup_success_emoji_template(
            success_template,
            user_id=user_id,
            user_name=u_name,
            order_id=order_id,
            amount=amount,
            utr=utr,
            current_balance=new_bal,
        )
        markup = types.InlineKeyboardMarkup()
        btn_main = make_ui_button("🏠 Main Menu", callback_data="back_to_main_new", button_key="nav:success_main_menu", default_color="blue")
        markup.add(btn_main)
    else:
        product = get_product_by_id(product_id)
        prod_name = product[1] if product else "VIP Hack"
        prod_days = product[3] if product else "1 Plan"
        pid_id = product[2] if product and product[2] and product[2] != '0' else "133"
        remote_dur = product[8] if len(product) > 8 and product[8] else prod_days
        tg_group_link = product[9] if len(product) > 9 and product[9] else ""

        key_val = fetch_and_claim_manual_key(prod_name, prod_days)
        if not key_val:
            key_val = fetch_key_from_api(pid_id, remote_dur, android_id=device_id)
        if not key_val:
            key_val = "⚠️ Key assigned! Check orders history or contact Admin."

        record_order(order_id, user_id, prod_name, prod_days, amount, key_val)
        notify_admins_purchase(user_id, u_name, order_id, prod_name, prod_days, amount, device_id)
        
        if user and user[12] > 0 and user[15] == 0:
            mark_ref_discount_used(user_id)

        usd_equiv = amount / 90.0

        dev_info = f"📱 <b>Device ID:</b> <code>{device_id}</code>\n" if device_id else ""

        payment_title = "💰 <b>WALLET PAYMENT SUCCESSFUL</b> 💰" if pay_type == "wallet" else "💳 <b>PAYMENT SUCCESSFUL</b> 💳"
        payment_method = "💼 Wallet Balance" if pay_type == "wallet" else "🇮🇳 Pay via UPI"
        # Wallet and UPI now have completely separate Premium Emoji/Text designs.
        # This keeps the existing Wallet editor intact and lets the admin customize
        # the UPI success message independently.
        payment_template = (
            get_wallet_payment_emoji_template()
            if str(pay_type).lower() == "wallet"
            else get_upi_payment_emoji_template()
        )
        if payment_template:
            success_msg = _render_wallet_payment_emoji_template(
                payment_template,
                user_id=user_id,
                order_id=order_id,
                product_id=product[0],
                product_name=prod_name,
                plan=prod_days,
                amount=amount,
                key_val=key_val,
                pay_type=pay_type,
                device_id=device_id,
            )
        else:
            success_msg = (
                f"{payment_title}\n"
                f"<i>Instant Key Delivery!</i>\n\n"
                f"📋 <b>ORDER DETAILS</b>\n"
                f"├── 👤 <b>User ID:</b> <code>{user_id}</code>\n"
                f"├── 🆔 <b>Order ID:</b> <code>{order_id}</code>\n"
                f"├── 🛒 <b>Product ID:</b> <code>{product[0]}</code>\n"
                f"├── 🎮 <b>Product:</b> {html.escape(str(prod_name))}\n"
                f"├── ⏱️ <b>Plan:</b> {html.escape(str(prod_days))}\n"
                f"├── 💳 <b>Method:</b> {payment_method}\n"
                f"{dev_info}"
                f"└── 💵 <b>Paid:</b> ₹{amount:.2f} INR\n\n"
                f"🔑 <b>YOUR KEY:</b>\n"
                f"<code>{html.escape(str(key_val))}</code>\n\n"
                f"💡 <i>Tap the key above to copy instantly.</i>"
            )
        markup = types.InlineKeyboardMarkup()
        if tg_group_link:
            markup.add(make_ui_button("🔗 Join Telegram Group", url=tg_group_link, button_key="link:telegram_group", default_color="blue"))
        markup.add(make_ui_button("🏠 Main Menu", callback_data="back_to_main_new", button_key="nav:success_main_menu", default_color="blue"))

    _send_payment_success_safely(chat_id, success_msg, reply_markup=markup)

PAYMENT_POLL_INTERVAL = 3
PAYMENT_TIMEOUT_SECONDS = 300


def poll_payment_in_bot(chat_id, user_id, message_id, order_id, amount, pay_type, product_id=0, device_id=None):
    start_time = time.time()
    while time.time() - start_time < PAYMENT_TIMEOUT_SECONDS: 
        if order_id not in active_orders:
            return  
            
        is_paid, utr, sender = verify_fam_order(order_id)
        if is_paid:
            active_orders.pop(order_id, None)
            process_successful_payment(chat_id, user_id, message_id, order_id, amount, pay_type, utr, product_id, device_id)
            return
        time.sleep(PAYMENT_POLL_INTERVAL)
    
    if order_id in active_orders:
        order_details = active_orders.pop(order_id, None)
        user = get_user(user_id)
        u_name = user[1] if user else "User"
        
        prod_name = "TopUp Balance"
        prod_days = "N/A"
        if product_id > 0:
            product = get_product_by_id(product_id)
            if product:
                prod_name = product[1]
                prod_days = product[3]
                
        record_pending_payment(order_id, user_id, u_name, prod_name, prod_days, amount)

        default_expire_msg = "⏱️ <b>Payment QR Expired!</b>\n5 minutes timeout completed. Please initiate a new request if you wish to pay."
        expire_text = get_custom_text("payment_expired", default_expire_msg)

        try:
            bot.delete_message(chat_id, message_id)
            bot.send_message(chat_id, expire_text, parse_mode="HTML")
        except Exception:
            pass

# ==================== BOT COMMANDS & HANDLERS ====================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "User"
    
    if user_id in admin_temp_data:
        admin_temp_data.pop(user_id, None)
    
    command_args = message.text.split()
    referred_by = 0
    if len(command_args) > 1 and command_args[1].startswith("ref_"):
        try:
            referred_by = int(command_args[1].replace("ref_", ""))
            if referred_by == user_id:
                referred_by = 0
        except ValueError:
            referred_by = 0

    user = get_user(user_id)

    if not user or user[10] == 0:
        save_or_update_user(user_id, first_name, verified=0, referred_by=referred_by)
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        btn_contact = types.KeyboardButton(text="📱 Share Contact", request_contact=True)
        markup.add(btn_contact)

        verification_text = (
            f"🏪 <b>RG CHEAT SHOP</b>\n\n"
            f"👋 <b>Welcome, {first_name}!</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔒 <b>VERIFICATION REQUIRED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>To start shopping, please verify your phone number.</b>\n\n"
            f"✅ <b>Why we need this:</b>\n"
            f"• <b>Secure your purchases</b>\n"
            f"• <b>Deliver keys to you</b>\n"
            f"• <b>Protect your account</b>\n\n"
            f"<i>Tap the button below to share your contact.</i>"
        )
        verification_template = get_custom_text("verification_required", "{default_verification_required}")
        verification_values = _get_user_template_values(user_id, first_name)
        verification_values.update({
            "user": verification_values["name"],
            "telegram_id": str(user_id),
            "number": verification_values["phone"],
            "default_verification_required": verification_text,
        })
        verification_text = _safe_format_custom_text(verification_template, **verification_values)
        verification_text = _inject_labeled_user_values(verification_text, verification_values)
        verification_text = _replace_live_greeting_name(verification_text, first_name)
        bot.send_message(message.chat.id, verification_text, parse_mode="HTML", reply_markup=markup)
    else:
        show_shop_features(message.chat.id, first_name)

@bot.message_handler(content_types=['contact'])
def handle_contact_verification(message):
    if message.contact is not None:
        user_id = message.from_user.id
        first_name = message.from_user.first_name or "User"
        phone_number = message.contact.phone_number

        user = get_user(user_id)
        referred_by = user[13] if user and len(user) > 13 else 0

        save_or_update_user(user_id, first_name, phone_number, verified=1)

        if referred_by > 0:
            reward_referrer_discount(referred_by)
            try:
                bot.send_message(referred_by, f"🎉 <b>New Referral Verified!</b>\n\nUser <b>{first_name}</b> verified their phone number using your link!\n🎁 <b>₹2.00 INR balance has been added to your wallet!</b>", parse_mode="HTML")
            except Exception:
                pass

        default_new_user_text = (
            f"🚨 <b>NEW USER VERIFIED!</b> 🚨\n\n"
            f"👤 <b>Name:</b> {first_name}\n"
            f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
            f"📱 <b>Phone Number:</b> <code>{phone_number}</code>\n"
            f"📅 <b>Date/Time:</b> {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        new_user_values = _get_user_template_values(user_id, first_name, phone_number)
        new_user_values.update({
            "name": html.escape(str(first_name)),
            "user": html.escape(str(first_name)),
            "user_id": str(user_id),
            "telegram_id": str(user_id),
            "phone": html.escape(str(phone_number or "N/A")),
            "number": html.escape(str(phone_number or "N/A")),
            "date": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "default_new_user": default_new_user_text,
        })
        admin_notification_template = get_custom_text("new_user_notification", "{default_new_user}")
        admin_notification_text = _safe_format_custom_text(
            admin_notification_template,
            **new_user_values
        )
        admin_notification_text = _inject_labeled_user_values(admin_notification_text, new_user_values)
        for admin_id in ADMIN_IDS:
            try:
                bot.send_message(admin_id, admin_notification_text, parse_mode="HTML")
            except Exception:
                pass

        verified_text = (
            f"✅ <b>Phone verified!</b>\n\n"
            f"📞 <b>{phone_number}</b>\n"
            f"🇮🇳 <b>India</b>\n\n"
            f"<b>Welcome aboard! Loading shop...</b>"
        )
        verified_template = get_custom_text("phone_verified", "{default_phone_verified}")
        verified_values = _get_user_template_values(user_id, first_name, phone_number)
        verified_values.update({
            "user": verified_values["name"],
            "telegram_id": str(user_id),
            "number": verified_values["phone"],
            "default_phone_verified": verified_text,
        })
        verified_text = _safe_format_custom_text(verified_template, **verified_values)
        verified_text = _inject_labeled_user_values(verified_text, verified_values)
        bot.send_message(message.chat.id, verified_text, parse_mode="HTML", reply_markup=types.ReplyKeyboardRemove())
        show_shop_features(message.chat.id, first_name)

# ==================== ADMIN PANEL MENU ====================

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "❌ <b>Access Denied!</b> Only Admin can access this command.", parse_mode="HTML")
        return
    
    markup = types.InlineKeyboardMarkup()
    btn_quick_add = types.InlineKeyboardButton("⚡ Quick Admin Setup (One-Msg Hack Setup)", callback_data="admin_quick_setup")
    btn_reorder_hacks = types.InlineKeyboardButton("🔄 Reorder Hacks List Sequence", callback_data="admin_reorder_hacks")
    btn_user_reset = types.InlineKeyboardButton("🔄 Reset User Completely (By Telegram ID)", callback_data="admin_user_reset")
    btn_stock_mgmt = types.InlineKeyboardButton("📦 Stock On/Off (Out of Stock System)", callback_data="admin_stock_mgmt")
    btn_device_id_mgmt = types.InlineKeyboardButton("📱 Select Device ID Hack", callback_data="admin_device_id_mgmt")
    btn_edit_price = types.InlineKeyboardButton("✏️ Edit Product Price & Plans", callback_data="admin_edit_price")
    btn_tg_group = types.InlineKeyboardButton("🔗 Set Telegram Group Link", callback_data="admin_set_tg_group")
    btn_manage_hack_day = types.InlineKeyboardButton("⚙️ Manage Hack & Days (Add/Remove)", callback_data="admin_hack_day_mgmt")
    btn_server_api = types.InlineKeyboardButton("🌐 Add & Connect Server API", callback_data="admin_server_api_mgmt")
    btn_manual = types.InlineKeyboardButton("🔑 Add Manual VIP Keys (FIFO)", callback_data="admin_add_manual_key")
    btn_reseller = types.InlineKeyboardButton("👑 Add / Remove Reseller Role", callback_data="admin_manage_reseller")
    btn_disc = types.InlineKeyboardButton("🏷️ Manage Discounts (User/Global/Hack)", callback_data="admin_manage_discounts")
    btn_bcast = types.InlineKeyboardButton("📢 Multimedia Broadcast", callback_data="admin_broadcast")
    btn_set_guide = types.InlineKeyboardButton("🎬 Dynamic How To Use Bot Link", callback_data="admin_set_guide")
    btn_server_id_map = types.InlineKeyboardButton("🔗 Map Server Hack ID & Duration", callback_data="admin_map_server_id")
    btn_token_change = types.InlineKeyboardButton("🔑 Change Bot API Token", callback_data="admin_change_bot_token")
    btn_track = types.InlineKeyboardButton("👤 Track Users & Purchased Keys", callback_data="admin_track_users")
    btn_bal = types.InlineKeyboardButton("💰 Manage User Balance", callback_data="admin_manage_bal")
    
    btn_pending = types.InlineKeyboardButton("⏳ Pending Payments", callback_data="admin_view_pending_payments")
    btn_db_backup = types.InlineKeyboardButton("📥 Download Database Backup", callback_data="admin_db_backup")
    btn_button_cust = types.InlineKeyboardButton("🎨 All Button Color", callback_data="admin_button_colors")
    btn_button_color = types.InlineKeyboardButton("✏️ User Panel Names & Emoji", callback_data="admin_button_cust")
    btn_text_editor = types.InlineKeyboardButton("✏️ Edit Bot Texts (Text ID)", callback_data="admin_text_editor")
    btn_emoji_editor = types.InlineKeyboardButton("✨ Premium Emoji Editor", callback_data="admin_emoji_editor")
    btn_all_button_emoji = types.InlineKeyboardButton("✨ All Button Emoji", callback_data="admin_all_button_emoji")
    btn_all_product_emoji = types.InlineKeyboardButton("✨ All Product Button Emoji", callback_data="admin_all_product_emoji")
    btn_all_price_emoji = types.InlineKeyboardButton("💰 All Price List Button Emoji", callback_data="admin_all_price_emoji")
    btn_price_list_mode = types.InlineKeyboardButton(
        ("🟢 Premium Price List: ON" if get_price_list_premium_mode() else "🔴 Premium Price List: OFF"),
        callback_data="admin_toggle_price_list_mode"
    )
    btn_all_panel_price_emoji = types.InlineKeyboardButton("💠 All Panel Price & Text + Premium Emoji", callback_data="admin_all_panel_price_emoji")
    btn_plan_text_add = types.InlineKeyboardButton("📝 All Product Plan Text + Premium Emoji", callback_data="admin_plan_text_add")

    btn_hack_price_ui = types.InlineKeyboardButton("🧩 Price List Fix — Emoji & Text", callback_data="admin_hack_price_ui")

    markup.add(btn_quick_add)
    markup.add(btn_reorder_hacks, btn_user_reset)
    markup.add(btn_stock_mgmt, btn_device_id_mgmt)
    markup.add(btn_edit_price, btn_tg_group)
    markup.add(btn_manage_hack_day, btn_server_api)
    markup.add(btn_server_id_map, btn_manual)
    markup.add(btn_reseller, btn_disc)
    markup.add(btn_bcast, btn_set_guide)
    markup.add(btn_token_change, btn_track)
    markup.add(btn_bal, btn_pending)
    markup.add(btn_db_backup, btn_button_cust)
    markup.add(btn_button_color, btn_text_editor)
    markup.add(btn_emoji_editor)
    markup.add(btn_all_button_emoji)
    markup.add(btn_all_product_emoji, btn_all_price_emoji)
    markup.add(btn_price_list_mode)
    markup.add(btn_all_panel_price_emoji)
    markup.add(btn_plan_text_add)
    markup.add(btn_hack_price_ui)
    
    bot.send_message(message.chat.id, "🛠️ <b>ADMIN CONTROL PANEL</b>\n\nSelect an operation below:", parse_mode="HTML", reply_markup=markup)

# ==================== STEP-BY-STEP ADMIN HANDLERS ====================

def step_process_user_reset(message):
    try:
        target_uid = int(message.text.strip())
        success = reset_user_completely_db(target_uid)
        if success:
            try:
                bot.send_message(target_uid, "⚠️ <b>Your account has been reset by the Admin.</b>\nPlease send /start to re-verify your phone number and restart.", parse_mode="HTML")
            except Exception:
                pass
            bot.send_message(message.chat.id, f"✅ <b>User Reset Successful!</b>\n\nTelegram ID: <code>{target_uid}</code> has been completely reset. When they send /start, they will need to re-verify their phone number from the beginning.", parse_mode="HTML")
        else:
            bot.send_message(message.chat.id, f"⚠️ User ID <code>{target_uid}</code> was not found in database or already reset.", parse_mode="HTML")
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ <b>Invalid ID!</b> Please send numeric Telegram User ID:")
        bot.register_next_step_handler(msg, step_process_user_reset)

def step_edit_product_price(message):
    user_id = message.from_user.id
    try:
        prices = [p.strip() for p in message.text.strip().split('|')]
        if len(prices) != 2:
            raise ValueError
        new_price, new_resell_price = float(prices[0]), float(prices[1])
        plan_id = admin_temp_data[user_id]['plan_id']
        update_product_price_db(plan_id, new_price, new_resell_price)
        bot.send_message(message.chat.id, f"✅ <b>Price Updated Successfully!</b>\n\n💰 <b>New Regular Price:</b> ₹{new_price:.2f} INR\n💎 <b>New Reseller Price:</b> ₹{new_resell_price:.2f} INR", parse_mode="HTML")
        del admin_temp_data[user_id]
    except Exception:
        msg = bot.send_message(message.chat.id, "❌ <b>Format Error!</b> Enter price in format: <code>User_Price | Reseller_Price</code>\nExample: <code>200 | 150</code>")
        bot.register_next_step_handler(msg, step_edit_product_price)

def step_quick_setup(message):
    text = message.text.strip()
    try:
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        if len(lines) < 2:
            raise ValueError
            
        pid_id, hack_name = lines[0].split('|')
        pid_id, hack_name = pid_id.strip(), hack_name.strip()

        count = 0
        for line in lines[1:]:
            parts = line.split('|')
            if len(parts) == 4:
                days, server_dur, u_price, r_price = [p.strip() for p in parts]
                add_product_db(hack_name, pid_id, days, float(u_price), float(r_price), is_manual=0, remote_duration=server_dur)
                count += 1

        bot.send_message(message.chat.id, f"✅ <b>Quick Setup Completed!</b>\n\n🎮 <b>Hack:</b> {hack_name}\n🆔 <b>Product ID:</b> <code>{pid_id}</code>\n📦 <b>Plans Added:</b> {count}", parse_mode="HTML")
    except Exception:
        msg = bot.send_message(message.chat.id, "❌ <b>Format Error!</b> Please follow exact format:\n\n<code>Product_ID | Hack Name\n1 Hours | 1 Hours | 100 | 80\n1 DaYs | 1 DaYs | 500 | 400</code>")
        bot.register_next_step_handler(msg, step_quick_setup)

def step_set_tg_group_link(message):
    user_id = message.from_user.id
    p_name = admin_temp_data[user_id]['hack_name']
    group_link = message.text.strip()
    set_hack_tg_group(p_name, group_link)
    bot.send_message(message.chat.id, f"✅ <b>Telegram Group Link Set!</b>\n\n🎮 <b>Hack:</b> {p_name}\n🔗 <b>Link:</b> {group_link}", parse_mode="HTML")
    del admin_temp_data[user_id]

def step_get_reseller_uid(message):
    try:
        target_uid = int(message.text.strip())
        target_user = get_user(target_uid)
        if not target_user:
            bot.send_message(message.chat.id, "❌ User not found in database! User must start bot first.", parse_mode="HTML")
            return
        
        is_curr_reseller = target_user[11]
        markup = types.InlineKeyboardMarkup()
        if is_curr_reseller:
            markup.add(types.InlineKeyboardButton("❌ Remove Reseller Role", callback_data=f"set_resell_0_{target_uid}"))
        else:
            markup.add(types.InlineKeyboardButton("⭐ Promote to Reseller", callback_data=f"set_resell_1_{target_uid}"))
            
        bot.send_message(message.chat.id, f"👤 <b>User:</b> {target_user[1]} (<code>{target_uid}</code>)\n👑 <b>Current Role:</b> {'Reseller' if is_curr_reseller else 'Standard User'}\n\nSelect Action:", parse_mode="HTML", reply_markup=markup)
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ Invalid User ID! Enter numeric ID:")
        bot.register_next_step_handler(msg, step_get_reseller_uid)

def step_add_hack_name(message):
    user_id = message.from_user.id
    admin_temp_data[user_id] = {'name': message.text.strip()}
    msg = bot.send_message(message.chat.id, "📅 <b>Enter Day/Plan Duration Name</b> (e.g., <code>1 Hours</code>, <code>1 DaYs</code>):", parse_mode="HTML")
    bot.register_next_step_handler(msg, step_add_hack_days)

def step_add_hack_days(message):
    user_id = message.from_user.id
    admin_temp_data[user_id]['days'] = message.text.strip()
    msg = bot.send_message(message.chat.id, "💰 <b>Enter Regular User Price in INR (₹)</b> (e.g., <code>250</code>):", parse_mode="HTML")
    bot.register_next_step_handler(msg, step_add_hack_price)

def step_add_hack_price(message):
    user_id = message.from_user.id
    try:
        admin_temp_data[user_id]['price'] = float(message.text.strip())
        msg = bot.send_message(message.chat.id, "💎 <b>Enter Reseller Discounted Price in INR (₹)</b> (e.g., <code>125</code>):", parse_mode="HTML")
        bot.register_next_step_handler(msg, step_add_hack_resell_price)
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ Invalid price! Enter a valid number:")
        bot.register_next_step_handler(msg, step_add_hack_price)

def step_add_hack_resell_price(message):
    user_id = message.from_user.id
    try:
        resell_price = float(message.text.strip())
        data = admin_temp_data[user_id]
        add_product_db(data['name'], "133", data['days'], data['price'], resell_price, is_manual=0, remote_duration=data['days'])
        bot.send_message(
            message.chat.id, 
            f"✅ <b>Hack Plan Added Successfully!</b>\n\n"
            f"📦 <b>Name:</b> {data['name']}\n"
            f"📅 <b>Days:</b> {data['days']}\n"
            f"💰 <b>User Price:</b> ₹{data['price']:.2f} INR\n"
            f"💎 <b>Reseller Price:</b> ₹{resell_price:.2f} INR", 
            parse_mode="HTML"
        )
        del admin_temp_data[user_id]
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ Invalid price! Enter a valid number:")
        bot.register_next_step_handler(msg, step_add_hack_resell_price)

def step_get_add_day_to_hack(message):
    user_id = message.from_user.id
    admin_temp_data[user_id]['days'] = message.text.strip()
    msg = bot.send_message(message.chat.id, "💰 <b>Enter Regular User Price in INR (₹):</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, step_add_hack_price)

def step_get_server_token(message):
    user_id = message.from_user.id
    admin_temp_data[user_id] = {'api_key': message.text.strip()}
    msg = bot.send_message(message.chat.id, "🌐 <b>Enter Server API URL</b> (e.g., <code>https://xyzcheats.com/api/reseller_v1.php</code>):", parse_mode="HTML")
    bot.register_next_step_handler(msg, step_get_server_url)

def step_get_server_url(message):
    user_id = message.from_user.id
    server_url = message.text.strip()
    api_key = admin_temp_data[user_id]['api_key']
    
    set_setting('server_api_key', api_key)
    set_setting('server_api_url', server_url)
    
    markup = types.InlineKeyboardMarkup()
    btn_conn = types.InlineKeyboardButton("⚡ Connect & Verify API", callback_data="test_server_api_conn")
    markup.add(btn_conn)
    
    bot.send_message(message.chat.id, "✅ <b>Add Successfully!</b>\n\nClick the button below to test server connection:", parse_mode="HTML", reply_markup=markup)
    del admin_temp_data[user_id]

def step_get_remote_pid(message):
    user_id = message.from_user.id
    admin_temp_data[user_id]['pid_id'] = message.text.strip()
    msg = bot.send_message(message.chat.id, "📅 <b>Enter Server Remote Duration String</b> (e.g., <code>1 Hours</code>, <code>3 Hours</code>, <code>1 DaYs</code>):", parse_mode="HTML")
    bot.register_next_step_handler(msg, step_get_remote_duration)

def step_get_remote_duration(message):
    user_id = message.from_user.id
    remote_duration = message.text.strip()
    plan_id = admin_temp_data[user_id]['plan_id']
    pid_id = admin_temp_data[user_id]['pid_id']
    
    update_product_api_mapping(plan_id, pid_id, remote_duration)
    
    bot.send_message(
        message.chat.id,
        f"✅ <b>Server API Auto-Fallback Connected Successfully!</b>\n\n"
        f"🆔 <b>Product ID:</b> <code>{pid_id}</code>\n"
        f"📅 <b>Remote Duration:</b> <code>{remote_duration}</code>",
        parse_mode="HTML"
    )
    del admin_temp_data[user_id]

def step_get_new_bot_token(message):
    new_token = message.text.strip()
    if ":" in new_token and len(new_token) > 20:
        set_setting('bot_token', new_token)
        bot.send_message(message.chat.id, f"✅ <b>Bot API Token Updated Successfully!</b>\n\n🔑 <b>New Token Saved:</b> <code>{new_token}</code>\n\nPlease restart the python script for the new bot token to take full effect.", parse_mode="HTML")
    else:
        msg = bot.send_message(message.chat.id, "❌ Invalid Bot Token format! Enter valid Telegram Bot API Token:")
        bot.register_next_step_handler(msg, step_get_new_bot_token)

def step_get_broadcast_media(message):
    users = get_all_users()
    sent_count = 0
    caption_text = message.caption or message.text or ""
    
    for u in users:
        try:
            if message.content_type == 'photo':
                bot.send_photo(u[0], message.photo[-1].file_id, caption=caption_text, parse_mode="HTML")
            elif message.content_type == 'video':
                bot.send_video(u[0], message.video.file_id, caption=caption_text, parse_mode="HTML")
            elif message.content_type == 'audio':
                bot.send_audio(u[0], message.audio.file_id, caption=caption_text, parse_mode="HTML")
            elif message.content_type == 'text':
                bot.send_message(u[0], caption_text, parse_mode="HTML")
            sent_count += 1
        except Exception:
            pass
            
    bot.send_message(message.chat.id, f"✅ <b>Broadcast Complete!</b>\nDelivered announcement to <b>{sent_count} users</b>.", parse_mode="HTML")

def step_get_user_discount_id(message):
    user_id = message.from_user.id
    try:
        target_uid = int(message.text.strip())
        admin_temp_data[user_id] = {'target_uid': target_uid}
        msg = bot.send_message(message.chat.id, f"🏷️ <b>Enter Discount Percentage for User {target_uid}</b> (e.g., <code>20</code> for 20%):", parse_mode="HTML")
        bot.register_next_step_handler(msg, step_get_user_discount_percent)
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ Invalid User ID! Please enter numeric ID:")
        bot.register_next_step_handler(msg, step_get_user_discount_id)

def step_get_user_discount_percent(message):
    user_id = message.from_user.id
    try:
        pct = float(message.text.strip())
        target_uid = admin_temp_data[user_id]['target_uid']
        set_user_discount_db(target_uid, pct)
        bot.send_message(message.chat.id, f"✅ <b>Discount Set!</b> User <code>{target_uid}</code> will get <b>{pct}% OFF</b> on their next purchase.", parse_mode="HTML")
        
        try:
            bot.send_message(target_uid, f"🎁 <b>Congratulations!</b> You have received a special <b>{pct}% Discount</b> on your next purchase in the shop!", parse_mode="HTML")
        except Exception:
            pass
            
        del admin_temp_data[user_id]
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ Enter valid percentage number:")
        bot.register_next_step_handler(msg, step_get_user_discount_percent)

def step_get_global_discount_percent(message):
    try:
        pct = float(message.text.strip())
        set_global_discount_db(pct)
        bot.send_message(message.chat.id, f"✅ <b>Global Store Discount Set!</b> Regular users now get <b>{pct}% OFF</b> on all products.", parse_mode="HTML")
        
        users = get_all_users()
        for u in users:
            try:
                bot.send_message(u[0], f"📢 <b>DISCOUNT NOTIFICATION!</b>\n\n🎉 A new <b>Global Store Discount of {pct}% OFF</b> is now live on all products! Check the store now.", parse_mode="HTML")
            except Exception:
                pass
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ Enter valid percentage number:")
        bot.register_next_step_handler(msg, step_get_global_discount_percent)

def step_get_prod_discount_percent(message):
    user_id = message.from_user.id
    try:
        pct = float(message.text.strip())
        p_name = admin_temp_data[user_id]['prod_name']
        set_product_discount_db(p_name, pct)
        bot.send_message(message.chat.id, f"✅ <b>Product Discount Set!</b> Product <b>{p_name}</b> now has a <b>{pct}% OFF</b> discount for regular users.", parse_mode="HTML")
        
        users = get_all_users()
        for u in users:
            try:
                bot.send_message(u[0], f"📢 <b>HACK DISCOUNT ALERT!</b>\n\n🎮 <b>{p_name}</b> is now available with <b>{pct}% OFF</b> discount! Grab your key now from the store.", parse_mode="HTML")
            except Exception:
                pass
                
        del admin_temp_data[user_id]
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ Enter valid percentage number:")
        bot.register_next_step_handler(msg, step_get_prod_discount_percent)

def step_get_bal_user_id(message):
    user_id = message.from_user.id
    try:
        target_uid = int(message.text.strip())
        admin_temp_data[user_id] = {'target_uid': target_uid}
        markup = types.InlineKeyboardMarkup()
        btn_add = types.InlineKeyboardButton("➕ Add Balance", callback_data="bal_action_add")
        btn_sub = types.InlineKeyboardButton("➖ Remove Balance", callback_data="bal_action_sub")
        markup.add(btn_add, btn_sub)
        bot.send_message(message.chat.id, f"💰 <b>Selected User:</b> <code>{target_uid}</code>\nChoose action:", parse_mode="HTML", reply_markup=markup)
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ Invalid User ID!")
        bot.register_next_step_handler(msg, step_get_bal_user_id)

def step_get_bal_amount(message):
    user_id = message.from_user.id
    try:
        amt = float(message.text.strip())
        target_uid = admin_temp_data[user_id]['target_uid']
        is_add = admin_temp_data[user_id]['is_add']
        
        modify_user_balance_manual(target_uid, amt, is_add)
        user_info = get_user(target_uid)
        new_bal = user_info[4] if user_info else 0.0
        
        act_str = "Added" if is_add else "Removed"
        bot.send_message(message.chat.id, f"✅ <b>Balance Updated!</b>\n{act_str} ₹{amt:.2f} INR for User <code>{target_uid}</code>.\n💼 New Balance: ₹{new_bal:.2f} INR", parse_mode="HTML")
        try:
            bot.send_message(target_uid, f"🔔 <b>Balance Update!</b>\nAdmin {act_str.lower()} ₹{amt:.2f} INR. Your new balance is ₹{new_bal:.2f} INR.", parse_mode="HTML")
        except Exception:
            pass
        del admin_temp_data[user_id]
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ Enter valid numerical amount:")
        bot.register_next_step_handler(msg, step_get_bal_amount)

def step_get_guide_url(message):
    global guide_video_url
    new_url = message.text.strip()
    if new_url.startswith("http://") or new_url.startswith("https://"):
        guide_video_url = new_url
        set_setting('guide_url', new_url)
        bot.send_message(message.chat.id, f"✅ <b>Guide Link Updated Successfully!</b>\n\n🔗 <b>New Link:</b> {new_url}", parse_mode="HTML")
    else:
        msg = bot.send_message(message.chat.id, "❌ Invalid Link! Please enter a valid URL starting with http:// or https://")
        bot.register_next_step_handler(msg, step_get_guide_url)

def step_get_custom_topup(message):
    try:
        amount = float(message.text)
        if 1 <= amount <= 10000:
            show_topup_confirm(message.chat.id, amount)
        else:
            msg = bot.send_message(message.chat.id, "❌ <b>Invalid Amount!</b> Please enter an amount between <b>₹1</b> and <b>₹10,000</b>.", parse_mode="HTML")
            bot.register_next_step_handler(msg, step_get_custom_topup)
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ Please enter a valid numerical amount (e.g., 250):")
        bot.register_next_step_handler(msg, step_get_custom_topup)

def _extract_premium_emoji_ids(message):
    """Return Premium custom emoji IDs found in a Telegram message, in order."""
    ids = []
    try:
        for ent in (getattr(message, "entities", None) or []):
            if getattr(ent, "type", None) == "custom_emoji":
                emoji_id = getattr(ent, "custom_emoji_id", None)
                if emoji_id:
                    emoji_id = str(emoji_id)
                    if emoji_id not in ids:
                        ids.append(emoji_id)
    except Exception:
        pass
    return ids


def show_hack_price_ui_catalog(chat_id, message_id=None):
    """Admin selects a hack, then configures only its title/emojis."""
    products = get_unique_products()
    if not products:
        bot.send_message(chat_id, "⚠️ <b>No hacks/products found.</b>", parse_mode="HTML")
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    catalog = {}
    for product_name in products:
        h = _ui_hash(product_name)
        catalog[h] = product_name
        cfg = get_hack_price_ui(product_name)
        icon = "🟢" if cfg else "⚪"
        label = cfg.get("title", product_name) if cfg else product_name
        markup.add(types.InlineKeyboardButton(
            f"{icon} {label}",
            callback_data=f"hpui_select_{h}"
        ))

    admin_temp_data.setdefault(chat_id, {})["hack_price_ui_catalog"] = catalog
    text = (
        "🎨 <b>HACK PRICE LIST — PREMIUM DESIGN</b>\n\n"
        "Select a hack below.\n\n"
        "You will set ONLY:\n"
        "• Top title text\n"
        "• 2 Premium emojis beside the title\n"
        "• 1 Premium emoji for every DAY/Validity line\n\n"
        "❗ Prices, plans, stock, Auto-API, manual stock and discounts are not edited here."
    )
    if message_id:
        try:
            bot.edit_message_text(text, chat_id, message_id, parse_mode="HTML", reply_markup=markup)
            return
        except Exception:
            pass
    bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)


def step_save_hack_price_ui_title(message):
    """Compatibility entry point: now accepts the complete design in ONE message."""
    user_id = message.from_user.id
    data = admin_temp_data.get(user_id, {})
    product_name = data.get("hack_price_ui_product")
    if not product_name:
        bot.send_message(message.chat.id, "❌ Session expired. Please open Price List Fix — Emoji & Text again.")
        return
    raw = _message_html_text(message).strip()
    if not raw:
        bot.send_message(message.chat.id, "❌ Please send the complete price-list design in one message.")
        return
    # Validate that the message contains the dynamic labels we need.
    plain = re.sub(r'<[^>]+>', '', raw).lower()
    if not all(x in plain for x in ('validity', 'stock', 'price')):
        bot.send_message(
            message.chat.id,
            "❌ Your design must contain the words <b>Validity</b>, <b>Stock</b> and <b>Price</b> so the bot can inject live values automatically.",
            parse_mode="HTML"
        )
        return
    set_hack_price_ui_template(product_name, raw)
    admin_temp_data.pop(user_id, None)
    bot.send_message(
        message.chat.id,
        "✅ <b>Price List Fix Saved!</b>\n\n"
        f"🛒 <b>Hack:</b> {html.escape(product_name)}\n"
        "✨ Your Premium emojis and custom text are saved exactly as sent.\n"
        "📦 Plans/prices are automatic.\n"
        "📊 Manual / Auto-API stock is automatic.\n"
        "❌ Out of Stock is automatic.\n"
        "🏷️ Discounts are automatic.\n\n"
        "Old normal price-list text is no longer used for this hack.",
        parse_mode="HTML"
    )


def step_save_hack_price_ui_emojis(message):
    # Kept for backward compatibility with old pending sessions. New sessions use
    # step_save_hack_price_ui_title and save the whole design in one message.
    return step_save_hack_price_ui_title(message)

def step_save_premium_emoji(message):
    user_id = message.from_user.id
    target = admin_temp_data.get(user_id, {}).get("emoji_target")
    emoji_id = None
    try:
        entities = getattr(message, "entities", None) or []
        for ent in entities:
            if getattr(ent, "type", None) == "custom_emoji" and getattr(ent, "custom_emoji_id", None):
                emoji_id = str(ent.custom_emoji_id)
                break
    except Exception:
        pass

    if not emoji_id:
        bot.send_message(
            message.chat.id,
            "❌ I couldn't detect a Premium custom emoji. Please send exactly one Premium custom emoji."
        )
        return

    if target == "price_expiry":
        set_setting("price_expiry_emoji", emoji_id)
    elif target == "bulk_product_buttons":
        keys = _get_product_button_keys()
        set_bulk_button_emoji(keys, emoji_id)
    elif target == "bulk_price_buttons":
        keys = _get_price_button_keys()
        set_bulk_button_emoji(keys, emoji_id)
    elif target:
        set_button_emoji(target, emoji_id)
    else:
        bot.send_message(message.chat.id, "❌ Emoji target expired. Please open All Button Emoji again.")
        return

    if target == "bulk_product_buttons":
        saved_scope = f"all {len(_get_product_button_keys())} product buttons"
    elif target == "bulk_price_buttons":
        saved_scope = f"all {len(_get_price_button_keys())} price-list buttons"
    elif target == "price_expiry":
        saved_scope = "Price List expiry lines"
    else:
        saved_scope = "the selected button"

    bot.send_message(
        message.chat.id,
        "✅ <b>Premium Emoji Saved!</b>\n\n"
        f"Applied to <b>{saved_scope}</b>.\n"
        "Old normal leading button emojis are automatically hidden, so the Premium emoji is shown instead.",
        parse_mode="HTML"
    )
    admin_temp_data.setdefault(user_id, {}).pop("emoji_target", None)

def step_save_product_plan_text(message):
    user_id = message.from_user.id
    product_name = admin_temp_data.get(user_id, {}).get('plan_text_product')
    raw = _message_html_text(message).strip()
    if not product_name:
        bot.send_message(message.chat.id, "❌ Product selection expired. Open All Product Plan Text again.", parse_mode="HTML")
        return
    if not raw:
        bot.send_message(message.chat.id, "❌ No text received. Please send the custom text + Premium emoji again.", parse_mode="HTML")
        return
    # Save the exact HTML design, including Telegram Premium custom-emoji
    # <tg-emoji> tags. The setter also stores a migration-safe last-template alias.
    cleaned = _repair_premium_emoji_markup(raw)
    set_plan_text_product(product_name, cleaned)
    admin_temp_data[user_id] = {}
    bot.send_message(
        message.chat.id,
        "✅ <b>PRODUCT PLAN TEXT SAVED!</b>\n\n"
        f"🛒 <b>Hack:</b> {html.escape(product_name)}\n"
        "✨ Your Premium text/emoji is now the only custom price-list text for this hack.\n"
        "🤖 Days + API/Manual/Out-of-Stock status + live price are automatic.\n"
        "🧹 Old duplicated price-list/header text is not appended.",
        parse_mode="HTML"
    )


def step_save_plan_text_add(message):
    """Save the admin's custom text/header with Premium custom emojis.

    This intentionally accepts ANY text. The bot does not require Validity/Stock/Price
    lines here because those live values are generated automatically from the DB below
    the custom text."""
    user_id = message.from_user.id
    raw = _message_html_text(message).strip()
    if not raw:
        bot.send_message(
            message.chat.id,
            "❌ <b>No text received.</b> Please send the Plan Text again with your Premium emoji(s).",
            parse_mode="HTML"
        )
        return

    # Save exactly what the admin sent. No legacy price-list/sample rows are required.
    set_plan_text_add(raw)

    bot.send_message(
        message.chat.id,
        "✅ <b>PLAN TEXT SAVED!</b>\n\n"
        "📝 Your custom text + Premium emoji(s) will now appear above the live plan buttons.\n"
        "🧹 Old Plans & Pricing / Choose a Plan / legacy plan text is no longer shown.\n"
        "🤖 Days, live price, Manual/API stock and Out of Stock status remain automatic.\n\n"
        "You can send a new text anytime from the same <b>Plan Text Add + Premium Emoji</b> button.",
        parse_mode="HTML"
    )


def step_save_global_price_list_template(message):
    """Save one master price-list design containing optional Premium emojis.

    The admin can type/paste formatted Telegram text with Premium custom emojis.
    The live DB pricing is injected automatically through {pricing_info}; old
    manually typed plan rows are removed so each hack gets its own current plans.
    """
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return

    try:
        raw = _message_html_text(message).strip()
        if not raw:
            bot.send_message(message.chat.id, "❌ Please send the price-list text (with Premium emoji if needed).")
            return

        normalized = _strip_legacy_price_list_block(raw)
        set_global_price_list_template(normalized)
        # Saving the master design explicitly enables Premium Price List Mode.
        set_price_list_premium_mode(True)

        # Refresh saved product/plan colors so the new template is immediately used
        # on every hack without touching product prices or plans.
        sync_all_product_button_colors()

        bot.send_message(
            message.chat.id,
            "✅ <b>All Panel Price & Emojis Saved!</b>\n\n"
            "• Premium custom emojis are preserved.\n"
            "• Old duplicated/manual price rows are removed from the template.\n"
            "• Every hack automatically injects its own Admin-configured plans/prices.\n"
            "• Stock automatically shows Manual stock when manual keys exist, otherwise Auto-API.\n"
            "• Discounted hacks stay Green; normal hacks stay Blue.\n\n"
            "Use <code>{pricing_info}</code> anywhere you want the live price list inserted.",
            parse_mode="HTML"
        )
        admin_temp_data.setdefault(user_id, {}).pop('global_price_list_edit', None)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Could not save the master price-list template: <code>{html.escape(str(e))}</code>", parse_mode="HTML")


def _save_order_history_premium_ids(template):
    """Persist the exact Premium custom-emoji occurrence order for Order History.

    The HTML template is the primary source of truth. This ordered cache is only
    a recovery mechanism. IDs are intentionally NOT deduplicated.
    """
    ids = _premium_emoji_ids_from_template(template, unique=False)
    if ids:
        set_setting("order_history_premium_emoji_ids", json.dumps(ids, ensure_ascii=False))
    return ids


def _get_saved_order_history_premium_ids():
    try:
        ids = json.loads(get_setting("order_history_premium_emoji_ids") or "[]")
        return [str(x) for x in ids if str(x).strip()]
    except Exception:
        return []


def _build_order_history_premium_fallback(ids):
    """Build a Premium Order History design when only saved IDs are available.

    Many templates use a normal Unicode emoji for the title (ALL HISTORY) and
    Premium emojis only for the eight live/account fields. Older fallback code
    assumed ID #0 belonged to the title and shifted every following icon by one
    position. The saved 8-ID layout is therefore:
    spent, deposited, recent-orders, order-id, product, price, date/time, key.

    When a complete admin template exists, that template is ALWAYS the source of
    truth. This fallback is used only when the template itself is unavailable.
    """
    ids = [str(x).strip() for x in (ids or []) if str(x).strip()]
    if len(ids) < 8:
        return ""

    if len(ids) == 8:
        offset = 0
        title = '📜'
    else:
        offset = 1
        title = _premium_emoji_html(ids[0], '📜')

    e = lambda i, fallback: _premium_emoji_html(ids[i + offset], fallback) if i + offset < len(ids) else fallback

    return (
        f"{title} <b>ALL HISTORY</b>\n"
        f"────────────────────────\n"
        f"├── {e(0, '💎')} <b>Total spent:</b> ₹{{lifetime}} INR ({{orders}} orders)\n"
        f"└── {e(1, '📥')} <b>Total deposited:</b> ₹{{deposited}} INR\n\n"
        f"{e(2, '🛍️')} <b>Recent Orders</b>\n"
        f"────────────────────────\n"
        f"{e(3, '✅')} <b>{{order_id}}</b>\n"
        f"├── {e(4, '📦')} <b>{{product_name}}</b> · <i>{{days}}</i>\n"
        f"├── {e(5, '💰')} <b>{{price}}</b>\n"
        f"├── {e(6, '⏰')} <b>{{date_time}}</b>\n"
        f"└── {e(7, '🔑')} <code>{{key}}</code>\n"
    )



def step_save_wallet_topup_success_template(message):
    """Save the Add Balance/Wallet Top-Up success visual design."""
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return

    raw = _message_html_text(message).strip()
    if not raw:
        bot.send_message(
            message.chat.id,
            "❌ No Wallet Balance Success design received. Send the complete success layout with at least one Premium custom emoji.",
            parse_mode="HTML",
        )
        return

    premium_ids = _premium_emoji_ids_from_template(raw, unique=False)
    if not premium_ids:
        bot.send_message(
            message.chat.id,
            "❌ I couldn't detect any Premium custom emoji. Please send the Wallet Balance Success layout containing your Premium emoji(s).",
            parse_mode="HTML",
        )
        return

    set_wallet_topup_success_emoji_template(raw)
    admin_temp_data.setdefault(user_id, {}).pop("text_key", None)

    bot.send_message(
        message.chat.id,
        "✅ <b>Wallet Balance Success Premium Emoji/Text Design Saved!</b>\n\n"
        f"✨ <b>{len(premium_ids)} Premium emoji occurrence(s)</b> saved in exact order/position.\n"
        "🤖 Username, Telegram ID, Order ID, Amount, UTR and Current Balance remain live automatically.\n"
        "💰 Balance is still credited by the existing payment-verification system.\n"
        "🛡️ Existing payment/checkout logic was not removed.",
        parse_mode="HTML",
    )
    admin_temp_data.pop(user_id, None)


def step_save_wallet_payment_template(message):
    """Save the Wallet success visual design with Telegram Premium emojis."""
    _save_payment_success_emoji_template(
        message,
        payment_type="wallet",
        setter=set_wallet_payment_emoji_template,
        title="Wallet Payment",
    )


def step_save_upi_payment_template(message):
    """Save the UPI success visual design with Telegram Premium emojis."""
    _save_payment_success_emoji_template(
        message,
        payment_type="upi",
        setter=set_upi_payment_emoji_template,
        title="UPI Payment",
    )


def _save_payment_success_emoji_template(message, payment_type, setter, title):
    """Shared validator/saver for separate Wallet and UPI success templates."""
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return

    raw = _message_html_text(message).strip()
    if not raw:
        bot.send_message(
            message.chat.id,
            f"❌ No {title} design received. Send the complete success layout with at least one Premium custom emoji.",
            parse_mode="HTML",
        )
        return

    premium_ids = _premium_emoji_ids_from_template(raw, unique=False)
    if not premium_ids:
        bot.send_message(
            message.chat.id,
            "❌ I couldn't detect any Premium custom emoji. Please send the payment layout containing your Premium emoji(s).",
            parse_mode="HTML",
        )
        return

    setter(raw)
    admin_temp_data.setdefault(user_id, {}).pop("text_key", None)

    method_text = "Wallet Method" if payment_type == "wallet" else "UPI Method"
    bot.send_message(
        message.chat.id,
        f"✅ <b>{title} Premium Emoji/Text Design Saved!</b>\n\n"
        f"✨ <b>{len(premium_ids)} Premium emoji occurrence(s)</b> saved in exact order/position.\n"
        "🤖 User ID, Order ID, Product ID, Product, Plan, Amount and Key remain live.\n"
        f"💳 Payment method is automatically shown as <b>{method_text}</b>.\n"
        "🔑 The delivered key remains inside <code>&lt;code&gt;</code> so Telegram can copy it on tap.\n"
        "🛡️ Existing payment/checkout logic was not removed.",
        parse_mode="HTML",
    )
    admin_temp_data.pop(user_id, None)


def step_save_custom_text(message):
    user_id = message.from_user.id
    t_key = admin_temp_data[user_id]['text_key']
    t_val = _message_html_text(message).strip()

    if t_key == "order_history":
        # IMPORTANT: save Telegram Premium custom-emoji IDs together with the
        # exact HTML template. This prevents a later render from falling back to
        # normal Unicode emoji.
        t_val = _repair_premium_emoji_markup(t_val)
        ids = _save_order_history_premium_ids(t_val)
        set_setting("custom_text_order_history", t_val)
        bot.send_message(
            message.chat.id,
            "✅ <b>Text Updated Successfully for ID:</b> <code>order_history</code>\n\n"
            f"✨ <b>{len(ids)} Premium emoji ID(s) saved.</b>\n"
            "They will be restored automatically and the exact emoji positions will be preserved for every user's live orders.",
            parse_mode="HTML"
        )
        del admin_temp_data[user_id]
        return

    if t_key == "top_up":
        # Save Add Balance designs into the new dedicated key. This keeps the
        # old Add Balance sample/template from returning while preserving it
        # in the database for backward compatibility.
        t_val = _repair_premium_emoji_markup(t_val)
        if not _premium_emoji_ids_from_template(t_val, unique=False):
            # Some pyTelegramBotAPI versions expose the visible fallback in
            # html_text but still provide the real custom_emoji entities.
            # Rebuild once directly from Telegram's message entities so the
            # Premium IDs are not lost when the template is saved.
            try:
                t_val = _message_html_text(message).strip()
            except Exception:
                pass
            t_val = _repair_premium_emoji_markup(t_val)
        set_add_balance_text_template(t_val)
        bot.send_message(
            message.chat.id,
            "✅ <b>Add Balance Text Updated Successfully!</b>\n\n"
            "✨ Premium custom emojis and your layout are saved.\n"
            "💰 Balance, amount, minimum ₹1 and maximum ₹10,000 stay live automatically.",
            parse_mode="HTML"
        )
        del admin_temp_data[user_id]
        return

    if t_key == "top_up_qr":
        # Dedicated Add Balance QR template. It is separate from the product QR
        # template so admins can style top-ups without affecting checkout.
        set_add_balance_qr_text_template(t_val)
        bot.send_message(
            message.chat.id,
            "✅ <b>Add Balance QR Text Updated Successfully!</b>\n\n"
            "✨ Premium custom emojis and the complete QR layout are saved.\n"
            "💵 Add Amount and 🆔 Order ID are injected live for every top-up.\n"
            "⚡ Existing QR generation and auto-verification are unchanged.",
            parse_mode="HTML"
        )
        del admin_temp_data[user_id]
        return

    if t_key == "qr_payment":
        set_qr_payment_text(t_val)
        bot.send_message(
            message.chat.id,
            "✅ <b>QR BELOW TEXT UPDATED!</b>\n\n"
            "✨ Your text + Premium emoji(s) will now appear directly below every purchase QR.\n"
            "🔄 Hack name, plan, amount, purchase date and Order ID remain live and unique for each buyer.",
            parse_mode="HTML"
        )
        del admin_temp_data[user_id]
        return

    if t_key == "price_list":
        t_val = _strip_legacy_price_list_block(t_val)
        if not any(token in t_val for token in ("{pricing_info}", "{price_list}", "{prices}", "{default_price_list}")):
            t_val = t_val.rstrip() + "\n\n{pricing_info}"
        set_global_price_list_template(t_val)
        set_price_list_premium_mode(True)

    set_setting(f"custom_text_{t_key}", t_val)
    bot.send_message(message.chat.id, f"✅ <b>Text Updated Successfully for ID:</b> <code>{t_key}</code>", parse_mode="HTML")
    del admin_temp_data[user_id]


def step_save_custom_btn(message):
    user_id = message.from_user.id
    b_key = admin_temp_data[user_id]['btn_key']
    b_val = message.text.strip()
    set_setting(f"custom_btn_{b_key}", b_val)
    bot.send_message(message.chat.id, f"✅ <b>Button Name/Emoji Updated Successfully for:</b> <code>{b_key}</code>", parse_mode="HTML")
    del admin_temp_data[user_id]

def step_get_device_id_input(message):
    user_id = message.from_user.id
    if user_id not in admin_temp_data or 'checkout_pid' not in admin_temp_data[user_id]:
        bot.send_message(message.chat.id, "❌ Session expired. Please try purchasing again.")
        return

    dev_id = message.text.strip() if message.text else ""

    if dev_id.startswith('/') or dev_id.lower() in ['start', '/start', 'cancel', 'menu']:
        del admin_temp_data[user_id]
        if dev_id.lower() in ['/start', 'start']:
            send_welcome(message)
        else:
            bot.send_message(message.chat.id, "❌ <b>Purchase Cancelled!</b> Invalid Device ID provided.", parse_mode="HTML")
            show_shop_features(message.chat.id, message.from_user.first_name or "User")
        return

    product_id = admin_temp_data[user_id]['checkout_pid']
    
    del admin_temp_data[user_id]
    show_order_summary(message.chat.id, product_id, device_id=dev_id)

# ==================== MAIN SHOP UI SCREENS ====================

def _fast_callback_ack(call):
    """Acknowledge a callback immediately so Telegram clients do not feel stuck."""
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass


def render_or_edit(chat_id, message_id, text, markup):
    """Render a screen without ever deleting the current product message on error.

    Premium/custom-emoji HTML can be rejected by Telegram for some emoji IDs or
    library/API combinations. Previously the fallback deleted the existing
    product message before the fallback send completed, so a failed fallback
    made the product look as if it had disappeared.

    Recovery order:
      1) normal HTML (Premium emojis preserved)
      2) HTML with custom <tg-emoji> wrappers removed
      3) plain text with no parse mode
    The existing message is NEVER deleted as part of error recovery.
    """
    def send_or_edit_html(payload):
        if message_id:
            return bot.edit_message_text(payload, chat_id, message_id, parse_mode="HTML", reply_markup=markup)
        return bot.send_message(chat_id, payload, parse_mode="HTML", reply_markup=markup)

    try:
        send_or_edit_html(str(text))
        return
    except Exception as first_error:
        pass

    # Safe transport fallback: preserve the admin's text and all live values,
    # replacing only Telegram custom-emoji wrappers with their visible fallback.
    # Keep Premium custom-emoji wrappers during HTML recovery. The previous
    # fallback stripped them, making the price list look normal if another
    # part of the HTML payload was rejected.
    fallback_text = _repair_premium_emoji_markup(str(text))
    fallback_text = fallback_text.replace("&amp;", "&")

    try:
        send_or_edit_html(fallback_text)
        return
    except Exception:
        pass

    # Second recovery: explicitly send Telegram custom_emoji entities. This
    # keeps Premium emojis alive even when HTML parsing is the part Telegram
    # rejected. The helper is defined later in the file and is available by the
    # time any UI callback invokes render_or_edit().
    try:
        plain_text, entities = _html_to_plain_text_with_custom_emoji_entities(fallback_text)
        if message_id:
            if entities:
                bot.edit_message_text(
                    plain_text,
                    chat_id,
                    message_id,
                    entities=entities,
                    reply_markup=markup,
                )
            else:
                bot.edit_message_text(
                    plain_text,
                    chat_id,
                    message_id,
                    reply_markup=markup,
                )
        else:
            if entities:
                bot.send_message(
                    chat_id,
                    plain_text,
                    entities=entities,
                    reply_markup=markup,
                )
            else:
                bot.send_message(
                    chat_id,
                    plain_text,
                    reply_markup=markup,
                )
        return
    except Exception:
        pass

    # Last-resort recovery: do not parse HTML at all. This guarantees that a
    # bad custom template/emoji cannot make the product screen disappear.
    plain_text = re.sub(r'<tg-emoji\b[^>]*>(.*?)</tg-emoji>', lambda m: m.group(1), str(text), flags=re.I | re.S)
    plain_text = re.sub(r'<[^>]+>', '', plain_text)
    plain_text = (html.unescape(plain_text)
                  .replace("\r\n", "\n")
                  .replace("\r", "\n"))
    try:
        if message_id:
            # Telegram may reject an edit because the message contains unsupported
            # markup. Try a plain-text edit first; the old message is retained if
            # this also fails.
            bot.edit_message_text(plain_text, chat_id, message_id, reply_markup=markup)
        else:
            bot.send_message(chat_id, plain_text, reply_markup=markup)
        return
    except Exception:
        # Never delete the user's current screen. Re-raise only for logging; the
        # polling loop remains alive and the existing message stays visible.
        raise first_error


def show_shop_features(chat_id, first_name, message_id=None):
    default_shop_text = (
        f"🛍️ <b>RG CHEAT SHOP</b>\n"
        f"────────────────────────\n"
        f"👋 <i>Hello, <b>{first_name}</b>!</i>\n\n"
        f"🧡 — <b>SHOP FEATURES</b> — 🧡\n\n"
        f"├── 🔑 <b>Premium Cheats Keys</b>\n"
        f"├── ⚡ <b>Instant Delivery 24/7</b>\n"
        f"├── 🔒 <b>100% Secure Payment</b>\n"
        f"├── 🕊️ <b>Best Prices Guaranteed</b>\n"
        f"├── 🎁 <b>Invite Referral Rewards</b>\n"
        f"└── 🎭 <b>Android Root Service</b>\n\n"
        f"────────────────────────\n"
        f"🚀 <b>Click Open Store to Start!</b>"
    )
    shop_template = get_custom_text("main_menu", default_shop_text)
    shop_values = _get_user_template_values(chat_id, first_name)
    shop_values.update({
        "user": shop_values["name"],
        "telegram_id": str(chat_id),
        "number": shop_values["phone"],
        "first_name": shop_values["name"],
    })
    shop_text = _safe_format_custom_text(shop_template, **shop_values)
    shop_text = _inject_labeled_user_values(shop_text, shop_values)
    shop_text = _replace_live_greeting_name(shop_text, shop_values.get("name") or first_name)
    
    markup = types.InlineKeyboardMarkup()
    btn_open_store = make_ui_button(get_custom_btn("open_store", "🛍️ Open Store"), callback_data="open_store", button_key="main:open_store", default_color=DEFAULT_MAIN_BUTTON_COLORS["open_store"])
    btn_top_up = make_ui_button(get_custom_btn("top_up", "💰 Top Up"), callback_data="top_up", button_key="main:top_up", default_color=DEFAULT_MAIN_BUTTON_COLORS["top_up"])
    btn_orders = make_ui_button(get_custom_btn("orders", "📜 Orders"), callback_data="orders", button_key="main:orders", default_color=DEFAULT_MAIN_BUTTON_COLORS["orders"])
    btn_my_account = make_ui_button(get_custom_btn("my_account", "👤 My Account"), callback_data="my_account", button_key="main:my_account", default_color=DEFAULT_MAIN_BUTTON_COLORS["my_account"])
    btn_invite_earn = make_ui_button(get_custom_btn("invite_earn", "🎁 Invite & Earn"), callback_data="invite_earn", button_key="main:invite_earn", default_color=DEFAULT_MAIN_BUTTON_COLORS["invite_earn"])
    btn_how_to_use = make_ui_button(get_custom_btn("how_to_use", "🎬 How To Use Bot"), callback_data="how_to_use_bot", button_key="main:how_to_use", default_color=DEFAULT_MAIN_BUTTON_COLORS["how_to_use"])
    btn_all_update = make_ui_button("📢 All Update File", url=UPDATE_CHANNEL_LINK, button_key="main:all_update", default_color=DEFAULT_MAIN_BUTTON_COLORS["all_update"])
    btn_help_desk = make_ui_button(get_custom_btn("help_desk", "📞 Help Desk"), callback_data="help_desk", button_key="main:help_desk", default_color=DEFAULT_MAIN_BUTTON_COLORS["help_desk"])
    
    markup.add(btn_open_store)
    markup.add(btn_top_up, btn_orders)
    markup.add(btn_my_account, btn_invite_earn)
    markup.add(btn_how_to_use, btn_all_update)
    markup.add(btn_help_desk)
    
    render_or_edit(chat_id, message_id, shop_text, markup)

def get_product_discount_percent(product_name):
    """Return the store-wide/hack discount that controls product UI color."""
    try:
        global_disc = float(get_setting('global_discount') or '0')
    except Exception:
        global_disc = 0.0
    try:
        plans = get_product_plans(product_name)
        product_disc = max([float(p[6] or 0) for p in plans] or [0.0])
    except Exception:
        product_disc = 0.0
    return max(global_disc, product_disc)


def get_product_button_default_color(product_name):
    return "green" if get_product_discount_percent(product_name) > 0 else "blue"


def sync_product_button_colors(product_name):
    """Keep hack and all of its plan buttons in sync with discount state."""
    color = get_product_button_default_color(product_name)
    set_button_style(f"hack:{product_name}", color)
    for plan in get_product_plans(product_name):
        set_button_style(f"price:{product_name}:{plan[0]}", color)


def sync_all_product_button_colors():
    for product_name in get_unique_products():
        sync_product_button_colors(product_name)


def _strip_legacy_price_list_block(template):
    """Normalize a price-list template without duplicating the live DB price list.

    Admin-entered text is treated as the design/header. The actual plans, prices,
    stock state and discount labels always come from the products table through
    {pricing_info}. A legacy hand-written plan block is removed while its heading
    and "Choose a plan" footer are preserved in the correct order.
    """
    if not template:
        return "{pricing_info}"

    lines = str(template).splitlines()
    out = []
    in_generated_block = False
    inserted_placeholder = False

    for line in lines:
        plain = re.sub(r'<[^>]+>', '', line).lower().strip()
        is_start = (
            'plans & pricing' in plain or
            'plans and pricing' in plain or
            'stock & pricing' in plain or
            'stock and pricing' in plain
        )
        is_end = (
            'choose a plan' in plain or
            'select your plan' in plain
        )

        if is_start and not in_generated_block:
            # Keep the admin's heading, but replace everything underneath it
            # with the single live placeholder.
            out.append(line)
            out.append('{pricing_info}')
            inserted_placeholder = True
            in_generated_block = True
            continue

        if in_generated_block:
            if is_end:
                out.append(line)
                in_generated_block = False
            # All other legacy pricing lines are intentionally discarded.
            continue

        # Avoid a second copy if the admin already used the placeholder.
        if line.strip() in ('{pricing_info}', '{price_list}', '{prices}', '{default_price_list}'):
            if not inserted_placeholder:
                out.append('{pricing_info}')
                inserted_placeholder = True
            continue
        out.append(line)

    cleaned = '\n'.join(out).strip()
    if not inserted_placeholder:
        if cleaned:
            # The global editor is a design template. Append live plans exactly once.
            cleaned = cleaned.rstrip() + '\n\n{pricing_info}'
        else:
            cleaned = '{pricing_info}'
    return cleaned


def show_open_store(chat_id, message_id=None):
    default_store_text = (
        f"🛍️ <b>RG CHEAT SHOP</b>\n"
        f"────────────────────────\n"
        f"⭐ <b>Available Products</b>\n\n"
        f"├── 🔑 Premium Keys\n"
        f"├── ⚡ Instant Delivery\n"
        f"├── 🔒 Secure Payment\n"
        f"└── 🏆 24/7 Support\n\n"
        f"📦 <b>Choose your product below 👇</b>\n"
        f"<i>Tap any item to see plans & prices.</i>"
    )
    store_text = get_custom_text("store_menu", default_store_text)
    markup = types.InlineKeyboardMarkup()
    products = get_unique_products()
    if products:
        for prod in products:
            markup.add(make_ui_button(f"🛒 {prod}", callback_data=f"prod_{prod}", button_key=f"hack:{prod}", default_color=get_product_button_default_color(prod)))
    else:
        store_text += "\n\n⚠️ <i>No active products added yet. Use /admin to add products.</i>"

    btn_back = make_ui_button("⬅️ Back to Main", callback_data="back_to_main", button_key="nav:back_main", default_color="blue")
    markup.add(btn_back)
    
    render_or_edit(chat_id, message_id, store_text, markup)

def show_product_plans(chat_id, product_name, message_id=None):
    plans = get_product_plans(product_name)
    user = get_user(chat_id)

    global_disc_val = float(get_setting('global_discount') or '0.0')
    user_disc_val = user[12] if user and len(user) > 12 else 0.0
    ref_disc_used = user[15] if user and len(user) > 15 else 0
    is_reseller = user[11] if user and len(user) > 11 else 0

    pricing_info = ""
    buttons = []

    premium_price_mode = get_price_list_premium_mode()
    hack_price_ui = get_hack_price_ui(product_name)

    # Keep the first three Premium emojis from the admin's design available
    # even when the renderer falls back to the generated price-list format.
    template_for_emoji = (
        hack_price_ui.get('template') if hack_price_ui and hack_price_ui.get('template')
        else (get_global_price_list_template() if premium_price_mode else None)
    )
    template_emoji_ids = _premium_emoji_ids_from_template(template_for_emoji)
    row_validity_emoji = _premium_emoji_html(template_emoji_ids[0], '⏳') if len(template_emoji_ids) > 0 else None
    row_stock_emoji = _premium_emoji_html(template_emoji_ids[1], '📦') if len(template_emoji_ids) > 1 else None
    row_price_emoji = _premium_emoji_html(template_emoji_ids[2], '💰') if len(template_emoji_ids) > 2 else None

    if hack_price_ui:
        expiry_emoji = _premium_emoji_html(hack_price_ui.get("day_emoji"), "⏳")
    elif premium_price_mode:
        expiry_emoji = _premium_emoji_html(get_setting("price_expiry_emoji"), "⏳")
    else:
        expiry_emoji = "⏳"

    product_ui_color = get_product_button_default_color(product_name)

    # One stock query for the entire price list instead of one DB query per plan.
    stock_counts = get_key_stock_counts(product_name, [plan[2] for plan in plans])

    live_rows = []

    for plan in plans:
        p_id, pid_id, days, reg_price, resell_price, is_manual, prod_disc_val, remote_dur, tg_link, is_oos, req_dev_id = plan
        days = _clean_plan_days(days)

        if is_reseller == 1:
            final_price = resell_price
            discount_tag = " <i>(Reseller Rate)</i>"
        else:
            base_price = reg_price
            effective_discount = max(global_disc_val, prod_disc_val)
            if user_disc_val > 0 and ref_disc_used == 0:
                effective_discount = max(effective_discount, user_disc_val)
            final_price = base_price * (1 - effective_discount / 100) if effective_discount > 0 else base_price
            discount_tag = f" <i>({effective_discount:.0f}% Off)</i>" if effective_discount > 0 else ""

        stock_count = stock_counts.get(str(days), 0)

        # Determine the actual delivery source from BOTH fields. A plan with a
        # configured API product id is an API plan even if an older database row
        # still has is_manual=1. This prevents stale/manual flags from making every
        # API plan appear Out of Stock.
        pid_text = str(pid_id or '').strip()
        has_api_mapping = bool(pid_text) and pid_text != '0' and not (
            pid_text.isdigit() and int(pid_text) < 10
        )
        is_manual_plan = bool(is_manual) and not has_api_mapping

        if has_api_mapping:
            # API inventory is remote and must NOT be inferred from local panels.
            # Do not call the provider's "buy" endpoint just to render the list,
            # because that endpoint can consume a key. Actual availability is
            # confirmed during checkout.
            is_real_oos = False
            stock_status = "In Stock (Auto-API)"
        else:
            # Manual plans use the local panels inventory. Explicit OOS or an empty
            # local inventory both mean Out of Stock.
            is_real_oos = (is_oos == 1) or (stock_count <= 0)
            stock_status = (
                f"{stock_count} Available (Manual)"
                if not is_real_oos else
                "Out of Stock"
            )

        if is_real_oos:
            price_text = ""
            pricing_info += (
                f"❌ <b>{row_validity_emoji or expiry_emoji} {days} DAYS</b>\n"
                f"├── {row_stock_emoji or '📦'} <b>Stock:</b> Out of Stock\n"
                f"└── {row_price_emoji or '💰'} <b>Price:</b>\n\n"
            )
            buttons.append(make_ui_button(
                f"❌ {days} DAYS - Out of Stock",
                callback_data="out_of_stock_alert",
                button_key=f"price:{product_name}:{p_id}",
                default_color="red"
            ))
        else:
            price_text = f"₹{final_price:.2f} INR{discount_tag}"
            pricing_info += (
                f"{row_validity_emoji or expiry_emoji} <b>{days} DAYS</b>\n"
                f"├── {row_stock_emoji or '📦'} <b>Stock:</b> {stock_status}\n"
                f"└── {row_price_emoji or '💰'} <b>Price:</b> {price_text}\n\n"
            )
            buttons.append(make_ui_button(
                f"🛒 Buy {days} DAYS - ₹{final_price:.2f}",
                callback_data=f"checkout_{p_id}",
                button_key=f"price:{product_name}:{p_id}",
                default_color=product_ui_color
            ))

        live_rows.append({
            "days": days,
            "stock_status": stock_status,
            "price_text": price_text,
            "out_of_stock": is_real_oos,
        })

    default_plan_text = (
        f"🛒 <b>{html.escape(str(product_name))}</b>\n\n"
        f"📊 <b>STOCK &amp; PRICING :</b>\n\n"
        f"{pricing_info}"
        f"🎯 <b>CHOOSE A PLAN</b> 🎯"
    )

    # Per-product custom text has absolute priority. It replaces every old
    # header/price-list design for this hack. No legacy text is appended.
    product_plan_text = get_plan_text_product(product_name)
    if product_plan_text:
        plan_text = _render_plan_text_product(product_plan_text, live_rows, product_name)
    else:
        # Backward-compatible fallback for products not yet configured through
        # the new All Product Plan Text editor.
        plan_text_add = get_plan_text_add()
        if plan_text_add:
            custom_header = _safe_format_custom_text(
                plan_text_add,
                product_name=product_name,
                hack=product_name,
                pricing_info=pricing_info,
                price_list=pricing_info,
                prices=pricing_info,
                default_price_list=default_plan_text,
            )
            plan_text = custom_header.rstrip() + "\n\n" + pricing_info.strip()
        elif hack_price_ui and hack_price_ui.get('template'):
            rendered = _render_hack_price_ui_template(
                hack_price_ui.get('template'), live_rows, product_name
            )
            plan_text = rendered or pricing_info.strip()
        else:
            # No custom design: show only the live plan rows, without legacy
            # product/header/choose-a-plan text.
            plan_text = pricing_info.strip()

    markup = types.InlineKeyboardMarkup()
    for btn in buttons:
        markup.add(btn)
    markup.add(make_ui_button(
        "⬅️ Back to Store",
        callback_data="open_store",
        button_key="nav:back_store",
        default_color="blue"
    ))

    render_or_edit(chat_id, message_id, plan_text, markup)


def show_order_summary(chat_id, product_id, message_id=None, device_id=None):
    product = get_product_by_id(product_id)
    if not product:
        bot.send_message(chat_id, "❌ Product not found.")
        return

    prod_name = product[1]
    prod_days = product[3]
    reg_price = product[4]
    resell_price = product[5]
    prod_disc_val = product[7]

    user = get_user(chat_id)
    user_bal = user[4] if user else 0.0
    user_name = user[1] if user and len(user) > 1 else "User"
    user_phone = user[2] if user and len(user) > 2 and user[2] else "N/A"
    global_disc_val = float(get_setting('global_discount') or '0.0')
    user_disc_val = user[12] if user and len(user) > 12 else 0.0
    ref_disc_used = user[15] if user and len(user) > 15 else 0
    is_reseller = user[11] if user and len(user) > 11 else 0

    if is_reseller == 1:
        final_price = resell_price
    else:
        base_price = reg_price
        effective_discount = max(global_disc_val, prod_disc_val)
        if user_disc_val > 0 and ref_disc_used == 0:
            effective_discount = max(effective_discount, user_disc_val)
        final_price = base_price * (1 - effective_discount / 100) if effective_discount > 0 else base_price

    dev_line = f"├── 📱 <b>Device ID:</b> <code>{device_id}</code>\n" if device_id else ""
    default_summary_text = (
        f"🧾 <b>ORDER SUMMARY</b>\n"
        f"────────────────────────\n"
        f"├── 👤 <b>Name:</b> {user_name}\n"
        f"├── 🆔 <b>User ID:</b> <code>{chat_id}</code>\n"
        f"├── 📞 <b>Phone:</b> <code>{user_phone}</code>\n"
        f"├── 📦 <b>Product:</b> 🛒 {prod_name}\n"
        f"├── 🏷️ <b>Plan:</b> {prod_days}\n"
        f"{dev_line}"
        f"├── 🔢 <b>Quantity:</b> 1\n"
        f"└── 💵 <b>Unit price:</b> ₹{final_price:.2f} INR\n"
        f"────────────────────────\n"
        f"💼 <b>Your Balance: ₹{user_bal:.2f} INR</b>\n"
        f"💳 <b>Final Total: ₹{final_price:.2f} INR</b>\n\n"
        f"👇 <b>Choose your payment method</b>"
    )
    order_template = get_custom_text("order_summary", default_summary_text)
    order_summary_text = _safe_format_custom_text(
        order_template,
        user=user_name,
        name=user_name,
        user_id=chat_id,
        telegram_id=chat_id,
        phone=user_phone,
        number=user_phone,
        product_name=prod_name,
        hack=prod_name,
        plan=prod_days,
        amount=f"{final_price:.2f}",
        balance=f"{user_bal:.2f}",
        device_id=device_id or "",
        default_order_summary=default_summary_text,
    )
    live_username = _get_live_telegram_username(chat_id)
    order_summary_text = _inject_labeled_user_values(
        order_summary_text,
        {
            "name": html.escape(str(user_name), quote=False),
            "username": html.escape(str(live_username), quote=False),
            "username_at": html.escape(f"@{live_username}" if live_username else "", quote=False),
            "user_id": str(chat_id),
            "phone": html.escape(str(user_phone), quote=False),
            "balance": f"{user_bal:.2f}",
            "product_name": html.escape(str(prod_name), quote=False),
            "plan": html.escape(str(prod_days), quote=False),
            "amount": f"₹{final_price:.2f} INR",
        }
    )

    markup = types.InlineKeyboardMarkup()
    dev_param = f":{device_id}" if device_id else ""
    if user_bal >= final_price:
        btn_wallet = make_ui_button(
            f"💳 Pay via Wallet — ₹{final_price:.2f}",
            callback_data=f"pay_wallet_{product_id}{dev_param}",
            button_key="payment:wallet",
            default_color="blue"
        )
        markup.add(btn_wallet)

    btn_upi = make_ui_button(
        f"🇮🇳 Pay via UPI — ₹{final_price:.2f}",
        callback_data=f"pay_upi_{product_id}{dev_param}",
        button_key="payment:upi",
        default_color="blue"
    )
    btn_back = make_ui_button("🔙 Back to Store", callback_data="open_store", button_key="nav:back_store", default_color="blue")
    markup.add(btn_upi)
    markup.add(btn_back)
    render_or_edit(chat_id, message_id, order_summary_text, markup)

def process_wallet_checkout(chat_id, user_id, product_id, device_id=None):
    product = get_product_by_id(product_id)
    if not product:
        bot.send_message(chat_id, "❌ Product not found!")
        return

    first_name = "User"
    user_info = get_user(user_id)
    if user_info:
        first_name = user_info[1]

    prod_name = product[1]
    prod_days = product[3]
    reg_price = product[4]
    resell_price = product[5]
    prod_disc_val = product[7]
    pid_id = product[2] if product[2] and product[2] != '0' else '133'
    remote_dur = product[8] if len(product) > 8 and product[8] else prod_days
    tg_group_link = product[9] if len(product) > 9 and product[9] else ""

    user = get_user(user_id)
    global_disc_val = float(get_setting('global_discount') or '0.0')
    user_disc_val = user[12] if user and len(user) > 12 else 0.0
    ref_disc_used = user[15] if user and len(user) > 15 else 0
    is_reseller = user[11] if user and len(user) > 11 else 0

    if is_reseller == 1:
        final_price = resell_price
    else:
        base_price = reg_price
        effective_discount = max(global_disc_val, prod_disc_val)
        if user_disc_val > 0 and ref_disc_used == 0:
            effective_discount = max(effective_discount, user_disc_val)
        final_price = base_price * (1 - effective_discount / 100) if effective_discount > 0 else base_price

    if deduct_user_balance(user_id, final_price):
        order_id = "WAL" + datetime.datetime.now().strftime("%Y%m%d%H%M%S") + str(random.randint(1000, 9999))
        
        key_val = fetch_and_claim_manual_key(prod_name, prod_days)
        if not key_val:
            key_val = fetch_key_from_api(pid_id, remote_dur, android_id=device_id)
        if not key_val:
            key_val = "⚠️ Key assigned! Check orders history or contact Admin."

        record_order(order_id, user_id, prod_name, prod_days, final_price, key_val)
        notify_admins_purchase(user_id, first_name, order_id, prod_name, prod_days, final_price, device_id)
        
        if user and user[12] > 0 and user[15] == 0:
            mark_ref_discount_used(user_id)

        dev_info = f"📱 <b>Device ID:</b> <code>{device_id}</code>\n" if device_id else ""

        wallet_template = get_wallet_payment_emoji_template()
        if wallet_template:
            success_msg = _render_wallet_payment_emoji_template(
                wallet_template,
                user_id=user_id,
                order_id=order_id,
                product_id=product[0],
                product_name=prod_name,
                plan=prod_days,
                amount=final_price,
                key_val=key_val,
                pay_type="wallet",
                device_id=device_id,
            )
        else:
            success_msg = (
                f"💰 <b>WALLET PAYMENT SUCCESSFUL</b> 💰\n"
                f"<i>Instant Key Delivery!</i>\n\n"
                f"📋 <b>ORDER DETAILS</b>\n"
                f"├── 👤 <b>User ID:</b> <code>{user_id}</code>\n"
                f"├── 🆔 <b>Order ID:</b> <code>{order_id}</code>\n"
                f"├── 🛒 <b>Product ID:</b> <code>{product[0]}</code>\n"
                f"├── 🎮 <b>Product:</b> {html.escape(str(prod_name))}\n"
                f"├── ⏱️ <b>Plan:</b> {html.escape(str(prod_days))}\n"
                f"├── 💳 <b>Method:</b> 💼 Wallet Balance\n"
                f"{dev_info}"
                f"└── 💵 <b>Paid:</b> ₹{final_price:.2f} INR\n\n"
                f"🔑 <b>YOUR KEY:</b>\n"
                f"<code>{html.escape(str(key_val))}</code>\n\n"
                f"💡 <i>Tap the key above to copy instantly.</i>"
            )

        markup = types.InlineKeyboardMarkup()
        if tg_group_link:
            markup.add(make_ui_button("🔗 Join Telegram Group", url=tg_group_link, button_key="link:telegram_group", default_color="blue"))
        markup.add(make_ui_button("🏠 Main Menu", callback_data="back_to_main_new", button_key="nav:success_main_menu", default_color="blue"))

        _send_payment_success_safely(chat_id, success_msg, reply_markup=markup)
    else:
        bot.send_message(chat_id, "❌ Insufficient wallet balance!")

def show_upi_checkout(chat_id, product_id, message_id=None, device_id=None):
    if message_id:
        try:
            bot.delete_message(chat_id, message_id)
        except Exception:
            pass

    product = get_product_by_id(product_id)
    if not product:
        bot.send_message(chat_id, "❌ Product not found.")
        return

    prod_name = product[1]
    prod_days = product[3]
    reg_price = product[4]
    resell_price = product[5]
    prod_disc_val = product[7]

    user = get_user(chat_id)
    global_disc_val = float(get_setting('global_discount') or '0.0')
    user_disc_val = user[12] if user and len(user) > 12 else 0.0
    ref_disc_used = user[15] if user and len(user) > 15 else 0
    is_reseller = user[11] if user and len(user) > 11 else 0

    if is_reseller == 1:
        final_price = resell_price
    else:
        base_price = reg_price
        effective_discount = max(global_disc_val, prod_disc_val)
        if user_disc_val > 0 and ref_disc_used == 0:
            effective_discount = max(effective_discount, user_disc_val)
        final_price = base_price * (1 - effective_discount / 100) if effective_discount > 0 else base_price

    qr_url, order_ref = create_fam_qr(final_price)

    # This timestamp is created once for this purchase screen and is used only for
    # this buyer's live QR caption. It is never written into the shared template.
    purchase_dt = datetime.datetime.now()
    purchase_date = purchase_dt.strftime("%A, %d %b %Y")
    dev_info = f"├── 📱 <b>Device ID:</b> <code>{html.escape(str(device_id))}</code>\n" if device_id else ""

    # Once the admin has saved a QR-below template, that template is the
    # COMPLETE text below the QR. The old Order Details/How to Pay blocks are
    # not appended, so old normal text/emojis cannot remain underneath it.
    if _has_custom_qr_payment_text():
        qr_custom_template = get_setting(QR_PAYMENT_TEXT_KEY) or ''
        caption_text = _render_qr_payment_text(
            qr_custom_template,
            prod_name=prod_name,
            prod_days=prod_days,
            amount=final_price,
            order_id=order_ref,
            purchase_date=purchase_date,
            device_id=device_id,
        )
    else:
        # Legacy fallback is kept unchanged until the admin configures the
        # QR-below custom template.
        caption_parts = []
        caption_parts.append(
            "📦 <b>Order Details:</b>\n"
            f"├── 🎮 <b>Product:</b> {html.escape(str(prod_name), quote=False)}\n"
            f"├── ⏱️ <b>Plan:</b> {html.escape(str(prod_days), quote=False)}\n"
            f"├── 💰 <b>Amount:</b> ₹{final_price:.2f} INR\n"
            f"{dev_info}"
            f"├── 📅 <b>Purchase Date:</b> {html.escape(purchase_date, quote=False)}\n"
            f"└── 🆔 <b>Order ID:</b> <code>{html.escape(str(order_ref), quote=False)}</code>"
        )
        caption_parts.append(
            "📱 <b>How to Pay:</b>\n"
            "├── 1️⃣ Scan the QR Code above using GPay, PhonePe, Paytm or FamPay\n"
            f"├── 2️⃣ Pay exact amount: <b>₹{final_price:.2f}</b>\n"
            "└── 3️⃣ Wait a few seconds for auto-verification!"
        )
        caption_parts.append(
            "────────────────────────\n"
            "⚡ <i>Auto-checking live payment in background...</i>"
        )
        caption_text = "\n\n".join(caption_parts)

    markup = types.InlineKeyboardMarkup()
    btn_back = make_ui_button("🔙 Back to Store", callback_data="back_from_qr", button_key="nav:back_qr", default_color="blue")
    markup.add(btn_back)

    sent_msg = bot.send_photo(chat_id, photo=qr_url, caption=caption_text, parse_mode="HTML", reply_markup=markup)
    
    active_orders[order_ref] = {
        'chat_id': chat_id,
        'user_id': chat_id,
        'message_id': sent_msg.message_id,
        'amount': final_price,
        'pay_type': "purchase",
        'product_id': product_id,
        'device_id': device_id
    }

    threading.Thread(target=poll_payment_in_bot, args=(chat_id, chat_id, sent_msg.message_id, order_ref, final_price, "purchase", product_id, device_id), daemon=True).start()

def _get_topup_keypad_amount(chat_id):
    try:
        return max(0, min(int(topup_keypad_state.get(int(chat_id), 0) or 0), 10000))
    except (TypeError, ValueError):
        return 0

def _set_topup_keypad_amount(chat_id, amount):
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        amount = 0
    topup_keypad_state[int(chat_id)] = max(0, min(amount, 10000))
    return topup_keypad_state[int(chat_id)]

def _clear_topup_keypad_state(chat_id):
    topup_keypad_state.pop(int(chat_id), None)

# Add Balance has its own template key so an old saved Add Balance layout
# cannot reappear after the UI was redesigned. Existing settings/data are kept.
ADD_BALANCE_TEXT_V2_KEY = "add_balance_text_v2"

# Separate Add Balance QR caption design. This is intentionally independent from
# the normal purchase QR text so admins can make the top-up screen match the
# Premium purchase/payment design without changing product checkout.
ADD_BALANCE_QR_TEXT_KEY = "add_balance_qr_text_v2"

DEFAULT_ADD_BALANCE_QR_TEXT = (
    "💰 <b>ADD BALANCE PAYMENT GATEWAY</b> 💰\n"
    "<i>Scan & Pay — Instant Wallet Credit</i>\n\n"
    "📋 <b>DEPOSIT DETAILS</b>\n"
    "├── 💵 <b>Add Amount:</b> {add_amount}\n"
    "└── 🆔 <b>Order ID:</b> <code>{order_id}</code>\n\n"
    "⏱️ <b>Expires in 5 minutes</b>\n"
    "🔥 <b>Instant Verification</b>\n\n"
    "💳 <b>How to Pay</b>\n"
    "➜ Scan the QR code above using any UPI App.\n"
    "➜ Pay the exact amount: <b>{add_amount}</b>\n"
    "➜ Your payment will be verified automatically!\n\n"
    "────────────────────────\n"
    "⚡ <i>Auto-checking live payment in background...</i>"
)

def get_add_balance_qr_text_template():
    return get_setting(ADD_BALANCE_QR_TEXT_KEY) or DEFAULT_ADD_BALANCE_QR_TEXT

def set_add_balance_qr_text_template(template):
    cleaned = _repair_premium_emoji_markup(str(template or "").strip())
    set_setting(ADD_BALANCE_QR_TEXT_KEY, cleaned)

def _render_add_balance_qr_text(amount, order_id):
    """Render the Add Balance QR caption with live amount/order ID.

    The saved template is presentation-only. Premium custom emojis and HTML
    formatting are preserved while transaction values are always generated live.
    """
    try:
        amount_value = float(amount)
    except (TypeError, ValueError):
        amount_value = 0.0

    live_amount = f"₹{amount_value:.2f} INR"
    purchase_date = datetime.datetime.now().strftime("%A, %d %b %Y %H:%M:%S")
    values = {
        "amount": live_amount,
        "add_amount": live_amount,
        "topup_amount": live_amount,
        "order_id": html.escape(str(order_id), quote=False),
        "date": html.escape(purchase_date, quote=False),
        "purchase_date": html.escape(purchase_date, quote=False),
    }

    rendered = _repair_premium_emoji_markup(get_add_balance_qr_text_template())
    rendered = _safe_format_custom_text(rendered, **values)

    # If the admin pasted an already-rendered sample instead of placeholders,
    # replace the labelled transaction fields with the current live values.
    rendered = _inject_labeled_user_values(
        rendered,
        {
            "amount": live_amount,
            "add_amount": live_amount,
            "topup_amount": live_amount,
            "order_id": html.escape(str(order_id), quote=False),
            "date": html.escape(purchase_date, quote=False),
        },
    )

    rendered = re.sub(
        r'(?im)^([^\n]*\b(?:Add\s+Amount|Amount\s+Adding|Top[- ]?up\s+Amount|Amount)\b[^:\n]*:\s*)[^\n]*$',
        lambda m: m.group(1) + live_amount,
        rendered,
    )
    rendered = re.sub(
        r'(?im)^([^\n]*\bOrder\s+ID\b[^:\n]*:\s*)[^\n]*$',
        lambda m: m.group(1) + f'<code>{html.escape(str(order_id), quote=False)}</code>',
        rendered,
    )
    return _repair_telegram_html_markup(_repair_premium_emoji_markup(rendered).strip())

DEFAULT_ADD_BALANCE_TEXT = (
    "💰 <b>ADD BALANCE TO WALLET</b>\n"
    "💸 <b>Current balance :</b> ₹{balance} INR\n\n"
    "📉 <b>Minimum Deposit :</b> ₹1 INR\n\n"
    "↗️ <b>Maximum Deposit :</b> ₹10,000\n\n"
    "💎 <b>Amount:</b> {amount}\n\n"
    "👑 <i>Use the keypad below to enter amount</i>"
)

def get_add_balance_text_template():
    # Only the new editor/template is used. The legacy custom_text_top_up
    # remains stored but is intentionally not rendered by the Add Balance UI.
    return get_setting(ADD_BALANCE_TEXT_V2_KEY) or DEFAULT_ADD_BALANCE_TEXT

def set_add_balance_text_template(template):
    cleaned = _repair_premium_emoji_markup(str(template or "").strip())
    # Never convert Premium custom emojis to normal Unicode in the saved
    # template; keep their Telegram <tg-emoji emoji-id="..."> wrappers intact.
    set_setting(ADD_BALANCE_TEXT_V2_KEY, cleaned)

def _render_add_balance_keypad_text(chat_id, amount=None):
    # Every value here is resolved per-user/per-render; no user's balance is
    # ever stored in the shared presentation template.
    user = get_user(chat_id)
    curr_bal = float(user[4] if user else 0.0)
    amount = _get_topup_keypad_amount(chat_id) if amount is None else int(amount)

    template = get_add_balance_text_template()
    values = _get_user_template_values(chat_id, user[1] if user else None)
    live_amount = f"₹{amount} INR"
    live_balance = f"{curr_bal:.2f}"

    values.update({
        "user": values.get("name", "User"),
        "first_name": values.get("name", "User"),
        "balance": live_balance,
        "current_balance": f"₹{live_balance} INR",
        "amount": live_amount,
        "add_amount": live_amount,
        "topup_amount": live_amount,
        "after_deposit": f"₹{curr_bal + amount:.2f} INR",
        "minimum_deposit": "₹1 INR",
        "max_deposit": "₹10,000",
        "maximum_deposit": "₹10,000",
    })

    text = _safe_format_custom_text(template, **values)

    # Force transaction/account fields to stay live even if the admin copied
    # an old rendered sample into the new editor.
    text = _inject_labeled_user_values(text, {
        "name": values.get("name", "User"),
        "username": values.get("username", ""),
        "username_at": values.get("username_at", ""),
        "user_id": str(chat_id),
        "phone": values.get("phone", "N/A"),
        "country": values.get("country", "IN"),
        "balance": f"₹{live_balance} INR",
        "ref_balance": values.get("ref_balance", "0.00"),
        "orders": values.get("orders", "0"),
        "lifetime": values.get("lifetime", "0.00"),
        "deposited": values.get("deposited", "0.00"),
        "joined": values.get("joined", "N/A"),
        "amount": live_amount,
        "add_amount": live_amount,
        "topup_amount": live_amount,
        "after_deposit": f"₹{curr_bal + amount:.2f} INR",
    })

    # These limits are fixed by the requested Add Balance rules.
    text = re.sub(
        r'(?im)^([^\n]*\b(?:Minimum|Min)\s+Deposit\b[^:\n]*:\s*)[^\n]*$',
        lambda m: m.group(1) + "₹1 INR",
        text,
    )
    text = re.sub(
        r'(?im)^([^\n]*\b(?:Maximum|Max)\s+Deposit\b[^:\n]*:\s*)[^\n]*$',
        lambda m: m.group(1) + "₹10,000",
        text,
    )
    text = re.sub(
        r'(?im)^([^\n]*\b(?:Amount|Adding|Amount Adding|Top[- ]?up Amount)\b[^:\n]*:\s*)[^\n]*$',
        lambda m: m.group(1) + live_amount,
        text,
    )

    return _repair_premium_emoji_markup(text).strip()

def _build_add_balance_keypad_markup():
    markup = types.InlineKeyboardMarkup(row_width=3)
    for row in ((1, 2, 3), (4, 5, 6), (7, 8, 9)):
        markup.row(*[
            make_ui_button(str(d), callback_data=f"topkey_d_{d}",
                           button_key=f"topkey:{d}", default_color="blue")
            for d in row
        ])
    markup.row(
        make_ui_button("❌ Cancel", callback_data="topkey_clear",
                       button_key="topkey:cancel", default_color="red"),
        make_ui_button("0", callback_data="topkey_d_0",
                       button_key="topkey:0", default_color="blue"),
        make_ui_button("💳 Confirm", callback_data="topkey_confirm",
                       button_key="topkey:confirm", default_color="green"),
    )
    markup.add(make_ui_button("❌ Back", callback_data="topkey_back",
                              button_key="nav:back_topup", default_color="red"))
    return markup

def show_topup_options(chat_id, message_id=None):
    _set_topup_keypad_amount(chat_id, 0)
    render_or_edit(
        chat_id, message_id,
        _render_add_balance_keypad_text(chat_id, 0),
        _build_add_balance_keypad_markup()
    )

def _html_to_plain_text_with_custom_emoji_entities(html_text):
    """Build plain text + Telegram custom-emoji entities as an edit fallback.

    The normal path uses HTML so the saved Add Balance design keeps all
    formatting and Premium custom emojis. If Telegram rejects that HTML during
    an edit, this fallback uses explicit custom_emoji MessageEntity objects so
    the Premium IDs are still preserved and the keypad remains live.
    """
    value = _repair_premium_emoji_markup(str(html_text or ""))
    plain_parts = []
    entities = []
    cursor_utf16 = 0
    pos = 0

    tag_re = re.compile(
        r'<tg-emoji\s+emoji-id=["\']([^"\']+)["\']>(.*?)</tg-emoji>',
        re.I | re.S
    )

    def utf16_len(text):
        return len(str(text).encode("utf-16-le")) // 2

    for match in tag_re.finditer(value):
        before = value[pos:match.start()]
        before_plain = html.unescape(re.sub(r'<[^>]+>', '', before))
        plain_parts.append(before_plain)
        cursor_utf16 += utf16_len(before_plain)

        visible = html.unescape(re.sub(r'<[^>]+>', '', match.group(2)))
        emoji_id = str(match.group(1)).strip()
        if visible and emoji_id:
            entities.append(
                types.MessageEntity(
                    type="custom_emoji",
                    offset=cursor_utf16,
                    length=utf16_len(visible),
                    custom_emoji_id=emoji_id,
                )
            )
        plain_parts.append(visible)
        cursor_utf16 += utf16_len(visible)
        pos = match.end()

    tail = value[pos:]
    tail_plain = html.unescape(re.sub(r'<[^>]+>', '', tail))
    plain_parts.append(tail_plain)
    return ''.join(plain_parts), entities


def _update_topup_keypad_message(chat_id, message_id):
    """Update the same Add Balance message immediately after every digit.

    The old code swallowed every edit error, so an HTML/custom-emoji parsing
    failure left the user seeing the old ₹0 forever. The amount is now stored
    first and the edit has two safe fallbacks.
    """
    text = _render_add_balance_keypad_text(chat_id)
    markup = _build_add_balance_keypad_markup()

    # 1) Normal HTML path: complete saved design + Premium emojis.
    try:
        bot.edit_message_text(
            text,
            chat_id,
            message_id,
            parse_mode="HTML",
            reply_markup=markup,
        )
        return True
    except Exception as html_error:
        last_error = html_error

    # 2) Explicit custom-emoji entities: Premium IDs survive even when the
    # HTML parser rejects the payload.
    try:
        plain_text, entities = _html_to_plain_text_with_custom_emoji_entities(text)
        if entities:
            bot.edit_message_text(
                plain_text,
                chat_id,
                message_id,
                entities=entities,
                reply_markup=markup,
            )
        else:
            bot.edit_message_text(
                plain_text,
                chat_id,
                message_id,
                reply_markup=markup,
            )
        return True
    except Exception as entity_error:
        last_error = entity_error

    # 3) Last-resort plain-text edit keeps the keypad functional for very old
    # Telegram libraries. This path is only reached if both richer transports
    # fail; the Premium-emoji design remains saved for the next render.
    try:
        plain_text = re.sub(
            r'<tg-emoji\b[^>]*>(.*?)</tg-emoji>',
            lambda m: m.group(1),
            text,
            flags=re.I | re.S,
        )
        plain_text = re.sub(r'<[^>]+>', '', plain_text)
        plain_text = html.unescape(plain_text)
        bot.edit_message_text(
            plain_text,
            chat_id,
            message_id,
            reply_markup=markup,
        )
        return True
    except Exception:
        print(
            f"[TOPUP UI] Failed to update chat={chat_id}, message={message_id}: "
            f"{last_error!r}"
        )
        return False

def show_topup_confirm(chat_id, amount, message_id=None):
    # Legacy callback compatibility: seed the new keypad instead of showing
    # the old fixed payment-method screen.
    try:
        amount = int(float(amount))
    except (TypeError, ValueError):
        amount = 0
    if 1 <= amount <= 10000:
        _set_topup_keypad_amount(chat_id, amount)
        if message_id:
            _update_topup_keypad_message(chat_id, message_id)
        else:
            show_topup_options(chat_id)
    else:
        show_topup_options(chat_id, message_id=message_id)

def show_topup_upi_screen(chat_id, amount, message_id=None):
    try:
        amount = int(float(amount))
    except (TypeError, ValueError):
        amount = 0
    if not 1 <= amount <= 10000:
        show_topup_options(chat_id, message_id=message_id)
        return

    _clear_topup_keypad_state(chat_id)
    if message_id:
        try:
            bot.delete_message(chat_id, message_id)
        except Exception:
            pass

    qr_url, order_ref = create_fam_qr(amount)
    # Add Balance now uses its own Premium-editable QR design. The live amount
    # and gateway Order ID are injected on every request, exactly like product
    # checkout, so a copied admin sample can never leak an old transaction.
    caption_text = _render_add_balance_qr_text(amount, order_ref)
    markup = types.InlineKeyboardMarkup()
    markup.add(make_ui_button("🔙 Back to Main", callback_data="back_from_qr",
                              button_key="nav:back_qr", default_color="blue"))
    sent_msg = bot.send_photo(chat_id, photo=qr_url, caption=caption_text,
                              parse_mode="HTML", reply_markup=markup)
    active_orders[order_ref] = {
        "chat_id": chat_id, "user_id": chat_id,
        "message_id": sent_msg.message_id, "amount": amount,
        "pay_type": "topup", "product_id": 0
    }
    threading.Thread(
        target=poll_payment_in_bot,
        args=(chat_id, chat_id, sent_msg.message_id, order_ref, amount, "topup", 0),
        daemon=True
    ).start()

def show_help_desk(chat_id, message_id=None):
    default_help_text = (
        f"🛟 <b>RG CHEAT SHOP — Support</b>\n\n"
        f"🎧 <i>Our team is here to help you.</i>\n\n"
        f"<b>We can assist with:</b>\n"
        f"├── 🔑 Orders & key delivery\n"
        f"├── 💰 Payments & balance\n"
        f"├── ❓ Product questions\n"
        f"└── ⚙️ Any other issue\n\n"
        f"⏱️ <i>Typical reply time: within a few hours.</i>\n\n"
        f"<i>Tap a button below to contact us directly 👇</i>"
    )
    help_template = get_custom_text("help_desk", default_help_text)
    help_user = get_user(chat_id)
    help_name = help_user[1] if help_user else "User"
    help_phone = help_user[2] if help_user and len(help_user) > 2 and help_user[2] else "N/A"
    help_text = _safe_format_custom_text(
        help_template,
        user=help_name,
        name=help_name,
        user_id=chat_id,
        telegram_id=chat_id,
        phone=help_phone,
        number=help_phone,
    )

    markup = types.InlineKeyboardMarkup()
    btn_telegram = make_ui_button("💬 Chat on Telegram", url=f"https://t.me/{TELEGRAM_USER}", button_key="link:telegram_support", default_color="blue")
    btn_whatsapp = make_ui_button("📱 Chat on WhatsApp", url=f"https://wa.me/{WHATSAPP_NUM}", button_key="link:whatsapp_support", default_color="green")
    btn_back = make_ui_button("🔙 Back to Main", callback_data="back_to_main", button_key="nav:back_main", default_color="blue")

    markup.add(btn_telegram)
    markup.add(btn_whatsapp)
    markup.add(btn_back)

    render_or_edit(chat_id, message_id, help_text, markup)

def show_how_to_use_bot(chat_id, message_id=None):
    global guide_video_url
    markup = types.InlineKeyboardMarkup()
    
    if guide_video_url:
        default_guide_text = (
            f"🎬 <b>HOW TO USE BOT</b>\n"
            f"────────────────────────\n\n"
            f"Watch our complete tutorial video to learn how to purchase, top-up balance, and claim your cheat keys automatically!\n\n"
            f"👇 <b>Click the button below to watch guide:</b>"
        )
        markup.add(make_ui_button("▶️ Watch Guide Video", url=guide_video_url, button_key="link:guide", default_color="blue"))
    else:
        default_guide_text = (
            f"🎬 <b>HOW TO USE BOT</b>\n"
            f"────────────────────────\n\n"
            f"ℹ️ <i>Tutorial video guide is currently being updated! Please check back soon.</i>\n\n"
            f"For immediate help, contact support using <b>Help Desk</b>."
        )

    # Admin can now edit this entire text section from Text Editor, including
    # Telegram Premium custom emojis. The saved template is presentation-only;
    # the guide URL/button remains controlled separately by the existing setting.
    guide_text = get_custom_text("how_to_use", default_guide_text)

    btn_back = make_ui_button("🔙 Back to Main", callback_data="back_to_main", button_key="nav:back_main", default_color="blue")
    markup.add(btn_back)

    render_or_edit(chat_id, message_id, guide_text, markup)

def _render_order_history_custom_template(template, orders):
    """Render live Order History from the admin's exact Premium-emoji skeleton.

    The admin message is a visual template, not a data record. Premium emoji
    markup is copied from the exact sample line where it was configured.
    Live values are injected semantically (or by the explicit placeholder) so
    an emoji can never be reassigned merely because another emoji was added or
    removed elsewhere in the message.

    Supported live placeholders:
      {order_id}, {product_name}/{hack}, {days}/{plan_days},
      {price}/{amount}, {date_time}/{date}, {key}/{purchased_key}.
    """
    if not template:
        return ""

    text = _repair_premium_emoji_markup(str(template).strip())
    if "{orders_list}" in text or "{{orders_list}}" in text:
        token = "{orders_list}" if "{orders_list}" in text else "{{orders_list}}"
        return text.replace(token, _build_default_live_orders(orders))

    lines = text.splitlines()

    def plain(line):
        value = re.sub(r"<tg-emoji\b[^>]*>.*?</tg-emoji>", "", str(line), flags=re.I | re.S)
        value = re.sub(r"<[^>]+>", "", value)
        return html.unescape(value).strip()

    def is_order_id_line(line):
        raw = str(line)
        p = plain(line)
        return bool(
            re.search(r"\{?\{?order_id\}?\}?", raw, re.I)
            or re.search(r"\b(?:WAL|ORD|ORDER)[_-]?\d{6,}\b", p, re.I)
            or re.search(r"\b\d{10,}\b", p)
        )

    recent_idx = next(
        (i for i, line in enumerate(lines)
         if re.search(r"\brecent\s+orders?\b", plain(line), re.I)),
        None
    )

    if recent_idx is None:
        return _repair_premium_emoji_markup(
            text.rstrip() + ("\n\n" + _build_default_live_orders(orders) if orders else "")
        )

    first_order = next(
        (i for i in range(recent_idx + 1, len(lines)) if is_order_id_line(lines[i])),
        None
    )

    if first_order is None:
        if not orders:
            # No purchased items: never expose a copied/sample order.
            return text
        return _repair_premium_emoji_markup(
            "\n".join(lines[:recent_idx + 1]).rstrip()
            + "\n"
            + _build_default_live_orders(orders).rstrip()
        )

    # Capture exactly one sample order block. Everything after the next sample
    # order is treated as stale copied data/footer and is not repeated.
    block_end = first_order
    next_order = None
    for i in range(first_order + 1, len(lines)):
        if is_order_id_line(lines[i]):
            next_order = i
            break
        if not lines[i].strip():
            block_end = i - 1
            break
        block_end = i

    sample = [x for x in lines[first_order:block_end + 1] if x.strip()]

    footer_start = block_end + 1
    if next_order is not None:
        footer_start = next_order
        while footer_start < len(lines) and is_order_id_line(lines[footer_start]):
            j = footer_start + 1
            while j < len(lines) and lines[j].strip() and not is_order_id_line(lines[j]):
                j += 1
            footer_start = j
            while footer_start < len(lines) and not lines[footer_start].strip():
                footer_start += 1

    footer = lines[footer_start:] if footer_start < len(lines) else []

    field_tokens = {
        0: ("order_id",),
        1: ("product_name", "hack", "days", "plan_days"),
        2: ("price", "amount"),
        3: ("date_time", "date"),
        4: ("key", "purchased_key"),
    }

    def normalize_placeholder_line(line):
        """Return (line, field) for explicit placeholders, if any."""
        raw = str(line)
        checks = [
            (0, ("{order_id}", "{{order_id}}")),
            (1, ("{product_name}", "{{product_name}}", "{hack}", "{{hack}}",
                 "{days}", "{{days}}", "{plan_days}", "{{plan_days}}")),
            (2, ("{price}", "{{price}}", "{amount}", "{{amount}}")),
            (3, ("{date_time}", "{{date_time}}", "{date}", "{{date}}")),
            (4, ("{key}", "{{key}}", "{purchased_key}", "{{purchased_key}}")),
        ]
        for field, tokens in checks:
            if any(token in raw for token in tokens):
                return True, field
        return False, None

    def classify_implicit_field(line):
        """Infer the field from the sample's visible text, never from emoji ID."""
        p = plain(line)
        low = p.lower()

        # Strongest signal first: order ID.
        if is_order_id_line(line):
            return 0

        # Key/status line. This is intentionally checked before date because
        # "Key assigned!" lines can also contain punctuation/digits.
        if re.search(r"\b(key\s+assigned|key\s*[:#]|license\s*[:#]|contact\s+admin)\b", low, re.I):
            return 4

        # Product/day line.
        if re.search(r"\b\d+\s*(?:d|day|days|h|hour|hours)\b", low, re.I):
            return 1
        if re.search(r"\b(?:product|hack|panel)\s*[:\-]", low, re.I):
            return 1

        # Money/price line.
        if "₹" in p or re.search(r"\binr\b", low) or re.search(r"\b(?:price|amount|cost|money)\s*[:\-]", low, re.I):
            return 2

        # Date/time line. IST is a particularly strong signal in this bot.
        if re.search(r"\b(?:ist|am|pm)\b", low, re.I):
            return 3
        if re.search(r"\b(?:date|time|purchased|bought)\s*[:\-]", low, re.I):
            return 3
        if re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", low, re.I):
            return 3

        return None

    def replace_visible_line(line, new_value):
        """Replace only the sample's visible value; preserve Premium HTML exactly."""
        value = html.escape(str(new_value), quote=False)
        original = str(line)

        matches = list(re.finditer(r"</tg-emoji>", original, re.I))
        if matches:
            cut = matches[-1].end()
            prefix = original[:cut]
            rest = original[cut:]

            # Preserve separators/tree characters and opening formatting tags.
            leading = re.match(
                r"(\s*(?:├──|└──|├─|└─|│|─|—|>|\s)*(?:<b>|<i>|<u>|<s>|<code>)*\s*)",
                rest,
                re.I
            )
            lead = leading.group(1) if leading else " "

            closing = ""
            # Preserve only formatting closures that already existed after the
            # sample value. The emoji wrapper itself is never removed.
            closings = re.findall(r"</(?:b|i|u|s|code)>", rest, flags=re.I)
            if closings:
                closing = closings[-1]

            return prefix + lead + value + closing

        # No Premium emoji on this line: preserve the visual tree prefix.
        m = re.match(r"^(\s*(?:├──|└──|├─|└─|│|─|—|>)+\s*)", original)
        prefix = m.group(1) if m else ""
        return prefix + value

    def replace_placeholders(line, vals):
        out = str(line)
        for key, value in vals.items():
            safe = html.escape(str(value), quote=False)
            out = out.replace("{{" + key + "}}", safe)
            out = out.replace("{" + key + "}", safe)
        return out

    def render_sample(order):
        ord_id, p_name, p_days, price, key_val, dt = order
        days = str(p_days or "").strip()
        amount = f"₹{float(price):.2f} INR"
        key_text = str(key_val or "").strip()

        vals = {
            "order_id": ord_id,
            "product_name": p_name,
            "hack": p_name,
            "days": days,
            "plan_days": days,
            "price": amount,
            "amount": amount,
            "date_time": dt,
            "date": dt,
            "key": key_text,
            "purchased_key": key_text,
        }

        out = []
        used_fields = set()
        fallback_index = 0

        for raw_line in sample:
            raw_line = str(raw_line)
            has_placeholder, explicit_field = normalize_placeholder_line(raw_line)

            if has_placeholder:
                if explicit_field == 4 and not key_text:
                    # No purchased/assigned key: hide the key field completely.
                    continue
                out.append(replace_placeholders(raw_line, vals))
                used_fields.add(explicit_field)
                continue

            field = classify_implicit_field(raw_line)

            # If the sample was intentionally left blank except for its Premium
            # emoji, use the original visual order as a LAST RESORT. This is not
            # an emoji-ID mapping; it is only a fallback for blank sample rows.
            if field is None:
                while fallback_index in used_fields:
                    fallback_index += 1
                if fallback_index <= 4 and re.search(r"<tg-emoji\b", raw_line, re.I):
                    field = fallback_index
                    fallback_index += 1

            if field is None or field in used_fields:
                # Decorative/sample text stays exactly as the admin sent it.
                out.append(raw_line)
                continue

            if field == 4 and not key_text:
                # No key was purchased/assigned, so do not expose a fake key or
                # stale "Key assigned" sample line.
                used_fields.add(field)
                continue

            if field == 0:
                new_value = ord_id
            elif field == 1:
                p = plain(raw_line)
                # Product rows commonly use a bold product name followed by an
                # italic validity value. Update those two text nodes separately
                # so the admin's formatting and Premium emoji remain untouched.
                if re.search(r"<i>.*?</i>", raw_line, re.I | re.S):
                    line = re.sub(
                        r"(<b>)(.*?)(</b>)",
                        lambda m: m.group(1) + html.escape(str(p_name), quote=False) + m.group(3),
                        raw_line,
                        count=1,
                        flags=re.I | re.S,
                    )
                    line = re.sub(
                        r"(<i>)(.*?)(</i>)",
                        lambda m: m.group(1) + html.escape(str(days), quote=False) + m.group(3),
                        line,
                        count=1,
                        flags=re.I | re.S,
                    )
                    out.append(line)
                    used_fields.add(field)
                    continue

                if "·" in p:
                    new_value = f"{p_name} · {days}"
                elif re.search(r"\b\d+\s*(?:day|days|hour|hours)\b", p, re.I):
                    # Preserve the sample separator if it used a plain dash.
                    sep = " - " if "-" in p else " · "
                    new_value = f"{p_name}{sep}{days}"
                else:
                    new_value = f"{p_name} · {days}"
            elif field == 2:
                new_value = amount
            elif field == 3:
                new_value = dt
            else:
                # Keep the admin's status/warning text but place the real key
                # immediately after the last Premium emoji when no explicit
                # {key} placeholder was supplied.
                p = plain(raw_line)
                if re.search(r"key\s+assigned|contact\s+admin", p, re.I):
                    matches = list(re.finditer(r"</tg-emoji>", raw_line, re.I))
                    if matches:
                        cut = matches[-1].end()
                        line = (
                            raw_line[:cut]
                            + " <code>"
                            + html.escape(key_text, quote=False)
                            + "</code>"
                            + raw_line[cut:]
                        )
                    else:
                        line = raw_line + " <code>" + html.escape(key_text, quote=False) + "</code>"
                    out.append(line)
                    used_fields.add(field)
                    continue
                new_value = key_text

            out.append(replace_visible_line(raw_line, new_value))
            used_fields.add(field)

        return "\n".join(out)

    prefix = lines[:first_order]
    parts = ["\n".join(prefix).rstrip()]

    # Never expose the admin's sample purchase to a user with no purchases.
    if orders:
        parts.append("\n\n".join(render_sample(order) for order in orders))
    else:
        parts.append("")

    if footer:
        parts.append("\n".join(footer).strip())

    return _repair_premium_emoji_markup("\n\n".join(p for p in parts if p).strip())


def _build_default_live_orders(orders):
    """Legacy fallback only when the admin template has no sample order block."""
    result = []
    for ord_id, p_name, p_days, price, key_val, dt in orders:
        result.append(
            f"✅ <b>{html.escape(str(ord_id), quote=False)}</b>\n"
            f"├── 📦 <b>{html.escape(str(p_name), quote=False)}</b> · <i>{html.escape(str(p_days), quote=False)}</i>\n"
            f"├── 💰 <b>₹{price:.2f} INR</b>\n"
            f"├── ⏰ <b>{html.escape(str(dt), quote=False)}</b>\n"
            f"└── 🔑 <code>{html.escape(str(key_val or ''), quote=False)}</code>\n"
        )
    return "\n".join(result)


def _inject_order_history_live_totals(text, user):
    """Fill Total spent/deposited/balance labels in the saved design.

    The admin is allowed to leave the value blank (for example ``Total spent:``).
    We only replace the value portion; Premium emoji wrappers and formatting before
    the label remain untouched.
    """
    if not text:
        return text
    lifetime = float(user[7] or 0) if user else 0.0
    deposited = float(user[8] or 0) if user else 0.0
    balance = float(user[4] or 0) if user else 0.0
    orders_count = int(user[6] or 0) if user else 0

    lines = []
    for line in str(text).splitlines():
        plain_line = re.sub(r"<tg-emoji\b[^>]*>.*?</tg-emoji>", "", line, flags=re.I | re.S)
        plain_line = re.sub(r"<[^>]+>", "", plain_line)
        low = html.unescape(plain_line).lower()

        if "total spent" in low:
            # Preserve the label and all Premium emoji/HTML before the colon.
            line = re.sub(
                r"(total\s+spent\s*:\s*)(?:</b>\s*)?(.*)$",
                lambda m: m.group(1) + "</b> " + f"₹{lifetime:.2f} INR ({orders_count} orders)",
                line, count=1, flags=re.I
            )
        elif "total deposited" in low:
            line = re.sub(
                r"(total\s+deposited\s*:\s*)(?:</b>\s*)?(.*)$",
                lambda m: m.group(1) + "</b> " + f"₹{deposited:.2f} INR",
                line, count=1, flags=re.I
            )
        elif re.search(r"\bbalance\s*:", low):
            line = re.sub(
                r"(balance\s*:\s*)(?:</b>\s*)?(.*)$",
                lambda m: m.group(1) + "</b> " + f"₹{balance:.2f} INR",
                line, count=1, flags=re.I
            )
        lines.append(line)
    return "\n".join(lines)


def show_orders_history(chat_id, user_id, message_id=None):
    user = get_user(user_id)
    lifetime = user[7] if user else 0.0
    orders_count = user[6] if user else 0
    deposited = user[8] if user else 0.0
    balance = user[4] if user else 0.0

    # ALWAYS fetch orders by the current Telegram user ID. No shared/sample order
    # is ever used as live data.
    orders = get_user_orders(user_id)

    default_history_text = (
        f"📜 <b>ALL HISTORY</b>\n"
        f"────────────────────────\n"
        f"├── 💎 <b>Total spent:</b> ₹{lifetime:.2f} INR ({orders_count} orders)\n"
        f"└── 📥 <b>Total deposited:</b> ₹{deposited:.2f} INR\n\n"
        f"🛍️ <b>Recent Orders</b>\n"
        f"────────────────────────\n"
    )

    history_template = get_custom_text("order_history", "")
    saved_ids = _get_saved_order_history_premium_ids()

    # Migrate Premium IDs from an already-saved template when the recovery cache
    # is empty. This makes existing installations work without asking the admin
    # to send the Premium emojis again.
    if history_template:
        template_ids = _premium_emoji_ids_from_template(history_template)
        if template_ids:
            saved_ids = template_ids
            set_setting("order_history_premium_emoji_ids", json.dumps(template_ids, ensure_ascii=False))
        elif saved_ids:
            # Old/broken saved text contained only normal Unicode emoji. Replace
            # that renderer with the Premium recovery design automatically.
            recovered = _build_order_history_premium_fallback(saved_ids)
            if recovered:
                history_template = recovered

    # Recovery path: if there is no usable custom template, rebuild a complete
    # Premium design from the IDs already saved in the database. No manual Premium
    # emoji editing is required.
    if not history_template:
        history_template = _build_order_history_premium_fallback(saved_ids)

    if history_template:
        history_text = _render_order_history_custom_template(history_template, orders)
    else:
        history_text = default_history_text + _build_default_live_orders(orders)

    # Live account totals/balance are injected after the visual template render so
    # the admin can leave those values blank and still get correct per-user data.
    history_text = _inject_order_history_live_totals(history_text, user)

    live_username = _get_live_telegram_username(user_id)
    history_text = _safe_format_custom_text(
        history_text,
        user=(user[1] if user else "User"),
        name=(user[1] if user else "User"),
        username=live_username,
        telegram_username=live_username,
        user_id=user_id,
        telegram_id=user_id,
        phone=(user[2] if user and len(user) > 2 and user[2] else "N/A"),
        balance=f"{balance:.2f}",
        ref_balance=f"{user[5]:.2f}" if user else "0.00",
        orders=orders_count,
        lifetime=f"{lifetime:.2f}",
        deposited=f"{deposited:.2f}",
        orders_list=_build_default_live_orders(orders),
    )

    history_text = _inject_labeled_user_values(
        history_text,
        {
            "name": html.escape(str(user[1] if user else "User"), quote=False),
            "username": html.escape(str(live_username), quote=False),
            "username_at": html.escape(f"@{live_username}" if live_username else "", quote=False),
            "user_id": str(user_id),
            "phone": html.escape(str(user[2] if user and len(user) > 2 and user[2] else "N/A"), quote=False),
            "balance": f"{balance:.2f}",
            "ref_balance": f"{user[5]:.2f}" if user else "0.00",
            "orders": str(orders_count),
            "lifetime": f"{lifetime:.2f}",
            "deposited": f"{deposited:.2f}",
        }
    )

    markup = types.InlineKeyboardMarkup()
    btn_back = make_ui_button("🔙 Back to Main", callback_data="back_to_main", button_key="nav:back_main", default_color="blue")
    markup.add(btn_back)

    render_or_edit(chat_id, message_id, history_text, markup)


def _inject_referral_link_value(text, ref_link):
    """Always inject the LIVE referral link into a custom Referral Program template.

    Admins often save a formatted message copied from Telegram. In that case the
    visible URL may be missing even though the template contains labels such as
    ``Your Invite Link:`` or ``Your URL Link:``. This helper restores the current
    user's referral URL without changing the surrounding Premium emoji/HTML design.

    Supported forms:
      • Your Invite Link: {ref_link}
      • Your Invite Link:                    -> URL is inserted after ':'
      • Your Invite Link: (blank next line)  -> URL is inserted on that next line
    """
    if not text or not ref_link:
        return text

    value = html.escape(str(ref_link), quote=False)
    link_markup = f"<code>{value}</code>"
    lines = str(text).splitlines()

    labels = re.compile(
        r"\b(?:your\s+(?:invite|referral|url)\s+link|invite\s+link|referral\s+link|ref\s+link)\b",
        re.I,
    )

    # First, replace explicit placeholders wherever they exist.
    replaced_placeholder = False
    for i, line in enumerate(lines):
        if labels.search(re.sub(r"<[^>]+>", "", line)):
            for token in ("{ref_link}", "{{ref_link}}", "{invite_link}", "{{invite_link}}"):
                if token in lines[i]:
                    lines[i] = lines[i].replace(token, link_markup)
                    replaced_placeholder = True

    # Then handle a copied Telegram layout where the link was never saved as a
    # placeholder. Put the URL after the label's colon if that field is blank.
    for i, line in enumerate(lines):
        plain = re.sub(r"<[^>]+>", "", line).strip()
        if not labels.search(plain):
            continue

        # Already contains a real URL or placeholder-generated value.
        if re.search(r"https?://t\.me/", plain, re.I):
            return "\n".join(lines)

        colon = re.match(r"^(.*?:)(\s*)$", line)
        if colon:
            lines[i] = colon.group(1) + " " + link_markup
            return "\n".join(lines)

        # If the label is a heading with a blank line immediately below it,
        # insert the URL there instead of disturbing the user's layout.
        if i + 1 < len(lines) and not lines[i + 1].strip():
            lines[i + 1] = link_markup
            return "\n".join(lines)

        # Label without ':' and without a blank next line: append the URL.
        lines[i] = line.rstrip() + " " + link_markup
        return "\n".join(lines)

    # If no label exists at all, do not silently alter the custom design. The
    # admin can use {ref_link}; the normal/default template already contains it.
    return "\n".join(lines) if replaced_placeholder else text


def show_referral_program(chat_id, user_id, message_id=None):
    user = get_user(user_id)
    ref_count = user[14] if user and len(user) > 14 else 0
    ref_bal = user[5] if user else 0.0

    bot_info = bot.get_me()
    bot_username = bot_info.username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    default_ref_text = (
        f"🎁 <b>REFERRAL PROGRAM</b>\n"
        f"────────────────────────\n"
        f"💰 <b>Earn ₹2.00 INR added directly to your wallet for every friend who joins & verifies their phone number using your referral link!</b>\n\n"
        f"📊 <b>Your Stats</b>\n"
        f"├── 👥 <b>Referrals Verified:</b> {ref_count}\n"
        f"└── 💼 <b>Ref Earnings:</b> ₹{ref_bal:.2f} INR\n\n"
        f"🔗 <b>Your Link</b>\n"
        f"<code>{ref_link}</code> <i>(tap to copy)</i>\n\n"
        f"<i>Share & earn real balance!</i>"
    )

    ref_template = get_custom_text("referral_program", default_ref_text)
    live_username = _get_live_telegram_username(user_id)
    ref_values = {
        "user": (user[1] if user else "User"),
        "name": (user[1] if user else "User"),
        "username": live_username,
        "telegram_username": live_username,
        "user_id": user_id,
        "telegram_id": user_id,
        "phone": (user[2] if user and len(user) > 2 and user[2] else "N/A"),
        "ref_link": ref_link,
        "invite_link": ref_link,
        "referrals": ref_count,
        "ref_balance": f"{ref_bal:.2f}",
        "balance": f"{user[4]:.2f}" if user else "0.00",
    }

    # Render all normal placeholders first.
    ref_text = _safe_format_custom_text(ref_template, **ref_values)

    # Restore live account fields for copied/labeled templates.
    ref_text = _inject_labeled_user_values(
        ref_text,
        {
            "name": html.escape(str(user[1] if user else "User"), quote=False),
            "username": html.escape(str(live_username), quote=False),
            "username_at": html.escape(f"@{live_username}" if live_username else "", quote=False),
            "user_id": str(user_id),
            "phone": html.escape(str(user[2] if user and len(user) > 2 and user[2] else "N/A"), quote=False),
            "balance": f"{user[4]:.2f}" if user else "0.00",
            "ref_balance": f"{ref_bal:.2f}",
            "orders": str(user[6] if user and len(user) > 6 else 0),
        }
    )

    # IMPORTANT: do this AFTER custom-text rendering. This fixes the exact case
    # where the admin only changed Premium emojis/text and left the link field blank.
    ref_text = _inject_referral_link_value(ref_text, ref_link)
    ref_text = _repair_premium_emoji_markup(ref_text)

    markup = types.InlineKeyboardMarkup()
    from urllib.parse import quote
    share_text = quote("Join RG CHEAT SHOP to get instant VIP Gaming Cheats Keys!")
    share_url = f"https://t.me/share/url?url={quote(ref_link, safe='')}&text={share_text}"

    btn_send = make_ui_button(
        "📩 Send Link",
        url=share_url,
        button_key="link:referral_share",
        default_color="green"
    )
    btn_back = make_ui_button(
        "🔙 Back to Main",
        callback_data="back_to_main",
        button_key="nav:back_main",
        default_color="blue"
    )

    markup.add(btn_send)
    markup.add(btn_back)
    render_or_edit(chat_id, message_id, ref_text, markup)

def show_my_account(chat_id, user_id, first_name, message_id=None):
    user = get_user(user_id)
    if user:
        u_id = user[0]
        name = user[1] or first_name
        phone = user[2] or 'N/A'
        country = user[3] or 'IN'
        balance = user[4]
        ref_balance = user[5]
        orders = user[6]
        lifetime = user[7]
        deposited = user[8]
        joined = user[9] or 'N/A'
        is_reseller = user[11]
    else:
        u_id = user_id
        name = first_name
        phone = 'N/A'
        country = 'IN'
        balance = 0.0
        ref_balance = 0.0
        orders = 0
        lifetime = 0.0
        deposited = 0.0
        joined = datetime.datetime.now().strftime("%Y-%m-%d IST")
        is_reseller = 0

    reseller_status = "⭐ <b>Reseller</b> · <i>discounted prices unlocked</i>" if is_reseller else "👤 <b>Standard User</b>"
    default_profile_text = (
        f"👤 <b>MY PROFILE</b>\n"
        f"────────────────────────\n"
        f"├── 🆔 <b>ID:</b> {u_id}\n"
        f"├── 🔥 <b>Name:</b> <i>{name}</i>\n"
        f"├── 📱 <b>Phone:</b> <code>{phone}</code>\n"
        f"├── 🌐 <b>Country:</b> {country}\n"
        f"├── 💼 <b>Balance:</b> ₹{balance:.2f} INR\n"
        f"├── 🎁 <b>Ref Balance:</b> ₹{ref_balance:.2f} INR\n"
        f"├── 📦 <b>Orders:</b> {orders}\n"
        f"├── 💎 <b>Lifetime spent:</b> ₹{lifetime:.2f} INR\n"
        f"├── 📥 <b>Total deposited:</b> ₹{deposited:.2f} INR\n"
        f"└── 📅 <b>Joined:</b> <i>{joined}</i>\n\n"
        f"{reseller_status}"
    )
    profile_template = get_custom_text("my_profile", default_profile_text)
    live_username = _get_live_telegram_username(u_id)
    profile_text = _safe_format_custom_text(
        profile_template,
        user=name,
        name=name,
        first_name=name,
        username=live_username,
        telegram_username=live_username,
        user_id=u_id,
        telegram_id=u_id,
        phone=phone,
        number=phone,
        country=country,
        balance=f"{balance:.2f}",
        ref_balance=f"{ref_balance:.2f}",
        orders=orders,
        lifetime=f"{lifetime:.2f}",
        deposited=f"{deposited:.2f}",
        joined=joined,
    )
    profile_text = _inject_labeled_user_values(
        profile_text,
        {
            "name": html.escape(str(name), quote=False),
            "username": html.escape(str(live_username), quote=False),
            "username_at": html.escape(f"@{live_username}" if live_username else "", quote=False),
            "user_id": str(u_id),
            "phone": html.escape(str(phone), quote=False),
            "country": html.escape(str(country), quote=False),
            "balance": f"{balance:.2f}",
            "ref_balance": f"{ref_balance:.2f}",
            "orders": str(orders),
            "lifetime": f"{lifetime:.2f}",
            "deposited": f"{deposited:.2f}",
            "joined": joined,
        }
    )

    # Existing custom profile layouts often use ``ID:`` (not ``User ID:``).
    # Update only a standalone ID row so Product ID / Order ID are unaffected.
    profile_lines = []
    for profile_line in profile_text.splitlines():
        plain_profile_line = re.sub(r'<[^>]+>', '', profile_line).strip()
        normalized_profile_line = re.sub(r'^[\s├└│|→➜\-_*]+', '', plain_profile_line)
        if (
            re.search(r'(?i)(?:^|[^A-Za-z0-9])ID\s*:', normalized_profile_line)
            and not re.search(r'(?i)^(?:User|Telegram|Account|Order|Product|Device)\s+ID\s*:', normalized_profile_line)
        ):
            profile_line = re.sub(
                r'(\bID\s*:\s*)([^\n]*)',
                lambda m: m.group(1) + str(u_id),
                profile_line,
                count=1,
                flags=re.I,
            )
        profile_lines.append(profile_line)
    profile_text = '\n'.join(profile_lines)

    markup = types.InlineKeyboardMarkup()
    btn_back = make_ui_button("🔙 Back to Main", callback_data="back_to_main", button_key="nav:back_main", default_color="blue")
    markup.add(btn_back)
    render_or_edit(chat_id, message_id, profile_text, markup)

# ==================== CALLBACK QUERY HANDLERS ====================

@bot.callback_query_handler(func=lambda call: True)
def handle_menu_click(call):
    user_id = call.from_user.id
    first_name = call.from_user.first_name or "User"
    
    if call.data == "open_store":
        _fast_callback_ack(call)
        show_open_store(call.message.chat.id, message_id=call.message.message_id)

    elif call.data == "my_account":
        _fast_callback_ack(call)
        show_my_account(call.message.chat.id, user_id, first_name, message_id=call.message.message_id)

    elif call.data == "orders":
        _fast_callback_ack(call)
        show_orders_history(call.message.chat.id, user_id, message_id=call.message.message_id)

    elif call.data == "invite_earn":
        _fast_callback_ack(call)
        show_referral_program(call.message.chat.id, user_id, message_id=call.message.message_id)

    elif call.data == "how_to_use_bot":
        _fast_callback_ack(call)
        show_how_to_use_bot(call.message.chat.id, message_id=call.message.message_id)

    elif call.data == "help_desk":
        _fast_callback_ack(call)
        show_help_desk(call.message.chat.id, message_id=call.message.message_id)

    elif call.data == "top_up":
        _fast_callback_ack(call)
        show_topup_options(call.message.chat.id, message_id=call.message.message_id)

    elif call.data.startswith("topkey_d_"):
        _fast_callback_ack(call)
        try:
            digit = int(call.data.replace("topkey_d_", "", 1))
        except ValueError:
            return
        current = _get_topup_keypad_amount(call.message.chat.id)
        candidate = 0 if (current == 0 and digit == 0) else current * 10 + digit
        if candidate > 10000:
            bot.answer_callback_query(call.id, "❌ Maximum Add Balance is ₹10,000", show_alert=True)
            return
        # Save the exact number represented by the keypad before rendering.
        # The same user/chat state is then rendered immediately below.
        _set_topup_keypad_amount(call.message.chat.id, candidate)
        _update_topup_keypad_message(call.message.chat.id, call.message.message_id)

    elif call.data == "topkey_clear":
        _fast_callback_ack(call)
        _set_topup_keypad_amount(call.message.chat.id, 0)
        _update_topup_keypad_message(call.message.chat.id, call.message.message_id)

    elif call.data == "topkey_confirm":
        _fast_callback_ack(call)
        amount = _get_topup_keypad_amount(call.message.chat.id)
        if not 1 <= amount <= 10000:
            bot.answer_callback_query(call.id, "❌ Enter an amount from ₹1 to ₹10,000", show_alert=True)
            return

        # Confirm uses the exact live keypad amount. The existing QR and
        # background auto-verification flow remains unchanged.
        show_topup_upi_screen(
            call.message.chat.id,
            amount,
            message_id=call.message.message_id,
        )

    elif call.data == "topkey_back":
        _fast_callback_ack(call)
        _clear_topup_keypad_state(call.message.chat.id)
        show_shop_features(call.message.chat.id, first_name, message_id=call.message.message_id)

    elif call.data.startswith("topup_amt_"):
        amt = float(call.data.replace("topup_amt_", ""))
        show_topup_confirm(call.message.chat.id, amt, message_id=call.message.message_id)

    elif call.data == "topup_custom":
        msg = bot.send_message(call.message.chat.id, "✏️ <b>Enter Custom Amount in INR (₹1 - ₹10,000):</b>", parse_mode="HTML")
        bot.register_next_step_handler(msg, step_get_custom_topup)

    elif call.data.startswith("pay_topup_upi_"):
        amt = float(call.data.replace("pay_topup_upi_", ""))
        show_topup_upi_screen(call.message.chat.id, amt, message_id=call.message.message_id)

    elif call.data == "out_of_stock_alert":
        bot.answer_callback_query(call.id, "❌ This plan is currently Out of Stock!", show_alert=True)

    elif call.data.startswith("prod_"):
        _fast_callback_ack(call)
        product_name = call.data.replace("prod_", "")
        show_product_plans(call.message.chat.id, product_name, message_id=call.message.message_id)

    elif call.data.startswith("checkout_"):
        product_id = int(call.data.replace("checkout_", ""))
        product = get_product_by_id(product_id)
        
        req_dev_id = product[11] if product and len(product) > 11 else 0
        if req_dev_id == 1:
            admin_temp_data[user_id] = {'checkout_pid': product_id}
            msg = bot.send_message(call.message.chat.id, "📱 <b>Please enter your Device ID to proceed with purchase:</b>", parse_mode="HTML")
            bot.register_next_step_handler(msg, step_get_device_id_input)
        else:
            show_order_summary(call.message.chat.id, product_id, message_id=call.message.message_id)

    elif call.data.startswith("pay_upi_"):
        raw_data = call.data.replace("pay_upi_", "")
        product_id = 0
        device_id = None
        if ":" in raw_data:
            parts = raw_data.split(":")
            product_id = int(parts[0])
            device_id = parts[1] if len(parts) > 1 and parts[1] else None
        else:
            parts = raw_data.split("_")
            product_id = int(parts[0])
            device_id = parts[1] if len(parts) > 1 and parts[1] else None
        show_upi_checkout(call.message.chat.id, product_id, message_id=call.message.message_id, device_id=device_id)

    # ROBUST WALLET PAYMENT CALLBACK
    elif call.data.startswith("pay_wallet_"):
        # Acknowledge immediately so a slow key/API request never makes the
        # Telegram Wallet button look like it did nothing.
        _fast_callback_ack(call)
        raw_data = call.data.replace("pay_wallet_", "")
        product_id = 0
        device_id = None
        if ":" in raw_data:
            parts = raw_data.split(":")
            product_id = int(parts[0])
            device_id = parts[1] if len(parts) > 1 and parts[1] else None
        else:
            parts = raw_data.split("_")
            product_id = int(parts[0])
            device_id = parts[1] if len(parts) > 1 and parts[1] else None
            
        process_wallet_checkout(call.message.chat.id, user_id, product_id, device_id=device_id)

    elif call.data == "admin_reorder_hacks":
        if user_id in ADMIN_IDS:
            products = get_unique_products()
            if not products:
                bot.send_message(call.message.chat.id, "❌ No hacks/products found to reorder.", parse_mode="HTML")
                return
            markup = types.InlineKeyboardMarkup()
            for idx, prod in enumerate(products, 1):
                btn_name = types.InlineKeyboardButton(f"{idx}. {prod}", callback_data="noop")
                btn_up = types.InlineKeyboardButton("⬆️ Up", callback_data=f"reorder_up_{prod}")
                btn_down = types.InlineKeyboardButton("⬇️ Down", callback_data=f"reorder_down_{prod}")
                markup.add(btn_name, btn_up, btn_down)
            bot.send_message(call.message.chat.id, "🔄 <b>HACK LIST REORDER PANEL</b>\n\nUse Up/Down buttons to adjust the sequence in which hacks appear in store:", parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("reorder_up_") or call.data.startswith("reorder_down_"):
        if user_id in ADMIN_IDS:
            is_up = call.data.startswith("reorder_up_")
            prod_name = call.data.replace("reorder_up_", "") if is_up else call.data.replace("reorder_down_", "")
            move_hack_order(prod_name, "up" if is_up else "down")
            
            products = get_unique_products()
            markup = types.InlineKeyboardMarkup()
            for idx, prod in enumerate(products, 1):
                btn_name = types.InlineKeyboardButton(f"{idx}. {prod}", callback_data="noop")
                btn_up = types.InlineKeyboardButton("⬆️ Up", callback_data=f"reorder_up_{prod}")
                btn_down = types.InlineKeyboardButton("⬇️ Down", callback_data=f"reorder_down_{prod}")
                markup.add(btn_name, btn_up, btn_down)
            
            try:
                bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
            except Exception:
                pass
            bot.answer_callback_query(call.id, f"Moved {prod_name} {'Up' if is_up else 'Down'}!")

    elif call.data == "admin_user_reset":
        if user_id in ADMIN_IDS:
            msg = bot.send_message(call.message.chat.id, "🔄 <b>USER RESET PANEL</b>\n\nPlease enter or paste the Telegram User ID you want to reset completely:\n\n<i>This will erase their profile and force them to re-verify phone number on next /start.</i>", parse_mode="HTML")
            bot.register_next_step_handler(msg, step_process_user_reset)

    elif call.data == "noop":
        bot.answer_callback_query(call.id)

    elif call.data == "admin_device_id_mgmt":
        if user_id in ADMIN_IDS:
            products = get_unique_products()
            if not products:
                bot.send_message(call.message.chat.id, "❌ No products found.")
                return
            markup = types.InlineKeyboardMarkup()
            for prod in products:
                markup.add(types.InlineKeyboardButton(f"🎮 {prod}", callback_data=f"device_id_hack_{prod}"))
            bot.send_message(call.message.chat.id, "📱 <b>SELECT HACK TO TOGGLE DEVICE ID REQUIREMENT:</b>", parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("device_id_hack_"):
        if user_id in ADMIN_IDS:
            p_name = call.data.replace("device_id_hack_", "")
            plans = get_product_plans(p_name)
            markup = types.InlineKeyboardMarkup()
            for plan in plans:
                p_id = plan[0]
                p_days = plan[2]
                req_dev = plan[10] if len(plan) > 10 else 0
                status_str = "📱 Device ID ON" if req_dev == 1 else "⚪ Device ID OFF"
                markup.add(types.InlineKeyboardButton(f"{p_days} ({status_str})", callback_data=f"toggle_dev_id_{p_id}_{1 if req_dev==0 else 0}"))
            bot.send_message(call.message.chat.id, f"🎮 <b>Hack: {p_name}</b>\nTap any plan to toggle Device ID Requirement On/Off:", parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("toggle_dev_id_"):
        if user_id in ADMIN_IDS:
            parts = call.data.split("_")
            p_id = int(parts[3])
            new_status = int(parts[4])
            set_plan_device_id_status(p_id, new_status)
            status_txt = "ON (Device ID Required)" if new_status == 1 else "OFF (No Device ID)"
            bot.answer_callback_query(call.id, f"Device ID Status Updated to {status_txt}!", show_alert=True)
            bot.send_message(call.message.chat.id, f"✅ Device ID Requirement updated to <b>{status_txt}</b> successfully!", parse_mode="HTML")

    elif call.data == "admin_edit_price":
        if user_id in ADMIN_IDS:
            products = get_unique_products()
            if not products:
                bot.send_message(call.message.chat.id, "❌ No products found.", parse_mode="HTML")
                return
            markup = types.InlineKeyboardMarkup()
            for prod in products:
                markup.add(types.InlineKeyboardButton(f"🎮 {prod}", callback_data=f"edit_price_hack_{prod}"))
            bot.send_message(call.message.chat.id, "✏️ <b>SELECT HACK TO EDIT PLAN PRICING:</b>", parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("edit_price_hack_"):
        if user_id in ADMIN_IDS:
            p_name = call.data.replace("edit_price_hack_", "")
            plans = get_product_plans(p_name)
            markup = types.InlineKeyboardMarkup()
            for plan in plans:
                markup.add(types.InlineKeyboardButton(f"⏱️ {plan[2]} (₹{plan[3]} / Resell ₹{plan[4]})", callback_data=f"select_plan_edit_price_{plan[0]}"))
            bot.send_message(call.message.chat.id, f"🎮 <b>Selected Hack: {p_name}</b>\nSelect plan to update price:", parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("select_plan_edit_price_"):
        if user_id in ADMIN_IDS:
            plan_id = int(call.data.replace("select_plan_edit_price_", ""))
            admin_temp_data[user_id] = {'plan_id': plan_id}
            msg = bot.send_message(call.message.chat.id, "💰 <b>Enter New User Price & Reseller Price in INR (₹)</b>\nFormat: <code>User_Price | Reseller_Price</code>\nExample: <code>250 | 180</code>", parse_mode="HTML")
            bot.register_next_step_handler(msg, step_edit_product_price)

    elif call.data == "admin_view_pending_payments":
        if user_id in ADMIN_IDS:
            pending_list = get_all_pending_payments()
            if pending_list:
                msg_text = "⏳ <b>RECENT PENDING PAYMENTS (EXPIRED QRs)</b>\n────────────────────────\n\n"
                for item in pending_list:
                    ord_id, u_id, u_name, p_name, p_days, amt, dt = item
                    msg_text += (
                        f"🆔 <b>Order ID:</b> <code>{ord_id}</code>\n"
                        f"├── 👤 <b>User:</b> {u_name} (<code>{u_id}</code>)\n"
                        f"├── 🛒 <b>Hack:</b> {p_name}\n"
                        f"├── ⏱️ <b>Plan:</b> {p_days}\n"
                        f"├── 💰 <b>Amount:</b> ₹{amt:.2f} INR\n"
                        f"└── ⏰ <b>Time:</b> {dt}\n\n"
                    )
            else:
                msg_text = "✅ <i>No pending/expired payments recorded yet!</i>"
            
            bot.send_message(call.message.chat.id, msg_text, parse_mode="HTML")

    elif call.data == "admin_db_backup":
        if user_id in ADMIN_IDS:
            try:
                with open("shop_data.db", "rb") as db_file:
                    bot.send_document(call.message.chat.id, db_file, caption="📥 <b>Here is your complete database backup!</b>", parse_mode="HTML")
            except Exception as e:
                bot.send_message(call.message.chat.id, f"❌ Error downloading backup: {e}")

    elif call.data == "admin_all_button_color":
        if user_id in ADMIN_IDS:
            show_user_panel_button_color_catalog(call.message.chat.id, message_id=call.message.message_id)
            bot.answer_callback_query(call.id)

    elif call.data == "admin_hack_price_ui":
        if user_id in ADMIN_IDS:
            show_hack_price_ui_catalog(call.message.chat.id, message_id=call.message.message_id)
            bot.answer_callback_query(call.id)

    elif call.data.startswith("hpui_select_"):
        if user_id in ADMIN_IDS:
            h = call.data.replace("hpui_select_", "", 1)
            product_name = admin_temp_data.get(user_id, {}).get("hack_price_ui_catalog", {}).get(h)
            if not product_name:
                bot.answer_callback_query(call.id, "Please reopen Hack Price List Design.", show_alert=True)
                return

            admin_temp_data[user_id] = {"hack_price_ui_product": product_name}
            current = get_hack_price_ui(product_name)
            current_title = current.get("title") if current else product_name

            msg = bot.send_message(
                call.message.chat.id,
                "🧩 <b>PRICE LIST FIX — EMOJI & TEXT</b>\n\n"
                f"🛒 <b>Hack:</b> {html.escape(product_name)}\n\n"
                "Send <b>ONE message</b> containing the complete design you want users to see.\n\n"
                "For example, write your title and these three lines using your Premium custom emojis:"
                "\n<code>DRIP CLIENT - NON ROOT</code>\n"
                "<code>👉 Validity : 1 DAYS</code>\n"
                "<code>👉 Stock: In Stock</code>\n"
                "<code>👉 Price: ₹0.00 INR</code>\n\n"
                "You may use any text/formatting and Premium emojis. Send only ONE sample Validity/Stock/Price block; its values are placeholders. The bot will automatically inject every real plan, INR price, Manual/Auto-API/Out of Stock status and discount.\n\n"
                "🤖 The bot will automatically replace the plan values for every real DAY:"
                "\n• Validity / DAYS\n• Manual stock or In Stock (Auto-API)\n• Out of Stock\n• Live price\n• Discount / % Off\n\n"
                "❗ Do not type all real plans manually. Send only one sample Validity/Stock/Price block."
                "\nThe old normal price-list text for this hack will be replaced by your new design.",
                parse_mode="HTML"
            )
            bot.register_next_step_handler(msg, step_save_hack_price_ui_title)
            bot.answer_callback_query(call.id)

    elif call.data == "admin_plan_text_add":
        if user_id in ADMIN_IDS:
            products = get_unique_products()
            if not products:
                bot.send_message(call.message.chat.id, "❌ No products/hacks found.", parse_mode="HTML")
                bot.answer_callback_query(call.id)
                return
            markup = types.InlineKeyboardMarkup(row_width=1)
            catalog = {}
            for product_name in products:
                h = _ui_hash(product_name)
                catalog[h] = product_name
                saved = bool(get_plan_text_product(product_name))
                label = ("🟢 " if saved else "⚪ ") + product_name
                markup.add(types.InlineKeyboardButton(label, callback_data=f"plantext_select_{h}"))
            markup.add(types.InlineKeyboardButton("🗑 Clear Product Plan Text", callback_data="plantext_clear_menu"))
            admin_temp_data.setdefault(user_id, {})['plan_text_product_catalog'] = catalog
            bot.send_message(
                call.message.chat.id,
                "📝 <b>ALL PRODUCT PLAN TEXT + PREMIUM EMOJI</b>\n\n"
                "Select the hack/price list you want to design.\n"
                "Then send your own text + Premium emoji(s).\n\n"
                "Dynamic placeholders (only where you want live values):\n"
                "<code>{days}</code> = plan days\n"
                "<code>{stock}</code> = Auto-API / Manual / Out of Stock\n"
                "<code>{price}</code> = live price\n\n"
                "❌ No old PLANS & PRICING / CHOOSE A PLAN text will be added.",
                parse_mode="HTML", reply_markup=markup
            )
            bot.answer_callback_query(call.id)

    elif call.data.startswith("plantext_select_"):
        if user_id in ADMIN_IDS:
            h = call.data.replace("plantext_select_", "", 1)
            product_name = admin_temp_data.get(user_id, {}).get('plan_text_product_catalog', {}).get(h)
            if not product_name:
                bot.answer_callback_query(call.id, "Please reopen All Product Plan Text.", show_alert=True)
                return
            admin_temp_data[user_id] = {'plan_text_product': product_name}
            current = get_plan_text_product(product_name)
            preview = html.escape(current[:1500]) if current else "<i>No custom text saved yet.</i>"
            msg = bot.send_message(
                call.message.chat.id,
                "📝 <b>PLAN TEXT + PREMIUM EMOJI</b>\n\n"
                f"🛒 <b>Hack:</b> {html.escape(product_name)}\n\n"
                "Send the exact design you want. Premium custom emojis are preserved.\n\n"
                "Recommended dynamic row: <code>⏱ {days}\n📦 {stock}\n💰 {price}</code>\n\n"
                "The bot repeats that row for every real plan and inserts live days, API/manual/OOS stock and price.\n"
                "Do not write 1/3/7/15/30 days manually.\n\n"
                "<b>Current:</b>\n" + preview,
                parse_mode="HTML"
            )
            bot.register_next_step_handler(msg, step_save_product_plan_text)
            bot.answer_callback_query(call.id)

    elif call.data == "plantext_clear_menu":
        if user_id in ADMIN_IDS:
            products = get_unique_products()
            markup = types.InlineKeyboardMarkup(row_width=1)
            catalog = {}
            for product_name in products:
                h = _ui_hash(product_name)
                catalog[h] = product_name
                markup.add(types.InlineKeyboardButton(f"🗑 {product_name}", callback_data=f"plantext_clear_{h}"))
            admin_temp_data.setdefault(user_id, {})['plan_text_product_catalog'] = catalog
            bot.send_message(call.message.chat.id, "🗑 <b>Select product to clear its custom Plan Text.</b>", parse_mode="HTML", reply_markup=markup)
            bot.answer_callback_query(call.id)

    elif call.data.startswith("plantext_clear_"):
        if user_id in ADMIN_IDS:
            h = call.data.replace("plantext_clear_", "", 1)
            product_name = admin_temp_data.get(user_id, {}).get('plan_text_product_catalog', {}).get(h)
            if not product_name:
                bot.answer_callback_query(call.id, "Please reopen the menu.", show_alert=True)
                return
            set_plan_text_product(product_name, '')
            bot.send_message(call.message.chat.id, f"✅ Custom Plan Text cleared for <b>{html.escape(product_name)}</b>.", parse_mode="HTML")
            bot.answer_callback_query(call.id)

    elif call.data == "admin_all_panel_price_emoji":
        if user_id in ADMIN_IDS:
            current = get_global_price_list_template() or get_custom_text("price_list", "")
            preview = _strip_legacy_price_list_block(current)
            admin_temp_data.setdefault(user_id, {})['global_price_list_edit'] = True
            msg = bot.send_message(
                call.message.chat.id,
                "💠 <b>ALL PANEL PRICE & TEXT + PREMIUM EMOJI</b>\n\n"
                "Send the master price-list design now. You can paste Premium custom emojis and formatted HTML text.\n\n"
                "Saving this design automatically turns <b>Premium Price List Mode ON</b>.\n\n"
                "The bot will automatically:\n"
                "• remove old duplicated plan/price rows from this template;\n"
                "• insert each hack's current Admin-configured plans/prices;\n"
                "• show <b>In Stock (Auto-API)</b> when API stock is used;\n"
                "• show manual stock automatically when manual keys exist;\n"
                "• preserve your Premium custom emojis;\n"
                "• keep the same template across every hack.\n\n"
                "Recommended placeholder: <code>{pricing_info}</code>\n\n"
                "<b>Current normalized template:</b>\n" + html.escape(preview[:2500]),
                parse_mode="HTML"
            )
            bot.register_next_step_handler(msg, step_save_global_price_list_template)
            bot.answer_callback_query(call.id)

    elif call.data == "admin_all_product_emoji":
        if user_id in ADMIN_IDS:
            admin_temp_data.setdefault(user_id, {})["emoji_target"] = "bulk_product_buttons"
            count = len(_get_product_button_keys())
            msg = bot.send_message(
                call.message.chat.id,
                "✨ <b>ALL PRODUCT BUTTON EMOJI</b>\n\n"
                f"Found <b>{count}</b> product button(s).\n"
                "Send exactly one Premium custom emoji.\n\n"
                "That one emoji will replace the old normal leading emoji on <b>ALL product buttons</b>.",
                parse_mode="HTML"
            )
            bot.register_next_step_handler(msg, step_save_premium_emoji)
            bot.answer_callback_query(call.id)

    elif call.data == "admin_all_price_emoji":
        if user_id in ADMIN_IDS:
            admin_temp_data.setdefault(user_id, {})["emoji_target"] = "bulk_price_buttons"
            count = len(_get_price_button_keys())
            msg = bot.send_message(
                call.message.chat.id,
                "💰 <b>ALL PRICE LIST BUTTON EMOJI</b>\n\n"
                f"Found <b>{count}</b> price-plan button(s).\n"
                "Send exactly one Premium custom emoji.\n\n"
                "That one emoji will replace the old normal leading emoji on <b>ALL price-list buttons</b>.",
                parse_mode="HTML"
            )
            bot.register_next_step_handler(msg, step_save_premium_emoji)
            bot.answer_callback_query(call.id)

    elif call.data == "admin_toggle_price_list_mode":
        if user_id in ADMIN_IDS:
            new_state = not get_price_list_premium_mode()
            set_price_list_premium_mode(new_state)
            status = "🟢 <b>ON</b>" if new_state else "🔴 <b>OFF</b>"
            detail = (
                "Premium master price-list text/emojis are now active. "
                "Live DB plans, prices, stock and discounts remain automatic."
                if new_state else
                "Normal/original price-list text is active again. "
                "Your saved Premium template is kept and can be enabled later."
            )
            bot.answer_callback_query(call.id, "Premium Price List " + ("ON" if new_state else "OFF"))
            try:
                bot.edit_message_reply_markup(
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=call.message.reply_markup
                )
            except Exception:
                pass
            bot.send_message(
                call.message.chat.id,
                f"💠 <b>Premium Price List Mode:</b> {status}\n\n{detail}",
                parse_mode="HTML"
            )

    elif call.data == "admin_all_button_emoji":
        if user_id in ADMIN_IDS:
            show_user_panel_button_emoji_catalog(call.message.chat.id, message_id=call.message.message_id)
            bot.answer_callback_query(call.id)

    elif call.data.startswith("abe_select_"):
        if user_id in ADMIN_IDS:
            h = call.data.replace("abe_select_", "", 1)
            key = admin_temp_data.get(user_id, {}).get("all_button_emoji_catalog", {}).get(h)
            if not key:
                bot.answer_callback_query(call.id, "Please reopen All Button Emoji.", show_alert=True)
                return
            admin_temp_data.setdefault(user_id, {})["emoji_target"] = key
            msg = bot.send_message(
                call.message.chat.id,
                "✨ <b>Send the Premium custom emoji now.</b>\n\n"
                "Send only one Premium emoji. It will replace the normal leading emoji on this button.",
                parse_mode="HTML"
            )
            bot.register_next_step_handler(msg, step_save_premium_emoji)
            bot.answer_callback_query(call.id)

    elif call.data == "admin_button_colors":
        if user_id in ADMIN_IDS:
            show_user_panel_button_color_catalog(
                call.message.chat.id,
                message_id=call.message.message_id
            )
            bot.answer_callback_query(call.id)

    elif call.data.startswith("upc_select_"):
        if user_id in ADMIN_IDS:
            h = call.data.replace("upc_select_", "", 1)
            key = admin_temp_data.get(user_id, {}).get("user_panel_color_catalog", {}).get(h)

            if not key:
                bot.answer_callback_query(
                    call.id,
                    "Please reopen User Panel Button Colors.",
                    show_alert=True
                )
                return

            admin_temp_data[user_id]["active_user_panel_color_key"] = key

            current = _button_color_name(key)
            current_label = {
                "red": "🔴 Red",
                "blue": "🔵 Blue",
                "green": "🟢 Green",
            }.get(current, "⚪ Not Set")

            markup = types.InlineKeyboardMarkup(row_width=3)
            for color, label in [
                ("red", "🔴 Red"),
                ("green", "🟢 Green"),
                ("blue", "🔵 Blue"),
            ]:
                prefix = "✓ " if color == current else ""
                markup.add(
                    types.InlineKeyboardButton(
                        prefix + label,
                        callback_data=f"upc_color_{color}_{h}"
                    )
                )

            markup.add(
                types.InlineKeyboardButton(
                    "⬅️ Back to All Buttons",
                    callback_data="upc_back_catalog"
                )
            )

            selected_title = key.replace(":", " / ")
            text = (
                "🎨 <b>SELECT BUTTON COLOR</b>\n\n"
                f"🔘 <b>Button:</b> <code>{selected_title}</code>\n"
                f"🎯 <b>Current:</b> {current_label}\n\n"
                "Choose one color:"
            )

            try:
                bot.edit_message_text(
                    text,
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode="HTML",
                    reply_markup=markup
                )
            except Exception:
                bot.send_message(
                    call.message.chat.id,
                    text,
                    parse_mode="HTML",
                    reply_markup=markup
                )

            bot.answer_callback_query(call.id)

    elif call.data.startswith("upc_color_"):
        if user_id in ADMIN_IDS:
            parts = call.data.split("_")
            if len(parts) != 4:
                bot.answer_callback_query(call.id, "Invalid color selection.", show_alert=True)
                return

            color = parts[2]
            h = parts[3]

            if color not in ("red", "green", "blue"):
                bot.answer_callback_query(call.id, "Invalid color.", show_alert=True)
                return

            key = admin_temp_data.get(user_id, {}).get("user_panel_color_catalog", {}).get(h)
            if not key:
                bot.answer_callback_query(
                    call.id,
                    "Please reopen User Panel Button Colors.",
                    show_alert=True
                )
                return

            set_button_style(key, color)

            # Refresh the selector so the selected color is visibly checked.
            markup = types.InlineKeyboardMarkup(row_width=3)
            for c, label in [
                ("red", "🔴 Red"),
                ("green", "🟢 Green"),
                ("blue", "🔵 Blue"),
            ]:
                prefix = "✓ " if c == color else ""
                markup.add(
                    types.InlineKeyboardButton(
                        prefix + label,
                        callback_data=f"upc_color_{c}_{h}"
                    )
                )

            markup.add(
                types.InlineKeyboardButton(
                    "⬅️ Back to All Buttons",
                    callback_data="upc_back_catalog"
                )
            )

            text = (
                "🎨 <b>SELECT BUTTON COLOR</b>\n\n"
                f"🔘 <b>Button:</b> <code>{key.replace(':', ' / ')}</code>\n"
                f"✅ <b>Saved:</b> {color.title()}\n\n"
                "Choose another color if needed:"
            )

            try:
                bot.edit_message_text(
                    text,
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode="HTML",
                    reply_markup=markup
                )
            except Exception:
                pass

            bot.answer_callback_query(call.id, f"{color.title()} saved successfully")

    elif call.data == "upc_back_catalog":
        if user_id in ADMIN_IDS:
            show_user_panel_button_color_catalog(
                call.message.chat.id,
                message_id=call.message.message_id
            )
            bot.answer_callback_query(call.id)

    elif call.data == "admin_emoji_editor":
        if user_id in ADMIN_IDS:
            markup = types.InlineKeyboardMarkup()
            for title, key in [
                ("🛍️ Main Menu Buttons", "main_buttons"),
                ("🎮 Hack Buttons", "hack_buttons"),
                ("💙 Price List Buttons", "price_buttons"),
                ("✨ ALL Product Buttons — One Emoji", "bulk_product_buttons"),
                ("💠 ALL Price List Buttons — One Emoji", "bulk_price_buttons"),
                ("⏳ Price Expiry Emoji", "price_expiry"),
            ]:
                markup.add(types.InlineKeyboardButton(title, callback_data=f"emoji_group_{key}"))
            bot.send_message(call.message.chat.id, "✨ <b>PREMIUM EMOJI EDITOR</b>\n\nFor a button: send the Premium custom emoji by itself when asked. For text/notifications use the Text Editor and send the formatted text containing your Premium emoji.", parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("emoji_group_"):
        if user_id in ADMIN_IDS:
            group = call.data.replace("emoji_group_", "")
            if group == "price_expiry":
                msg = bot.send_message(call.message.chat.id, "⏳ Send one Premium custom emoji now. I will save its custom_emoji_id for Price List expiry lines.", parse_mode="HTML")
                admin_temp_data[user_id] = {"emoji_target": "price_expiry"}
                bot.register_next_step_handler(msg, step_save_premium_emoji)
            elif group == "bulk_product_buttons":
                count = len(_get_product_button_keys())
                msg = bot.send_message(
                    call.message.chat.id,
                    "✨ <b>ALL PRODUCT BUTTONS</b>\n\n"
                    f"{count} product button(s) will use the same Premium emoji.\n"
                    "Send exactly one Premium custom emoji.",
                    parse_mode="HTML"
                )
                admin_temp_data[user_id] = {"emoji_target": "bulk_product_buttons"}
                bot.register_next_step_handler(msg, step_save_premium_emoji)
            elif group == "bulk_price_buttons":
                count = len(_get_price_button_keys())
                msg = bot.send_message(
                    call.message.chat.id,
                    "💠 <b>ALL PRICE LIST BUTTONS</b>\n\n"
                    f"{count} price-plan button(s) will use the same Premium emoji.\n"
                    "Send exactly one Premium custom emoji.",
                    parse_mode="HTML"
                )
                admin_temp_data[user_id] = {"emoji_target": "bulk_price_buttons"}
                bot.register_next_step_handler(msg, step_save_premium_emoji)
            elif group == "main_buttons":
                markup = types.InlineKeyboardMarkup()
                for title, key in [("Open Store","main:open_store"),("Top Up","main:top_up"),("Orders","main:orders"),("My Account","main:my_account"),("Invite & Earn","main:invite_earn"),("How To Use","main:how_to_use"),("All Update","main:all_update"),("Help Desk","main:help_desk")]:
                    markup.add(types.InlineKeyboardButton(title, callback_data=f"emoji_pick_{_ui_hash(key)}"))
                    admin_temp_data.setdefault(user_id, {}).setdefault("emoji_catalog", {})[_ui_hash(key)] = key
                bot.send_message(call.message.chat.id, "✨ Select a main button to set its Premium emoji.", reply_markup=markup)
            elif group in ("hack_buttons", "price_buttons"):
                markup = types.InlineKeyboardMarkup()
                products = get_unique_products()
                for prod in products:
                    if group == "hack_buttons":
                        key = f"hack:{prod}"
                        h = _ui_hash(key)
                        admin_temp_data.setdefault(user_id, {}).setdefault("emoji_catalog", {})[h] = key
                        markup.add(types.InlineKeyboardButton(f"🎮 {prod}", callback_data=f"emoji_pick_{h}"))
                    else:
                        for plan in get_product_plans(prod):
                            p_id, _, days, *_ = plan
                            key = f"price:{prod}:{p_id}"
                            h = _ui_hash(key)
                            admin_temp_data.setdefault(user_id, {}).setdefault("emoji_catalog", {})[h] = key
                            markup.add(types.InlineKeyboardButton(f"💙 {prod} / {days}", callback_data=f"emoji_pick_{h}"))
                bot.send_message(call.message.chat.id, "✨ Select a button to set its Premium emoji.", reply_markup=markup)

    elif call.data.startswith("emoji_pick_"):
        if user_id in ADMIN_IDS:
            h = call.data.replace("emoji_pick_", "", 1)
            key = admin_temp_data.get(user_id, {}).get("emoji_catalog", {}).get(h)
            if not key:
                bot.answer_callback_query(call.id, "Please reopen the emoji editor.", show_alert=True)
                return
            admin_temp_data[user_id]["emoji_target"] = key
            msg = bot.send_message(call.message.chat.id, "✨ Send the Premium custom emoji now (send it as a single emoji message).", parse_mode="HTML")
            bot.register_next_step_handler(msg, step_save_premium_emoji)

    elif call.data == "admin_button_cust":
        if user_id in ADMIN_IDS:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🛍️ Open Store Button", callback_data="cust_name_open_store"))
            markup.add(types.InlineKeyboardButton("💰 Top Up Button", callback_data="cust_name_top_up"))
            markup.add(types.InlineKeyboardButton("📜 Orders Button", callback_data="cust_name_orders"))
            markup.add(types.InlineKeyboardButton("👤 My Account Button", callback_data="cust_name_my_account"))
            markup.add(types.InlineKeyboardButton("🎁 Invite & Earn Button", callback_data="cust_name_invite_earn"))
            markup.add(types.InlineKeyboardButton("🎬 How To Use Button", callback_data="cust_name_how_to_use"))
            markup.add(types.InlineKeyboardButton("📢 All Update Button", callback_data="cust_name_all_update"))
            markup.add(types.InlineKeyboardButton("📞 Help Desk Button", callback_data="cust_name_help_desk"))
            bot.send_message(
                call.message.chat.id,
                "✏️ <b>Select a Main Menu Button to edit its Name & Emoji:</b>",
                parse_mode="HTML",
                reply_markup=markup
            )

    elif call.data.startswith("cust_name_"):
        if user_id in ADMIN_IDS:
            b_key = call.data.replace("cust_name_", "", 1)
            admin_temp_data[user_id] = {'btn_key': b_key}
            msg = bot.send_message(
                call.message.chat.id,
                f"✏️ <b>Enter new name and emoji for button '{b_key}':</b>",
                parse_mode="HTML"
            )
            bot.register_next_step_handler(msg, step_save_custom_btn)

    elif call.data == "admin_text_editor":
        if user_id in ADMIN_IDS:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("Main Menu Text", callback_data="edit_txt_main_menu"))
            markup.add(types.InlineKeyboardButton("Store Menu Text", callback_data="edit_txt_store_menu"))
            markup.add(types.InlineKeyboardButton("🎬 How To Use Bot Text + Premium Emoji", callback_data="edit_txt_how_to_use"))
            markup.add(types.InlineKeyboardButton("💰 Add Balance Text + Premium Emoji", callback_data="edit_txt_top_up"))
            markup.add(types.InlineKeyboardButton(
                ("💠 Price List / Plans Text + Premium Emoji" if get_price_list_premium_mode()
                 else "✏️ Price List / Plans Text + Premium Emoji"),
                callback_data="edit_txt_price_list"
            ))
            markup.add(types.InlineKeyboardButton("Order Summary Text", callback_data="edit_txt_order_summary"))
            markup.add(types.InlineKeyboardButton("My Profile Text", callback_data="edit_txt_my_profile"))
            markup.add(types.InlineKeyboardButton("Order History Text", callback_data="edit_txt_order_history"))
            markup.add(types.InlineKeyboardButton("Referral Program Text", callback_data="edit_txt_referral_program"))
            markup.add(types.InlineKeyboardButton("Help Desk Text", callback_data="edit_txt_help_desk"))
            markup.add(types.InlineKeyboardButton("Payment Expired Text", callback_data="edit_txt_payment_expired"))
            markup.add(types.InlineKeyboardButton("👋 Verification / First Start Text", callback_data="edit_txt_verification_required"))
            markup.add(types.InlineKeyboardButton("📱 Phone Verified Text", callback_data="edit_txt_phone_verified"))
            markup.add(types.InlineKeyboardButton("🆕 New User Notification Text", callback_data="edit_txt_new_user_notification"))
            markup.add(types.InlineKeyboardButton("🛒 Purchase Notification Text", callback_data="edit_txt_purchase_notification"))
            markup.add(types.InlineKeyboardButton("⏳ Price Expiry Text", callback_data="edit_txt_price_expiry"))
            markup.add(types.InlineKeyboardButton("📲 QR Below Text + Premium Emoji", callback_data="edit_txt_qr_payment"))
            markup.add(types.InlineKeyboardButton("💳 Wallet Payment Text + Premium Emoji", callback_data="edit_txt_wallet_payment"))
            markup.add(types.InlineKeyboardButton("💰 Wallet Balance Success Text + Premium Emoji", callback_data="edit_txt_wallet_topup_success"))
            markup.add(types.InlineKeyboardButton("🇮🇳 UPI Payment Text + Premium Emoji", callback_data="edit_txt_upi_payment"))
            markup.add(types.InlineKeyboardButton("💰 Add Balance Text + Premium Emoji", callback_data="edit_txt_add_balance"))
            markup.add(types.InlineKeyboardButton("💳 Add Balance QR Text + Premium Emoji", callback_data="edit_txt_add_balance_qr"))
            bot.send_message(call.message.chat.id, "✏️ <b>Select Text Section to Edit (Text ID):</b>", parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("edit_txt_"):
        if user_id in ADMIN_IDS:
            t_key = call.data.replace("edit_txt_", "")
            if t_key == "add_balance":
                t_key = "top_up"
            elif t_key == "add_balance_qr":
                t_key = "top_up_qr"
            if t_key == "price_expiry":
                msg = bot.send_message(call.message.chat.id, "⏳ Send one Premium custom emoji now for Price List expiry. This replaces the current expiry emoji.", parse_mode="HTML")
                admin_temp_data[user_id] = {'emoji_target': 'price_expiry'}
                bot.register_next_step_handler(msg, step_save_premium_emoji)
            else:
                admin_temp_data[user_id] = {'text_key': t_key}
                if t_key == "wallet_topup_success":
                    current_wallet_success = get_wallet_topup_success_emoji_template()
                    prompt = (
                        "💰 <b>WALLET BALANCE SUCCESS TEXT + PREMIUM EMOJI</b>\n\n"
                        "Send the complete Wallet Balance Added Successfully message/layout you want users to see after an Add Balance payment is verified.\n\n"
                        "✨ Premium custom emojis are supported and their exact positions will be preserved.\n"
                        "🤖 Live placeholders:\n"
                        "• <code>{name}</code> / <code>{username}</code> → current user's name/username\n"
                        "• <code>{user_id}</code> / <code>{telegram_id}</code> → current Telegram ID\n"
                        "• <code>{order_id}</code> → current payment Order ID\n"
                        "• <code>{amount}</code> / <code>{add_amount}</code> / <code>{topup_amount}</code> → actual amount added\n"
                        "• <code>{utr}</code> → verified payment UTR\n"
                        "• <code>{balance}</code> / <code>{current_balance}</code> → wallet balance after credit\n\n"
                        "🔒 Old sample values are automatically replaced when labels are present.\n\n"
                        "📌 <b>Current design:</b>\n" + current_wallet_success[:3000]
                    )
                    msg = bot.send_message(call.message.chat.id, prompt, parse_mode="HTML")
                    bot.register_next_step_handler(msg, step_save_wallet_topup_success_template)
                    return
                if t_key == "wallet_payment":
                    prompt = (
                        "💳 <b>WALLET PAYMENT TEXT + PREMIUM EMOJI</b>\n\n"
                        "Send the complete Wallet Payment Successful message/layout you want users to see, "
                        "with your Premium custom emojis placed exactly where you want them.\n\n"
                        "✨ This design is saved <b>separately from UPI</b>.\n"
                        "🤖 User ID, Order ID, Product ID, Product, Plan, Paid Amount, Date and Key "
                        "are always injected live for the current buyer.\n"
                        "💳 Method automatically shows <b>Wallet Method</b>.\n"
                        "🔑 Keep the key in <code>&lt;code&gt;</code> (or use the {key} placeholder) so it stays copyable."
                    )
                    msg = bot.send_message(call.message.chat.id, prompt, parse_mode="HTML")
                    bot.register_next_step_handler(msg, step_save_wallet_payment_template)
                    return
                if t_key == "upi_payment":
                    prompt = (
                        "🇮🇳 <b>UPI PAYMENT TEXT + PREMIUM EMOJI</b>\n\n"
                        "Send the complete UPI Payment Successful message/layout you want users to see, "
                        "with your Premium custom emojis placed exactly where you want them.\n\n"
                        "✨ This design is saved <b>separately from Wallet</b>, so editing UPI will never change the Wallet design.\n"
                        "🤖 User ID, Order ID, Product ID, Product, Plan, Paid Amount, Date and Key "
                        "are always injected live for the current buyer.\n"
                        "🇮🇳 Method automatically shows <b>UPI Method</b>.\n"
                        "🔑 Keep the key in <code>&lt;code&gt;</code> (or use the {key} placeholder) so it stays copyable.\n"
                        "💡 You can copy the same layout style as your Wallet screenshot and replace the Premium emojis/text as you like."
                    )
                    msg = bot.send_message(call.message.chat.id, prompt, parse_mode="HTML")
                    bot.register_next_step_handler(msg, step_save_upi_payment_template)
                    return
                if t_key == "qr_payment":
                    prompt = (
                        "📲 <b>QR BELOW TEXT + PREMIUM EMOJI</b>\n\n"
                        "Send the exact text/design you want directly below the QR image. "
                        "Premium custom emojis are supported and their positions will be preserved.\n\n"
                        "Optional live placeholders: "
                        "<code>{hack}</code> / <code>{product_name}</code>, "
                        "<code>{plan}</code>, <code>{amount}</code>, "
                        "<code>{order_id}</code>, <code>{date}</code> / <code>{purchase_date}</code>.\n\n"
                        "The bot will still show a separate live Order Details section below this text, "
                        "so every user's hack name, plan, price, purchase date and unique Order ID stay correct."
                    )
                    msg = bot.send_message(call.message.chat.id, prompt, parse_mode="HTML")
                else:
                    if t_key == "top_up":
                        prompt = (
                            "💰 <b>ADD BALANCE TEXT + PREMIUM EMOJI</b>\n\n"
                            "Send the complete Add Balance screen design with your Premium custom emoji(s). "
                            "The old Add Balance layout is no longer used.\n\n"
                            "Live placeholders: <code>{balance}</code> for the current user's balance and "
                            "<code>{amount}</code>, <code>{add_amount}</code> or <code>{topup_amount}</code> for the keypad amount.\n\n"
                            "The bot automatically keeps Minimum Deposit at ₹1 and Maximum Deposit at ₹10,000. "
                            "When a user enters digits, the amount updates for that user only. Confirm opens the live QR payment screen."
                        )
                        msg = bot.send_message(call.message.chat.id, prompt, parse_mode="HTML")
                    elif t_key == "top_up_qr":
                        current_qr = get_add_balance_qr_text_template()
                        prompt = (
                            "💳 <b>ADD BALANCE QR TEXT + PREMIUM EMOJI</b>\n\n"
                            "Send the complete Premium design you want to appear directly below the Add Balance QR image. "
                            "Use the same clean style as your product purchase QR/payment screen.\n\n"
                            "✨ Premium custom emojis are supported and their exact positions are preserved.\n\n"
                            "<b>Live placeholders:</b>\n"
                            "• <code>{amount}</code> / <code>{add_amount}</code> / <code>{topup_amount}</code> → live Add Amount\n"
                            "• <code>{order_id}</code> → live gateway Order ID\n"
                            "• <code>{date}</code> / <code>{purchase_date}</code> → current date/time\n\n"
                            "🔒 Amount and Order ID are always replaced live, even if you paste an old sample.\n\n"
                            "📌 <b>Current design:</b>\n" + current_qr[:3000]
                        )
                        msg = bot.send_message(call.message.chat.id, prompt, parse_mode="HTML")
                        current_text = get_setting("custom_text_how_to_use") or ""
                        prompt = (
                            "🎬 <b>HOW TO USE BOT TEXT + PREMIUM EMOJI</b>\n\n"
                            "Send the complete text/design you want users to see on the How To Use Bot screen.\n\n"
                            "✨ Telegram Premium custom emojis are supported. Send the formatted message containing the Premium emoji(s), and their exact positions will be preserved.\n\n"
                            "The existing <b>Watch Guide Video</b> button and guide URL are kept separately and are NOT removed or changed by this editor.\n\n"
                            + ("📌 <b>Current saved text:</b>\n" + current_text[:2500] if current_text else "📌 <b>No custom text saved yet.</b> The bot will use the default How To Use text until you save your own.")
                        )
                        msg = bot.send_message(call.message.chat.id, prompt, parse_mode="HTML")
                    else:
                        msg = bot.send_message(
                            call.message.chat.id,
                            f"✏️ <b>Enter new HTML text for section '{t_key}':</b>\n\n"
                            + ("💠 <b>Price List Premium Mode is ON.</b> Your saved design will replace the old price-list text while live plans/prices/stock/discounts remain automatic.\n\n"
                               if t_key == "price_list" and get_price_list_premium_mode()
                               else "Premium custom emoji will be preserved.\n")
                            + "Dynamic placeholders are automatic and are different for every user. You can use: "
                            + "<code>{{user}}</code> / <code>{{name}}</code>, <code>{{user_id}}</code> / <code>{{telegram_id}}</code>, "
                            + "<code>{{phone}}</code> / <code>{{number}}</code>, <code>{{country}}</code>, <code>{{balance}}</code>, <code>{{date}}</code>, "
                            + "<code>{{hack}}</code> / <code>{{product_name}}</code>, <code>{{plan}}</code>, <code>{{amount}}</code>, "
                            + "<code>{{order_id}}</code>, <code>{{ref_link}}</code> / <code>{{invite_link}}</code>, "
                            + "<code>{{pricing_info}}</code> / <code>{{price_list}}</code> / <code>{{prices}}</code>, "
                            + "and <code>{{default_price_list}}</code>.\n\n"
                            + "For New User / Phone Verified texts, if you keep labels such as <b>Name:</b>, <b>User ID:</b> and <b>Phone Number:</b>, "
                            + "their live values will also be restored automatically even if you forget the placeholders.",
                            parse_mode="HTML"
                        )
                bot.register_next_step_handler(msg, step_save_custom_text)

    elif call.data == "admin_quick_setup":
        if user_id in ADMIN_IDS:
            msg_text = (
                f"⚡ <b>QUICK ADMIN SETUP</b>\n\n"
                f"Send setup details in this exact multi-line format:\n\n"
                f"<code>Product_ID | Hack Name\n"
                f"1 Hours | 1 Hours | User_Price | Reseller_Price\n"
                f"1 DaYs | 1 DaYs | User_Price | Reseller_Price</code>"
            )
            msg = bot.send_message(call.message.chat.id, msg_text, parse_mode="HTML")
            bot.register_next_step_handler(msg, step_quick_setup)

    elif call.data == "admin_stock_mgmt":
        if user_id in ADMIN_IDS:
            products = get_unique_products()
            if not products:
                bot.send_message(call.message.chat.id, "❌ No products found.")
                return
            markup = types.InlineKeyboardMarkup()
            for prod in products:
                markup.add(types.InlineKeyboardButton(f"🎮 {prod}", callback_data=f"stock_hack_{prod}"))
            bot.send_message(call.message.chat.id, "📦 <b>SELECT HACK TO MANAGE STOCK STATUS:</b>", parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("stock_hack_"):
        if user_id in ADMIN_IDS:
            p_name = call.data.replace("stock_hack_", "")
            plans = get_product_plans(p_name)
            markup = types.InlineKeyboardMarkup()
            for plan in plans:
                p_id, _, p_days, _, _, _, _, _, _, is_oos, _ = plan
                status_str = "❌ Out of Stock" if is_oos else "✅ In Stock"
                markup.add(types.InlineKeyboardButton(f"{p_days} ({status_str})", callback_data=f"toggle_stock_{p_id}_{1 if is_oos==0 else 0}"))
            bot.send_message(call.message.chat.id, f"🎮 <b>Hack: {p_name}</b>\nTap any plan to toggle Stock On/Off:", parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("toggle_stock_"):
        if user_id in ADMIN_IDS:
            parts = call.data.split("_")
            p_id = int(parts[2])
            new_status = int(parts[3])
            set_plan_stock_status(p_id, new_status)
            bot.answer_callback_query(call.id, f"Stock Status Updated to {'Out of Stock' if new_status==1 else 'In Stock'}!", show_alert=True)
            bot.send_message(call.message.chat.id, "✅ Stock status updated successfully!")

    elif call.data == "admin_set_tg_group":
        if user_id in ADMIN_IDS:
            products = get_unique_products()
            if not products:
                bot.send_message(call.message.chat.id, "❌ No products found.")
                return
            markup = types.InlineKeyboardMarkup()
            for prod in products:
                markup.add(types.InlineKeyboardButton(f"🎮 {prod}", callback_data=f"set_tg_hack_{prod}"))
            bot.send_message(call.message.chat.id, "🔗 <b>SELECT HACK TO SET TELEGRAM GROUP LINK:</b>", parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("set_tg_hack_"):
        if user_id in ADMIN_IDS:
            p_name = call.data.replace("set_tg_hack_", "")
            admin_temp_data[user_id] = {'hack_name': p_name}
            msg = bot.send_message(call.message.chat.id, f"🔗 <b>Paste Telegram Group Link for {p_name}:</b>", parse_mode="HTML")
            bot.register_next_step_handler(msg, step_set_tg_group_link)

    elif call.data == "admin_hack_day_mgmt":
        if user_id in ADMIN_IDS:
            markup = types.InlineKeyboardMarkup()
            btn_add_hack = types.InlineKeyboardButton("➕ Add New Hack & Day Plan", callback_data="admin_add_hack_plan")
            btn_add_day = types.InlineKeyboardButton("📅 Add Day to Existing Hack", callback_data="admin_add_day_exist")
            btn_del_hack = types.InlineKeyboardButton("🗑️ Remove Entire Hack", callback_data="admin_del_hack")
            btn_del_plan = types.InlineKeyboardButton("❌ Remove Day / Plan", callback_data="admin_del_plan")
            markup.add(btn_add_hack)
            markup.add(btn_add_day)
            markup.add(btn_del_hack, btn_del_plan)
            bot.send_message(call.message.chat.id, "⚙️ <b>HACK & DAY MANAGEMENT PANEL</b>\n\nSelect action:", parse_mode="HTML", reply_markup=markup)

    elif call.data == "admin_add_hack_plan":
        if user_id in ADMIN_IDS:
            msg = bot.send_message(call.message.chat.id, "📝 <b>Enter Hack / Product Name:</b>", parse_mode="HTML")
            bot.register_next_step_handler(msg, step_add_hack_name)

    elif call.data == "admin_add_day_exist":
        if user_id in ADMIN_IDS:
            products = get_unique_products()
            if not products:
                bot.send_message(call.message.chat.id, "❌ No products found.", parse_mode="HTML")
                return
            markup = types.InlineKeyboardMarkup()
            for prod in products:
                markup.add(types.InlineKeyboardButton(f"🎮 {prod}", callback_data=f"sel_hack_add_day_{prod}"))
            bot.send_message(call.message.chat.id, "🎮 <b>SELECT HACK TO ADD NEW DAY/PLAN:</b>", parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("sel_hack_add_day_"):
        if user_id in ADMIN_IDS:
            p_name = call.data.replace("sel_hack_add_day_", "")
            admin_temp_data[user_id] = {'name': p_name}
            msg = bot.send_message(call.message.chat.id, f"📅 <b>Enter New Duration/Day Name for {p_name}</b> (e.g., <code>1 Hours</code>, <code>1 DaYs</code>):", parse_mode="HTML")
            bot.register_next_step_handler(msg, step_get_add_day_to_hack)

    elif call.data == "admin_server_api_mgmt":
        if user_id in ADMIN_IDS:
            msg = bot.send_message(call.message.chat.id, "🔑 <b>Enter Server API Token Key:</b>", parse_mode="HTML")
            bot.register_next_step_handler(msg, step_get_server_token)

    elif call.data == "test_server_api_conn":
        if user_id in ADMIN_IDS:
            curr_url = get_setting('server_api_url') or RESELLER_API_URL
            curr_key = get_setting('server_api_key') or RESELLER_API_KEY
            try:
                res = HTTP_SESSION.post(curr_url, data={'api_key': curr_key, 'action': 'balance'}, timeout=8)
                if res.status_code == 200:
                    bot.send_message(call.message.chat.id, "✅ <b>Connect Successfully!</b>\n\nServer API connected & active.", parse_mode="HTML")
                else:
                    bot.send_message(call.message.chat.id, "❌ <b>Not Connect</b>\n\nServer returned an invalid response status.", parse_mode="HTML")
            except Exception as e:
                bot.send_message(call.message.chat.id, f"❌ <b>Not Connect</b>\n\nError: {e}", parse_mode="HTML")

    elif call.data == "admin_map_server_id":
        if user_id in ADMIN_IDS:
            products = get_unique_products()
            if not products:
                bot.send_message(call.message.chat.id, "❌ No products found.", parse_mode="HTML")
                return
            markup = types.InlineKeyboardMarkup()
            for prod in products:
                markup.add(types.InlineKeyboardButton(f"🎮 {prod}", callback_data=f"map_sel_hack_{prod}"))
            bot.send_message(call.message.chat.id, "🔗 <b>SELECT HACK TO MAP SERVER PRODUCT ID & DURATION:</b>", parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("map_sel_hack_"):
        if user_id in ADMIN_IDS:
            p_name = call.data.replace("map_sel_hack_", "")
            plans = get_product_plans(p_name)
            if not plans:
                bot.send_message(call.message.chat.id, "❌ No plans found.", parse_mode="HTML")
                return
            markup = types.InlineKeyboardMarkup()
            for plan in plans:
                markup.add(types.InlineKeyboardButton(f"⏱️ {plan[2]} Plan", callback_data=f"map_plan_id_{plan[0]}"))
            bot.send_message(call.message.chat.id, f"🎮 <b>Selected Hack: {p_name}</b>\nSelect Plan to Map Server API Details:", parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("map_plan_id_"):
        if user_id in ADMIN_IDS:
            plan_id = int(call.data.replace("map_plan_id_", ""))
            admin_temp_data[user_id] = {'plan_id': plan_id}
            msg = bot.send_message(call.message.chat.id, "🆔 <b>Enter Server Remote Product ID (PID):</b> (e.g., <code>133</code>)", parse_mode="HTML")
            bot.register_next_step_handler(msg, step_get_remote_pid)

    elif call.data == "admin_change_bot_token":
        if user_id in ADMIN_IDS:
            msg = bot.send_message(call.message.chat.id, "🔑 <b>Enter New Telegram Bot API Token:</b>", parse_mode="HTML")
            bot.register_next_step_handler(msg, step_get_new_bot_token)

    elif call.data == "admin_manage_reseller":
        if user_id in ADMIN_IDS:
            msg = bot.send_message(call.message.chat.id, "👤 <b>Enter Telegram User ID to Add/Remove Reseller:</b>", parse_mode="HTML")
            bot.register_next_step_handler(msg, step_get_reseller_uid)

    elif call.data.startswith("set_resell_"):
        if user_id in ADMIN_IDS:
            parts = call.data.split("_")
            status = int(parts[2])
            target_uid = int(parts[3])
            
            set_reseller_status(target_uid, status)
            role_title = "Reseller ⭐" if status == 1 else "Standard User 👤"
            bot.send_message(call.message.chat.id, f"✅ <b>Role Updated!</b> User <code>{target_uid}</code> is now a <b>{role_title}</b>.", parse_mode="HTML")
            
            try:
                if status == 1:
                    bot.send_message(target_uid, "🎉 <b>Congratulations!</b> You have been promoted to <b>Reseller</b>!\n💎 Reseller discounted prices are now unlocked for you in the shop.", parse_mode="HTML")
                else:
                    bot.send_message(target_uid, "ℹ️ Your Reseller status has been reset to Standard User.", parse_mode="HTML")
            except Exception:
                pass

    elif call.data == "admin_add_manual_key":
        if user_id in ADMIN_IDS:
            products = get_unique_products()
            if not products:
                bot.send_message(call.message.chat.id, "❌ No products found.", parse_mode="HTML")
                return
            markup = types.InlineKeyboardMarkup()
            for prod in products:
                markup.add(types.InlineKeyboardButton(f"🎮 {prod}", callback_data=f"man_key_hack_{prod}"))
            bot.send_message(call.message.chat.id, "🔑 <b>SELECT HACK TO ADD MANUAL VIP KEY:</b>", parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("man_key_hack_"):
        if user_id in ADMIN_IDS:
            p_name = call.data.replace("man_key_hack_", "")
            plans = get_product_plans(p_name)
            markup = types.InlineKeyboardMarkup()
            for plan in plans:
                markup.add(types.InlineKeyboardButton(f"⏱️ {plan[2]} Plan", callback_data=f"man_key_plan_{plan[0]}"))
            bot.send_message(call.message.chat.id, f"🎮 <b>Selected: {p_name}</b>\nSelect Plan:", parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("man_key_plan_"):
        if user_id in ADMIN_IDS:
            p_id = int(call.data.replace("man_key_plan_", ""))
            prod = get_product_by_id(p_id)
            if prod:
                admin_temp_data[user_id] = {'p_name': prod[1], 'days': prod[3]}
                msg = bot.send_message(call.message.chat.id, f"🔑 <b>Paste/Send VIP Key for {prod[1]} ({prod[3]}):</b>", parse_mode="HTML")
                
                def save_key_step(msg):
                    add_key_db(admin_temp_data[user_id]['p_name'], admin_temp_data[user_id]['days'], msg.text.strip())
                    bot.send_message(msg.chat.id, "✅ <b>Add Successfully! VIP Key Saved to Database (FIFO Queue).</b>", parse_mode="HTML")
                    del admin_temp_data[user_id]
                
                bot.register_next_step_handler(msg, save_key_step)

    elif call.data == "admin_track_users":
        if user_id in ADMIN_IDS:
            users = get_all_users()
            if not users:
                bot.send_message(call.message.chat.id, "❌ No verified users found.")
                return
            markup = types.InlineKeyboardMarkup()
            for u in users:
                markup.add(types.InlineKeyboardButton(f"👤 {u[1]} (ID: {u[0]})", callback_data=f"track_uid_{u[0]}"))
            bot.send_message(call.message.chat.id, "👥 <b>VERIFIED USERS LIST:</b>\n<i>Select any user to view detailed profile & orders.</i>", parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("track_uid_"):
        if user_id in ADMIN_IDS:
            target_uid = int(call.data.replace("track_uid_", ""))
            u_info = get_user(target_uid)
            if u_info:
                orders = get_user_orders(target_uid)
                ord_text = ""
                if orders:
                    for o in orders:
                        ord_text += (
                            f"🆔 <b>Order ID:</b> <code>{o[0]}</code>\n"
                            f"├── 🛒 <b>Hack:</b> {o[1]} ({o[2]})\n"
                            f"├── 💰 <b>Paid:</b> ₹{o[3]:.1f} INR\n"
                            f"├── ⏰ <b>Time:</b> {o[5]}\n"
                            f"└── 🔑 <b>Key:</b> <code>{o[4]}</code>\n\n"
                        )
                else:
                    ord_text = "<i>No purchase history yet.</i>"

                user_details = (
                    f"📊 <b>USER PROFILE & TRACKING</b>\n"
                    f"────────────────────────\n"
                    f"├── 🆔 <b>User ID:</b> <code>{u_info[0]}</code>\n"
                    f"├── 👤 <b>Name:</b> {u_info[1]}\n"
                    f"├── 📞 <b>Phone:</b> {u_info[2] or 'N/A'}\n"
                    f"├── 💼 <b>Balance:</b> ₹{u_info[4]:.2f} INR\n"
                    f"├── 📦 <b>Orders Count:</b> {u_info[6]}\n"
                    f"├── 💎 <b>Lifetime Spent:</b> ₹{u_info[7]:.2f} INR\n"
                    f"├── 📥 <b>Total Deposited:</b> ₹{u_info[8]:.2f} INR\n"
                    f"└── 📅 <b>Joined:</b> {u_info[9]}\n\n"
                    f"🛒 <b>Purchases & Keys:</b>\n{ord_text}"
                )
                bot.send_message(call.message.chat.id, user_details, parse_mode="HTML")

    elif call.data == "admin_manage_discounts":
        if user_id in ADMIN_IDS:
            markup = types.InlineKeyboardMarkup()
            btn_usr = types.InlineKeyboardButton("👤 Specific User Discount", callback_data="disc_specific_user")
            btn_glb = types.InlineKeyboardButton("🌐 Global Discount (All Hacks & Users)", callback_data="disc_global_store")
            btn_prd = types.InlineKeyboardButton("🎮 Specific Hack Discount", callback_data="disc_specific_hack")
            markup.add(btn_usr)
            markup.add(btn_glb)
            markup.add(btn_prd)
            bot.send_message(call.message.chat.id, "🏷️ <b>DISCOUNT MANAGEMENT PANEL</b>", parse_mode="HTML", reply_markup=markup)

    elif call.data == "disc_specific_user":
        if user_id in ADMIN_IDS:
            msg = bot.send_message(call.message.chat.id, "👤 <b>Enter Target Telegram User ID:</b>", parse_mode="HTML")
            bot.register_next_step_handler(msg, step_get_user_discount_id)

    elif call.data == "disc_specific_hack":
        if user_id in ADMIN_IDS:
            products = get_unique_products()
            if not products:
                bot.send_message(call.message.chat.id, "❌ No products found.", parse_mode="HTML")
                return
            markup = types.InlineKeyboardMarkup()
            for prod in products:
                current = get_product_discount_percent(prod)
                markup.add(types.InlineKeyboardButton(
                    f"🎮 {prod} ({current:.0f}% OFF)",
                    callback_data=f"disc_prod_{prod}"
                ))
            bot.send_message(
                call.message.chat.id,
                "🎮 <b>SELECT HACK FOR DISCOUNT</b>\n\nTap a hack to set its discount percentage. 0% returns its product/price buttons to blue unless a global discount is active.",
                parse_mode="HTML",
                reply_markup=markup
            )

    elif call.data == "disc_global_store":
        if user_id in ADMIN_IDS:
            msg = bot.send_message(call.message.chat.id, "🌐 <b>Enter Global Discount Percentage for ALL Users & Products</b> (e.g., <code>10</code> for 10%):", parse_mode="HTML")
            bot.register_next_step_handler(msg, step_get_global_discount_percent)

    elif call.data.startswith("disc_prod_"):
        if user_id in ADMIN_IDS:
            p_name = call.data.replace("disc_prod_", "")
            admin_temp_data[user_id] = {'prod_name': p_name}
            msg = bot.send_message(call.message.chat.id, f"🏷️ <b>Enter Discount Percentage for {p_name}:</b>", parse_mode="HTML")
            bot.register_next_step_handler(msg, step_get_prod_discount_percent)

    elif call.data == "admin_broadcast":
        if user_id in ADMIN_IDS:
            msg = bot.send_message(call.message.chat.id, "📢 <b>Send photo, video, audio or text message to broadcast to all users:</b>", parse_mode="HTML")
            bot.register_next_step_handler(msg, step_get_broadcast_media)

    elif call.data == "admin_manage_bal":
        if user_id in ADMIN_IDS:
            msg = bot.send_message(call.message.chat.id, "👤 <b>Enter Telegram User ID to Modify Balance:</b>", parse_mode="HTML")
            bot.register_next_step_handler(msg, step_get_bal_user_id)

    elif call.data in ["bal_action_add", "bal_action_sub"]:
        if user_id in ADMIN_IDS:
            admin_temp_data[user_id]['is_add'] = (call.data == "bal_action_add")
            msg = bot.send_message(call.message.chat.id, "💰 <b>Enter Amount in INR (₹):</b>", parse_mode="HTML")
            bot.register_next_step_handler(msg, step_get_bal_amount)

    elif call.data == "admin_del_hack":
        if user_id in ADMIN_IDS:
            products = get_unique_products()
            if not products:
                bot.send_message(call.message.chat.id, "❌ No products found to delete.", parse_mode="HTML")
                return
            markup = types.InlineKeyboardMarkup()
            for prod in products:
                markup.add(types.InlineKeyboardButton(f"🗑️ Delete {prod}", callback_data=f"confirm_del_hack_{prod}"))
            bot.send_message(call.message.chat.id, "⚠️ <b>SELECT ENTIRE HACK TO DELETE:</b>\n<i>This will remove all plans associated with this hack!</i>", parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("confirm_del_hack_"):
        if user_id in ADMIN_IDS:
            prod_name = call.data.replace("confirm_del_hack_", "")
            delete_entire_hack_db(prod_name)
            bot.send_message(call.message.chat.id, f"✅ <b>Successfully Deleted Entire Hack:</b> {prod_name}", parse_mode="HTML")

    elif call.data == "admin_del_plan":
        if user_id in ADMIN_IDS:
            products = get_unique_products()
            if not products:
                bot.send_message(call.message.chat.id, "❌ No products found.", parse_mode="HTML")
                return
            markup = types.InlineKeyboardMarkup()
            for prod in products:
                markup.add(types.InlineKeyboardButton(f"🎮 {prod}", callback_data=f"select_del_plan_hack_{prod}"))
            bot.send_message(call.message.chat.id, "❌ <b>SELECT HACK TO DELETE A SPECIFIC PLAN/DAY:</b>", parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("select_del_plan_hack_"):
        if user_id in ADMIN_IDS:
            prod_name = call.data.replace("select_del_plan_hack_", "")
            plans = get_product_plans(prod_name)
            if not plans:
                bot.send_message(call.message.chat.id, "❌ No plans found for this hack.", parse_mode="HTML")
                return
            markup = types.InlineKeyboardMarkup()
            for plan in plans:
                p_id, _, p_days, p_price, _, _, _, _, _, _, _ = plan
                markup.add(types.InlineKeyboardButton(f"🗑️ Delete {p_days} Plan (₹{p_price:.2f})", callback_data=f"confirm_del_plan_{p_id}"))
            bot.send_message(call.message.chat.id, f"🎮 <b>Selected Hack: {prod_name}</b>\nSelect Plan to Delete:", parse_mode="HTML", reply_markup=markup)

    elif call.data.startswith("confirm_del_plan_"):
        if user_id in ADMIN_IDS:
            p_id = int(call.data.replace("confirm_del_plan_", ""))
            delete_product_plan_db(p_id)
            bot.send_message(call.message.chat.id, "✅ <b>Successfully Deleted Plan!</b>", parse_mode="HTML")

    elif call.data == "admin_set_guide":
        if user_id in ADMIN_IDS:
            msg = bot.send_message(call.message.chat.id, "🎬 <b>Enter Dynamic How To Use Bot Guide Link (URL):</b>", parse_mode="HTML")
            bot.register_next_step_handler(msg, step_get_guide_url)

    elif call.data == "back_to_main":
        show_shop_features(call.message.chat.id, first_name, message_id=call.message.message_id)

    elif call.data == "back_to_main_new":
        show_shop_features(call.message.chat.id, first_name)

    elif call.data == "back_from_qr":
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        show_shop_features(call.message.chat.id, first_name)

print("🤖 RG Cheat Shop Bot is running successfully with Admin Verification Notification & Pending Payments feature...")

# ==================== SINGLE-INSTANCE POLLING GUARD ====================
# Telegram allows only one active getUpdates long-poll for a bot token.
# This local lock prevents accidental double-launches from Termux.
_POLL_LOCK_PATH = ".rg_cheat_shop_polling.lock"
_poll_lock_file = None

def acquire_single_instance_lock():
    global _poll_lock_file
    try:
        import fcntl
        _poll_lock_file = open(_POLL_LOCK_PATH, "w")
        fcntl.flock(_poll_lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _poll_lock_file.write(str(os.getpid()))
        _poll_lock_file.flush()
        return True
    except (BlockingIOError, OSError):
        print("❌ Another instance of this bot is already running in this folder. Stop it before starting a second copy.")
        return False
    except Exception as e:
        print(f"⚠️ Polling lock warning: {e}")
        return True

def run_bot_polling():
    if not acquire_single_instance_lock():
        return
    # Remove any webhook so long polling can work reliably after a webhook-based run.
    try:
        bot.remove_webhook()
    except Exception:
        pass
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=20)
            break
        except Exception as e:
            err = str(e)
            if "409" in err and "getUpdates" in err:
                print("⚠️ Telegram 409 Conflict: another getUpdates client is still active. Waiting 10 seconds before retrying...")
                time.sleep(10)
                continue
            print(f"⚠️ Polling stopped because of an unexpected error: {e}")
            time.sleep(5)

run_bot_polling()
