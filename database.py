import sqlite3
import datetime
import random
import string
from contextlib import contextmanager

from config import DB_PATH, CATEGORIES, ADMIN_IDS, SUPPORT_ADMIN_USERNAME
from text_style import stylize


def _now():
    return datetime.datetime.utcnow().isoformat()


def _gen_reference(prefix):
    return prefix + "".join(random.choices(string.digits, k=4))


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            phone_number TEXT,
            role TEXT DEFAULT 'user',        -- 'user' | 'reseller'
            balance REAL DEFAULT 0,
            banned INTEGER DEFAULT 0,
            last_daily_gift TEXT,
            joined_at TEXT
        )""")
        try:
            c.execute("ALTER TABLE users ADD COLUMN phone_number TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE users ADD COLUMN referral_bonus_earned REAL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        c.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            icon TEXT
        )""")
        try:
            c.execute("ALTER TABLE categories ADD COLUMN icon TEXT")
        except sqlite3.OperationalError:
            pass
        c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER,
            name TEXT,
            visibility TEXT DEFAULT 'all',
            icon TEXT,
            FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE CASCADE
        )""")
        try:
            c.execute("ALTER TABLE products ADD COLUMN visibility TEXT DEFAULT 'all'")
        except sqlite3.OperationalError:
            pass  # column already exists
        try:
            c.execute("ALTER TABLE products ADD COLUMN icon TEXT")
        except sqlite3.OperationalError:
            pass
        c.execute("""
        CREATE TABLE IF NOT EXISTS durations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            label TEXT,
            icon TEXT,
            FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
        )""")
        try:
            c.execute("ALTER TABLE durations ADD COLUMN icon TEXT")
        except sqlite3.OperationalError:
            pass
        c.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            duration_id INTEGER,
            scope TEXT,              -- 'all' | 'reseller' | 'user'
            telegram_id INTEGER,     -- only used when scope='user'
            price REAL,
            FOREIGN KEY(duration_id) REFERENCES durations(id) ON DELETE CASCADE
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS stock_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            duration_id INTEGER,
            key_text TEXT,
            is_sold INTEGER DEFAULT 0,
            sold_to INTEGER,
            sold_at TEXT,
            FOREIGN KEY(duration_id) REFERENCES durations(id) ON DELETE CASCADE
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS trial_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            icon TEXT,
            link TEXT
        )""")
        try:
            c.execute("ALTER TABLE trial_products ADD COLUMN link TEXT")
        except sqlite3.OperationalError:
            pass
        c.execute("""
        CREATE TABLE IF NOT EXISTS trial_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trial_product_id INTEGER,
            key_text TEXT,
            is_used INTEGER DEFAULT 0,
            used_by INTEGER,
            used_at TEXT,
            FOREIGN KEY(trial_product_id) REFERENCES trial_products(id) ON DELETE CASCADE
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            product_id INTEGER,
            duration_id INTEGER,
            price REAL,
            method TEXT,             -- 'balance' | 'qr' | 'binance'
            status TEXT DEFAULT 'pending',  -- pending | review | completed | rejected | cancelled
            screenshot_file_id TEXT,
            binance_order_id TEXT,
            reference TEXT,
            created_at TEXT
        )""")
        try:
            c.execute("ALTER TABLE orders ADD COLUMN binance_order_id TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE orders ADD COLUMN reference TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE orders ADD COLUMN delivered_key TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE orders ADD COLUMN coupon_code TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE orders ADD COLUMN gateway_order_id TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE orders ADD COLUMN gateway_expires_at TEXT")
        except sqlite3.OperationalError:
            pass
        c.execute("""
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            amount REAL,
            method TEXT DEFAULT 'upi',      -- 'upi' | 'binance'
            status TEXT DEFAULT 'pending',  -- pending | review | completed | rejected | cancelled
            screenshot_file_id TEXT,
            binance_order_id TEXT,
            reference TEXT,
            created_at TEXT
        )""")
        try:
            c.execute("ALTER TABLE deposits ADD COLUMN method TEXT DEFAULT 'upi'")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE deposits ADD COLUMN binance_order_id TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE deposits ADD COLUMN reference TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE deposits ADD COLUMN gateway_order_id TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE deposits ADD COLUMN gateway_expires_at TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE deposits ADD COLUMN purpose TEXT DEFAULT 'deposit'")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE deposits ADD COLUMN balance_before REAL")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE deposits ADD COLUMN balance_after REAL")
        except sqlite3.OperationalError:
            pass
        c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            type TEXT,
            amount REAL,
            description TEXT,
            created_at TEXT
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS coupons (
            code TEXT PRIMARY KEY,
            discount_type TEXT,
            discount_value REAL,
            active INTEGER DEFAULT 1,
            target_role TEXT DEFAULT 'all_except_reseller',
            expires_at TEXT,
            per_user_limit INTEGER DEFAULT -1,
            created_at TEXT
        )""")
        for col, coldef in [("target_role", "TEXT DEFAULT 'all_except_reseller'"),
                            ("expires_at", "TEXT"),
                            ("per_user_limit", "INTEGER DEFAULT -1"),
                            ("created_at", "TEXT")]:
            try:
                c.execute(f"ALTER TABLE coupons ADD COLUMN {col} {coldef}")
            except sqlite3.OperationalError:
                pass
        c.execute("""
        CREATE TABLE IF NOT EXISTS coupon_usages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            telegram_id INTEGER,
            used_at TEXT
        )""")

        for cat in CATEGORIES:
            c.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat,))

        defaults = {
            "shop_name": "Satyam's Shop",
            "welcome_message": (
                f"👑 {stylize('WELCOME TO')} {{shop_name}} 👑\n\n"
                "👋 Hey {name}, welcome to our store! 🎉\n\n"
                f"🌟 {stylize('WHY CHOOSE US?')}\n\n"
                f"🚀 {stylize('Fastest Delivery:')} Get instant server-side keys within seconds.\n\n"
                f"⚡ {stylize('100% Automated:')} Fully operational cloud panel connection.\n\n"
                f"🤝 {stylize('24x7 Dedicated Support:')} Safe, authentic and reliable setup.\n\n"
                f"💰 {stylize('Best Competitive Prices:')} Premium configurations at low cost.\n\n"
                "✨━━━━━━━━━━━━━━━━━━━━✨\n\n"
                "👇 Use the buttons below to open menu options:"
            ),
            "how_to_use_link": "https://t.me/",
            "updated_file_group_link": "https://t.me/",
            "upi_id": "",
            "payee_name": "Satyam's Shop",
            "support_username": SUPPORT_ADMIN_USERNAME,
            "btn_label_shop": "🛍 Shop Now",
            "btn_label_deposit": "💵 Deposit",
            "btn_label_profile": "👤 Profile",
            "btn_label_orders": "📜 Order History",
            "btn_label_daily": "🎁 Daily Gift",
            "btn_label_payproof": "📩 Pay Proof",
            "pay_proof_group_link": "https://t.me/",
            "usd_rate": "90",
            "bdt_rate": "115",
            "binance_pay_id": "",
            "binance_api_key": "",
            "earnlinks_api_token": "",
            "binance_api_secret": "",
            "bkash_number": "",
            "nagad_number": "",
            "btn_label_pay_bkash": "📱 Pay via bKash",
            "btn_label_pay_nagad": "📱 Pay via Nagad",
            "btn_label_howto": "📘 How To Use",
            "btn_label_files": "📂 Updated File",
            "btn_label_support": "🆘 Contact Support",
            "text_shop_subtitle": (
                "🔥 Premium Mods, Panels &amp; Bypasses — all in one place!\n"
                "⚡ Instant delivery • 🔒 Verified sellers • 💯 Trusted by 1000+ buyers\n\n"
                "👇 Tap a category below to get started:"
            ),
            "text_category_prompt": "➡️ Choose a product 🦇❤️",
            "text_product_prompt": "📥 Choose your package to purchase:",
            "text_duration_prompt": "Choose a payment method:",
            "text_payment_unverified_msg": (
                "⏳ We couldn't confirm your payment automatically yet.\n\n"
                "💡 If you're sure you've already paid, tap below to contact the admin directly "
                "with your payment proof so they can verify it manually."
            ),
            "btn_label_paid_qr": "✅ I Have Paid",
            "btn_label_paid_binance": "📋 I Paid — Submit Order ID",
            "btn_label_cancel_order": "❌ Cancel Order",
            "btn_label_contact_proof": "🆘 Contact Admin with Payment Proof",
        }
        for k, v in defaults.items():
            c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))


# ------------------ USERS ------------------

def get_or_create_user(telegram_id, username, first_name):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        if row:
            conn.execute("UPDATE users SET username=?, first_name=? WHERE telegram_id=?",
                         (username, first_name, telegram_id))
            return dict(row)
        conn.execute(
            "INSERT INTO users (telegram_id, username, first_name, joined_at) VALUES (?, ?, ?, ?)",
            (telegram_id, username, first_name, _now())
        )
        row = conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        return dict(row)


def set_role_pre_start(telegram_id, role):
    """Sets a user's role by Telegram ID even if they've NEVER started the bot yet —
    creates a placeholder account (username/first_name filled in automatically the
    moment they do /start, via get_or_create_user) so the role sticks either way.
    Returns (user_dict, was_new_placeholder)."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        if row:
            conn.execute("UPDATE users SET role=? WHERE telegram_id=?", (role, telegram_id))
            row = conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
            return dict(row), False
        conn.execute(
            "INSERT INTO users (telegram_id, role, joined_at) VALUES (?, ?, ?)",
            (telegram_id, role, _now())
        )
        row = conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        return dict(row), True


def set_phone_number(telegram_id, phone_number):
    with get_conn() as conn:
        conn.execute("UPDATE users SET phone_number=? WHERE telegram_id=?", (phone_number, telegram_id))


def get_usd_rate():
    """How many INR equal $1. Default: 1 USD = 90 INR."""
    try:
        return float(get_setting("usd_rate", "90"))
    except ValueError:
        return 90.0


def get_bdt_rate():
    """How many BDT equal $1. Default: 1 USD = 115 BDT (i.e. 90 INR = 115 BDT)."""
    try:
        return float(get_setting("bdt_rate", "115"))
    except ValueError:
        return 115.0


def inr_to_usd(inr_amount):
    rate = get_usd_rate()
    return round(inr_amount / rate, 2) if rate else 0.0


def usd_to_inr(usd_amount):
    rate = get_usd_rate()
    return round(usd_amount * rate, 2)


def inr_to_bdt(inr_amount):
    """Converts an INR amount to BDT via USD (INR -> USD -> BDT), matching the
    1 USD = 90 INR = 115 BDT rule."""
    usd_rate = get_usd_rate()
    bdt_rate = get_bdt_rate()
    if not usd_rate:
        return 0.0
    return round((inr_amount / usd_rate) * bdt_rate, 2)


def usd_to_bdt(usd_amount):
    rate = get_bdt_rate()
    return round(usd_amount * rate, 2)


# ------------------ COUPONS ------------------

def add_coupon(code, discount_type, discount_value, target_role="all_except_reseller",
                duration_hours=None, per_user_limit=-1):
    expires_at = None
    if duration_hours:
        expires_at = (datetime.datetime.utcnow() + datetime.timedelta(hours=duration_hours)).isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO coupons (code, discount_type, discount_value, active, target_role, "
            "expires_at, per_user_limit, created_at) VALUES (?, ?, ?, 1, ?, ?, ?, ?) "
            "ON CONFLICT(code) DO UPDATE SET discount_type=excluded.discount_type, "
            "discount_value=excluded.discount_value, active=1, target_role=excluded.target_role, "
            "expires_at=excluded.expires_at, per_user_limit=excluded.per_user_limit",
            (code.upper(), discount_type, discount_value, target_role, expires_at, per_user_limit, _now())
        )


def get_coupon(code):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM coupons WHERE code=?", (code.upper(),)).fetchone()
        return dict(row) if row else None


def list_coupons():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM coupons ORDER BY code").fetchall()
        return [dict(r) for r in rows]


def delete_coupon(code):
    with get_conn() as conn:
        conn.execute("DELETE FROM coupons WHERE code=?", (code.upper(),))
        conn.execute("DELETE FROM coupon_usages WHERE code=?", (code.upper(),))


def coupon_usage_count(code, telegram_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) c FROM coupon_usages WHERE code=? AND telegram_id=?",
            (code.upper(), telegram_id)
        ).fetchone()
        return row["c"]


def record_coupon_usage(code, telegram_id):
    with get_conn() as conn:
        conn.execute("INSERT INTO coupon_usages (code, telegram_id, used_at) VALUES (?, ?, ?)",
                      (code.upper(), telegram_id, _now()))


def validate_coupon(code, telegram_id, role):
    """Returns (coupon_dict, error_message). error_message is None if the coupon is usable."""
    coupon = get_coupon(code)
    if not coupon or not coupon["active"]:
        return None, "❌ Invalid or expired coupon code."
    if coupon["expires_at"]:
        if datetime.datetime.utcnow() > datetime.datetime.fromisoformat(coupon["expires_at"]):
            return None, "❌ This coupon has expired."
    target = coupon["target_role"]
    if target == "reseller" and role != "reseller":
        return None, "❌ This coupon is only valid for resellers."
    if target == "all_except_reseller" and role == "reseller":
        return None, "❌ This coupon isn't valid for resellers."
    limit = coupon["per_user_limit"]
    if limit is not None and limit >= 0:
        used = coupon_usage_count(code, telegram_id)
        if used >= limit:
            return None, f"❌ You've already used this coupon the maximum number of times ({limit})."
    return coupon, None


def apply_coupon_discount(price_inr, code):
    """Returns discounted price, or the original price if the coupon is invalid/inactive.
    NOTE: this only applies the discount math - use validate_coupon() first for role/expiry/limit checks."""
    coupon = get_coupon(code)
    if not coupon or not coupon["active"]:
        return price_inr, False
    if coupon["discount_type"] == "percent":
        new_price = round(price_inr * (1 - coupon["discount_value"] / 100), 2)
    else:
        new_price = max(0, round(price_inr - coupon["discount_value"], 2))
    return new_price, True


def set_order_delivered_key(order_id, key_text):
    with get_conn() as conn:
        conn.execute("UPDATE orders SET delivered_key=? WHERE id=?", (key_text, order_id))


# ------------------ STALE TRANSACTION CLEANUP ------------------

def cancel_stale_transactions(minutes=5):
    """Auto-cancels orders/deposits still untouched ('pending') after N minutes.
    Returns (cancelled_orders, cancelled_deposits) as lists of dicts for notification purposes."""
    cutoff = (datetime.datetime.utcnow() - datetime.timedelta(minutes=minutes)).isoformat()
    with get_conn() as conn:
        stale_orders = conn.execute(
            "SELECT * FROM orders WHERE status='pending' AND created_at < ?", (cutoff,)
        ).fetchall()
        stale_orders = [dict(r) for r in stale_orders]
        for o in stale_orders:
            conn.execute("UPDATE orders SET status='cancelled' WHERE id=?", (o["id"],))

        stale_deposits = conn.execute(
            "SELECT * FROM deposits WHERE status='pending' AND created_at < ?", (cutoff,)
        ).fetchall()
        stale_deposits = [dict(r) for r in stale_deposits]
        for d in stale_deposits:
            conn.execute("UPDATE deposits SET status='cancelled' WHERE id=?", (d["id"],))
    return stale_orders, stale_deposits


def get_user(telegram_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        return dict(row) if row else None


def is_admin(telegram_id):
    return telegram_id in ADMIN_IDS


def is_banned(telegram_id):
    u = get_user(telegram_id)
    return bool(u and u["banned"])


def list_users(role=None):
    with get_conn() as conn:
        if role:
            rows = conn.execute("SELECT * FROM users WHERE role=? AND banned=0", (role,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM users WHERE banned=0").fetchall()
        return [dict(r) for r in rows]


def set_role(telegram_id, role):
    with get_conn() as conn:
        conn.execute("UPDATE users SET role=? WHERE telegram_id=?", (role, telegram_id))


def ban_user(telegram_id):
    with get_conn() as conn:
        conn.execute("UPDATE users SET banned=1 WHERE telegram_id=?", (telegram_id,))


def list_banned_users():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM users WHERE banned=1").fetchall()
        return [dict(r) for r in rows]


def unban_user(telegram_id):
    with get_conn() as conn:
        conn.execute("UPDATE users SET banned=0 WHERE telegram_id=?", (telegram_id,))


def adjust_balance(telegram_id, delta, tx_type, description):
    with get_conn() as conn:
        conn.execute("UPDATE users SET balance = balance + ? WHERE telegram_id=?", (delta, telegram_id))
        conn.execute(
            "INSERT INTO transactions (telegram_id, type, amount, description, created_at) VALUES (?,?,?,?,?)",
            (telegram_id, tx_type, delta, description, _now())
        )


def reset_all_balances():
    """Zeroes out every user's wallet balance. Logs a transaction per affected user
    so it's auditable in their history. Returns (affected_count, total_wiped)."""
    with get_conn() as conn:
        rows = conn.execute("SELECT telegram_id, balance FROM users WHERE balance != 0").fetchall()
        total_wiped = sum(r["balance"] for r in rows)
        for r in rows:
            conn.execute(
                "INSERT INTO transactions (telegram_id, type, amount, description, created_at) "
                "VALUES (?,?,?,?,?)",
                (r["telegram_id"], "admin_reset", -r["balance"], "Balance reset to ₹0 by admin", _now())
            )
        conn.execute("UPDATE users SET balance = 0")
        return len(rows), total_wiped


REFERRAL_COMMISSION_RATE = 0.05  # 5% — applies to BOTH deposits and product purchases


def set_referrer(telegram_id, referrer_id):
    """Tags a brand-new user with who referred them. Only takes effect if the user
    doesn't already have a referrer, the referrer isn't the user themself, and the
    referrer actually exists. Call this ONLY for genuinely new users (never for
    someone who already had an account) so referral counts stay honest."""
    if not referrer_id or referrer_id == telegram_id:
        return False
    with get_conn() as conn:
        referrer_exists = conn.execute(
            "SELECT 1 FROM users WHERE telegram_id=?", (referrer_id,)).fetchone()
        if not referrer_exists:
            return False
        row = conn.execute("SELECT referred_by FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        if row is None or row["referred_by"] is not None:
            return False
        conn.execute("UPDATE users SET referred_by=? WHERE telegram_id=?", (referrer_id, telegram_id))
        return True


def count_referrals(telegram_id):
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM users WHERE referred_by=?", (telegram_id,)).fetchone()
        return row["c"] if row else 0


def credit_referral_commission(telegram_id, amount, source_label):
    """Pays the referrer their 5% commission the instant a REFERRED user (still role
    'user' — resellers no longer earn their referrer anything) completes a deposit or
    product purchase. Credits the referrer's wallet balance immediately and bumps
    their lifetime referral_bonus_earned counter. Returns
    (referrer_id, commission_amount, referrer_new_balance) or None if not applicable."""
    user = get_user(telegram_id)
    if not user or not user.get("referred_by") or user.get("role") != "user":
        return None
    referrer_id = user["referred_by"]
    referrer = get_user(referrer_id)
    if not referrer:
        return None
    commission = round(amount * REFERRAL_COMMISSION_RATE, 2)
    if commission <= 0:
        return None
    adjust_balance(referrer_id, commission, "referral_bonus",
                    f"5% referral commission from {source_label} by user #{telegram_id}")
    with get_conn() as conn:
        conn.execute("UPDATE users SET referral_bonus_earned = referral_bonus_earned + ? WHERE telegram_id=?",
                     (commission, referrer_id))
    new_balance = get_user(referrer_id)["balance"]
    return referrer_id, commission, new_balance


def get_user_stats(telegram_id):
    with get_conn() as conn:
        total_deposit = conn.execute(
            "SELECT COALESCE(SUM(amount),0) s FROM deposits WHERE telegram_id=? AND status='completed'",
            (telegram_id,)
        ).fetchone()["s"]
        completed_orders = conn.execute(
            "SELECT COUNT(*) c FROM orders WHERE telegram_id=? AND status='completed'", (telegram_id,)
        ).fetchone()["c"]
        gift_earned = conn.execute(
            "SELECT COALESCE(SUM(amount),0) s FROM transactions WHERE telegram_id=? AND type='daily_gift'",
            (telegram_id,)
        ).fetchone()["s"]
        return {
            "total_deposit": total_deposit,
            "completed_orders": completed_orders,
            "gift_earned": gift_earned,
        }


def list_transactions(telegram_id, limit=15):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE telegram_id=? ORDER BY id DESC LIMIT ?",
            (telegram_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]


# ------------------ CATEGORIES / PRODUCTS ------------------

def list_categories():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM categories ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def get_category(cat_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM categories WHERE id=?", (cat_id,)).fetchone()
        return dict(row) if row else None


def add_category(name, icon=None):
    with get_conn() as conn:
        cur = conn.execute("INSERT INTO categories (name, icon) VALUES (?, ?)", (name, icon))
        return cur.lastrowid


def update_category_name(cat_id, new_name, icon=None):
    with get_conn() as conn:
        if icon is not None:
            conn.execute("UPDATE categories SET name=?, icon=? WHERE id=?", (new_name, icon, cat_id))
        else:
            conn.execute("UPDATE categories SET name=? WHERE id=?", (new_name, cat_id))


def delete_category(cat_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM categories WHERE id=?", (cat_id,))


def add_product(category_id, name, visibility="all", icon=None):
    with get_conn() as conn:
        conn.execute("INSERT INTO products (category_id, name, visibility, icon) VALUES (?, ?, ?, ?)",
                     (category_id, name, visibility, icon))


def list_products(category_id, role=None):
    """role=None (admin) sees everything. role='user' sees only visibility='all'.
    role='reseller' sees everything (all + reseller_only)."""
    with get_conn() as conn:
        if role == "user":
            rows = conn.execute(
                "SELECT * FROM products WHERE category_id=? AND visibility='all'", (category_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM products WHERE category_id=?", (category_id,)).fetchall()
        return [dict(r) for r in rows]


def get_product(product_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        return dict(row) if row else None


def update_product_name(product_id, new_name, icon=None):
    with get_conn() as conn:
        if icon is not None:
            conn.execute("UPDATE products SET name=?, icon=? WHERE id=?", (new_name, icon, product_id))
        else:
            conn.execute("UPDATE products SET name=? WHERE id=?", (new_name, product_id))


def delete_product(product_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM products WHERE id=?", (product_id,))


# ------------------ DURATIONS ------------------

def add_duration(product_id, label, icon=None):
    with get_conn() as conn:
        conn.execute("INSERT INTO durations (product_id, label, icon) VALUES (?, ?, ?)",
                     (product_id, label, icon))


def list_durations(product_id):
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM durations WHERE product_id=?", (product_id,)).fetchall()
        return [dict(r) for r in rows]


def get_duration(duration_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM durations WHERE id=?", (duration_id,)).fetchone()
        return dict(row) if row else None


def update_duration_label(duration_id, new_label, icon=None):
    with get_conn() as conn:
        if icon is not None:
            conn.execute("UPDATE durations SET label=?, icon=? WHERE id=?", (new_label, icon, duration_id))
        else:
            conn.execute("UPDATE durations SET label=? WHERE id=?", (new_label, duration_id))


def delete_duration(duration_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM durations WHERE id=?", (duration_id,))


# ------------------ PRICES ------------------

def set_price_all(duration_id, price):
    with get_conn() as conn:
        conn.execute("DELETE FROM prices WHERE duration_id=? AND scope='all'", (duration_id,))
        conn.execute("INSERT INTO prices (duration_id, scope, price) VALUES (?, 'all', ?)", (duration_id, price))


def set_price_reseller(duration_id, price):
    with get_conn() as conn:
        conn.execute("DELETE FROM prices WHERE duration_id=? AND scope='reseller'", (duration_id,))
        conn.execute("INSERT INTO prices (duration_id, scope, price) VALUES (?, 'reseller', ?)", (duration_id, price))


def set_price_user(duration_id, telegram_id, price):
    with get_conn() as conn:
        conn.execute("DELETE FROM prices WHERE duration_id=? AND scope='user' AND telegram_id=?",
                     (duration_id, telegram_id))
        conn.execute("INSERT INTO prices (duration_id, scope, telegram_id, price) VALUES (?, 'user', ?, ?)",
                     (duration_id, telegram_id, price))


def get_price_for_user(duration_id, telegram_id, role):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT price FROM prices WHERE duration_id=? AND scope='user' AND telegram_id=?",
            (duration_id, telegram_id)
        ).fetchone()
        if row:
            return row["price"]
        if role == "reseller":
            row = conn.execute(
                "SELECT price FROM prices WHERE duration_id=? AND scope='reseller'", (duration_id,)
            ).fetchone()
            if row:
                return row["price"]
        row = conn.execute(
            "SELECT price FROM prices WHERE duration_id=? AND scope='all'", (duration_id,)
        ).fetchone()
        return row["price"] if row else None


# ------------------ STOCK KEYS ------------------

def add_keys(duration_id, keys):
    with get_conn() as conn:
        for k in keys:
            k = k.strip()
            if k:
                conn.execute("INSERT INTO stock_keys (duration_id, key_text) VALUES (?, ?)", (duration_id, k))


def count_available_keys(duration_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) c FROM stock_keys WHERE duration_id=? AND is_sold=0", (duration_id,)
        ).fetchone()
        return row["c"]


def pop_key(duration_id, telegram_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM stock_keys WHERE duration_id=? AND is_sold=0 LIMIT 1", (duration_id,)
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE stock_keys SET is_sold=1, sold_to=?, sold_at=? WHERE id=?",
            (telegram_id, _now(), row["id"])
        )
        return row["key_text"]


# ------------------ TRIAL ------------------

def add_trial_product(name, icon=None):
    with get_conn() as conn:
        cur = conn.execute("INSERT INTO trial_products (name, icon) VALUES (?, ?)", (name, icon))
        return cur.lastrowid


def list_trial_products():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM trial_products ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def get_trial_product(trial_product_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM trial_products WHERE id=?", (trial_product_id,)).fetchone()
        return dict(row) if row else None


def update_trial_product_name(trial_product_id, new_name, icon=None):
    with get_conn() as conn:
        if icon is not None:
            conn.execute("UPDATE trial_products SET name=?, icon=? WHERE id=?",
                         (new_name, icon, trial_product_id))
        else:
            conn.execute("UPDATE trial_products SET name=? WHERE id=?", (new_name, trial_product_id))


def update_trial_product_link(trial_product_id, link):
    """Admin-set delivery link for a trial product (Manage Trial > product > Set Link).
    When set, this is what users are sent when they claim a trial instead of the
    bot's own auto-generated one-time redeem link. Pass None/'' to clear it."""
    with get_conn() as conn:
        conn.execute("UPDATE trial_products SET link=? WHERE id=?", (link or None, trial_product_id))


def delete_trial_product(trial_product_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM trial_products WHERE id=?", (trial_product_id,))


def add_trial_keys(trial_product_id, keys):
    with get_conn() as conn:
        for k in keys:
            k = k.strip()
            if k:
                conn.execute("INSERT INTO trial_keys (trial_product_id, key_text) VALUES (?, ?)",
                             (trial_product_id, k))


def count_available_trial_keys(trial_product_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) c FROM trial_keys WHERE trial_product_id=? AND is_used=0", (trial_product_id,)
        ).fetchone()
        return row["c"]


def has_claimed_trial(telegram_id, trial_product_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM trial_keys WHERE trial_product_id=? AND used_by=? LIMIT 1",
            (trial_product_id, telegram_id)
        ).fetchone()
        return row is not None


def pop_trial_key(trial_product_id, telegram_id):
    """Gives one trial key to this user for this product. Returns the key text,
    or None if out of stock. Each user can only claim one key per trial product
    (checked separately via has_claimed_trial before calling this)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM trial_keys WHERE trial_product_id=? AND is_used=0 LIMIT 1", (trial_product_id,)
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE trial_keys SET is_used=1, used_by=?, used_at=? WHERE id=?",
            (telegram_id, _now(), row["id"])
        )
        return row["key_text"]


# ------------------ ORDERS ------------------

def create_order(telegram_id, product_id, duration_id, price, method, coupon_code=None):
    reference = _gen_reference("ORD")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO orders (telegram_id, product_id, duration_id, price, method, status, reference, "
            "coupon_code, created_at) VALUES (?,?,?,?,?, 'pending', ?, ?, ?)",
            (telegram_id, product_id, duration_id, price, method, reference, coupon_code, _now())
        )
        return cur.lastrowid


def get_order(order_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        return dict(row) if row else None


def set_order_status(order_id, status, screenshot_file_id=None):
    with get_conn() as conn:
        if screenshot_file_id:
            conn.execute("UPDATE orders SET status=?, screenshot_file_id=? WHERE id=?",
                         (status, screenshot_file_id, order_id))
        else:
            conn.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))


def set_order_binance_id(order_id, binance_order_id):
    with get_conn() as conn:
        conn.execute("UPDATE orders SET binance_order_id=? WHERE id=?", (binance_order_id, order_id))


def set_order_gateway_order(order_id, gateway_order_id, expires_at=None):
    with get_conn() as conn:
        conn.execute("UPDATE orders SET gateway_order_id=?, gateway_expires_at=? WHERE id=?",
                     (gateway_order_id, expires_at, order_id))


def list_pending_gateway_orders():
    """Orders waiting on FamPay auto-verify (method='qr', has a gateway_order_id, still 'pending')."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM orders WHERE status='pending' AND method='qr' "
            "AND gateway_order_id IS NOT NULL AND gateway_order_id != ''"
        ).fetchall()
        return [dict(r) for r in rows]


def is_binance_order_id_used(binance_order_id, exclude_kind=None, exclude_id=None):
    """Checks whether this Binance Order ID has already been submitted on any OTHER
    order or deposit that isn't cancelled/rejected. Prevents someone reusing a single
    real payment's Order ID to claim multiple purchases/deposits."""
    with get_conn() as conn:
        order_query = ("SELECT id FROM orders WHERE binance_order_id=? "
                        "AND status NOT IN ('cancelled', 'rejected')")
        order_params = [binance_order_id]
        if exclude_kind == "order" and exclude_id is not None:
            order_query += " AND id != ?"
            order_params.append(exclude_id)
        if conn.execute(order_query, order_params).fetchone():
            return True

        dep_query = ("SELECT id FROM deposits WHERE binance_order_id=? "
                      "AND status NOT IN ('cancelled', 'rejected')")
        dep_params = [binance_order_id]
        if exclude_kind == "deposit" and exclude_id is not None:
            dep_query += " AND id != ?"
            dep_params.append(exclude_id)
        if conn.execute(dep_query, dep_params).fetchone():
            return True
    return False


def list_pending_orders():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM orders WHERE status='review' ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def list_user_orders(telegram_id, limit=20):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM orders WHERE telegram_id=? AND status='completed' ORDER BY id DESC LIMIT ?",
            (telegram_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]


# ------------------ DEPOSITS ------------------

def create_deposit(telegram_id, amount, method="upi", purpose="deposit"):
    reference = _gen_reference("DEP")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO deposits (telegram_id, amount, method, status, reference, created_at, purpose) "
            "VALUES (?, ?, ?, 'pending', ?, ?, ?)",
            (telegram_id, amount, method, reference, _now(), purpose)
        )
        return cur.lastrowid


def get_deposit(deposit_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM deposits WHERE id=?", (deposit_id,)).fetchone()
        return dict(row) if row else None


def set_deposit_binance_id(deposit_id, binance_order_id):
    with get_conn() as conn:
        conn.execute("UPDATE deposits SET binance_order_id=? WHERE id=?", (binance_order_id, deposit_id))


def set_deposit_gateway_order(deposit_id, gateway_order_id, expires_at=None):
    with get_conn() as conn:
        conn.execute("UPDATE deposits SET gateway_order_id=?, gateway_expires_at=? WHERE id=?",
                     (gateway_order_id, expires_at, deposit_id))


def list_pending_gateway_deposits():
    """Deposits waiting on FamPay auto-verify (method='upi', has a gateway_order_id, still 'pending')."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM deposits WHERE status='pending' AND method='upi' "
            "AND gateway_order_id IS NOT NULL AND gateway_order_id != ''"
        ).fetchall()
        return [dict(r) for r in rows]


def set_deposit_status(deposit_id, status, screenshot_file_id=None):
    with get_conn() as conn:
        if screenshot_file_id:
            conn.execute("UPDATE deposits SET status=?, screenshot_file_id=? WHERE id=?",
                         (status, screenshot_file_id, deposit_id))
        else:
            conn.execute("UPDATE deposits SET status=? WHERE id=?", (status, deposit_id))


def set_deposit_balances(deposit_id, balance_before, balance_after):
    """Snapshots the wallet balance right before/after a deposit is credited, so
    Transaction History can show it later without recomputing from the transactions log."""
    with get_conn() as conn:
        conn.execute("UPDATE deposits SET balance_before=?, balance_after=? WHERE id=?",
                     (balance_before, balance_after, deposit_id))


def list_recent_completed_deposits(telegram_id, limit=5):
    """Only successful (status='completed') wallet deposits — excludes reseller-upgrade
    payments, which don't credit the wallet balance the same way."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM deposits WHERE telegram_id=? AND status='completed' AND purpose='deposit' "
            "ORDER BY id DESC LIMIT ?", (telegram_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]


def list_pending_deposits():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM deposits WHERE status='review' ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def list_user_deposits(telegram_id, limit=20):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM deposits WHERE telegram_id=? ORDER BY id DESC LIMIT ?", (telegram_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]


def count_completed_deposits(telegram_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) c FROM deposits WHERE telegram_id=? AND status='completed'", (telegram_id,)
        ).fetchone()
        return row["c"]


def count_successful_deposits(telegram_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) c FROM deposits WHERE telegram_id=? AND status='completed'", (telegram_id,)
        ).fetchone()
        return row["c"]


def list_user_deposits(telegram_id, limit=20):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM deposits WHERE telegram_id=? ORDER BY id DESC LIMIT ?", (telegram_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]


# ------------------ SETTINGS ------------------

def get_setting(key, default=""):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


# ------------------ MAINTENANCE MODE ------------------

def is_maintenance_mode():
    return get_setting("maintenance_mode", "0") == "1"


def set_maintenance_mode(enabled):
    set_setting("maintenance_mode", "1" if enabled else "0")


# ------------------ RESELLER UPGRADE ------------------

def get_reseller_fee():
    try:
        return float(get_setting("reseller_fee", "0"))
    except ValueError:
        return 0.0


def is_trial_button_enabled():
    return get_setting("trial_button_enabled", "1") == "1"


def set_trial_button_enabled(enabled):
    set_setting("trial_button_enabled", "1" if enabled else "0")


def is_reseller_button_enabled():
    return get_setting("reseller_button_enabled", "0") == "1"


def set_reseller_button_enabled(enabled, fee=None):
    set_setting("reseller_button_enabled", "1" if enabled else "0")
    if fee is not None:
        set_setting("reseller_fee", str(fee))


def set_setting(key, value):
    with get_conn() as conn:
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def delete_setting(key):
    with get_conn() as conn:
        conn.execute("DELETE FROM settings WHERE key=?", (key,))


# ------------------ DAILY GIFT ------------------

def can_claim_daily_gift(telegram_id):
    u = get_user(telegram_id)
    if not u or not u["last_daily_gift"]:
        return True
    last = datetime.datetime.fromisoformat(u["last_daily_gift"])
    return (datetime.datetime.utcnow() - last) >= datetime.timedelta(hours=24)


def time_until_next_gift(telegram_id):
    """Returns a timedelta of how long until the user can claim again, or None if they can claim now."""
    u = get_user(telegram_id)
    if not u or not u["last_daily_gift"]:
        return None
    last = datetime.datetime.fromisoformat(u["last_daily_gift"])
    next_time = last + datetime.timedelta(hours=24)
    now = datetime.datetime.utcnow()
    if now >= next_time:
        return None
    return next_time - now


def claim_daily_gift(telegram_id, dice_value):
    reward = round(dice_value * 0.5, 2)
    with get_conn() as conn:
        conn.execute("UPDATE users SET last_daily_gift=? WHERE telegram_id=?", (_now(), telegram_id))
        conn.execute("UPDATE users SET balance = balance + ? WHERE telegram_id=?", (reward, telegram_id))
        conn.execute(
            "INSERT INTO transactions (telegram_id, type, amount, description, created_at) VALUES (?,?,?,?,?)",
            (telegram_id, "daily_gift", reward, f"Daily spin gift (dice={dice_value})", _now())
        )
    return reward


def can_request_shortener(telegram_id):
    """Trial requests are no longer rate-limited — a user can claim as many
    times as trial stock/eligibility (per-product) allows."""
    return True


def record_shortener_request(telegram_id):
    set_setting(f"shortener_ts_{telegram_id}", datetime.datetime.utcnow().isoformat())


def shortener_cooldown_remaining(telegram_id):
    """24h cooldown removed — always returns None (no wait)."""
    return None
