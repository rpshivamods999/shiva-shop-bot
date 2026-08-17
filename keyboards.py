from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import re

import database as db

_HTML_TAG_RE = re.compile(r"<[^>]+>")


# ============ CUSTOM EMOJI ICONS (Bot API 9.4) ============
# Icons are now set the SAME place you edit a button's text/emoji (the
# "Customize Buttons" admin menu) - just send a message containing a real
# Telegram custom/Premium emoji and the bot will auto-detect and save its
# custom_emoji_id as that button's icon. Stored per-key as `icon_<key>`.
# Requires the bot owner account to have Telegram Premium, otherwise the
# icon is silently ignored by Telegram (no crash either way).

def get_icon(key):
    """Look up the custom_emoji_id saved for this button key, if any.
    In 'basic' theme, icons are suppressed globally even if one is saved,
    so /basic instantly strips the 3D icons without losing the saved data."""
    if get_theme() == "basic":
        return None
    return db.get_setting(f"icon_{key}", None) or None


# ============ GLOBAL LOOK: /premium vs /basic (admin-only commands) ============
# A single DB setting ("ui_theme") that the whole bot checks. "premium" (default)
# = full colours + 3D custom-emoji icons wherever they're set. "basic" = every
# button falls back to Telegram's plain grey style with no icon, regardless of
# what's saved per-button. Nothing per-button gets deleted - it's just hidden.

def get_theme():
    return db.get_setting("ui_theme", "premium")


def set_theme(value):
    db.set_setting("ui_theme", value)


def btn(text, callback_data=None, url=None, style=None, icon=None):
    """Build an InlineKeyboardButton, optionally with Bot API 9.4 extras:
    - style: 'primary' | 'success' | 'danger' -> colors the button.
    - icon: a Telegram *custom emoji* id (string of digits) -> shows that custom
      emoji as an icon on the button via the new `icon_custom_emoji_id` field.
      NOTE: this only renders if the bot's owner account has Telegram Premium,
      and `icon` must be a real custom_emoji_id (not a normal unicode emoji).
    python-telegram-bot doesn't have native params for these yet, so we pass
    them via api_kwargs (forward-compat mechanism that sends extra raw fields
    straight through to the Telegram Bot API).

    Global look: in 'basic' theme (set via /basic), colour and icon are
    stripped from EVERY button bot-wide, even ones with a hardcoded style=
    in the code below - so admin only needs the one switch. /premium restores
    whatever colour/icon was actually passed in / saved per-button."""
    if get_theme() == "basic":
        style = None
        icon = None
    kwargs = {}
    if callback_data is not None:
        kwargs["callback_data"] = callback_data
    if url is not None:
        kwargs["url"] = url
    api_kwargs = {}
    if style:
        api_kwargs["style"] = style
    if icon:
        api_kwargs["icon_custom_emoji_id"] = icon
    if api_kwargs:
        kwargs["api_kwargs"] = api_kwargs
    return InlineKeyboardButton(text, **kwargs)


def rows(buttons, cols=2):
    """buttons = list of InlineKeyboardButton -> chunk into rows of `cols`."""
    return [buttons[i:i + cols] for i in range(0, len(buttons), cols)]


# ================= ADMIN =================

def admin_main_menu():
    btns = [
        btn("👤 Users", callback_data="adm_users", style="primary"),
        btn("🔴 Resellers", callback_data="adm_resellers", style="primary"),
        btn("🚫 Banned Users", callback_data="adm_banned", style="danger"),
        btn("🟢 Manage Products", callback_data="adm_products", style="primary"),
        btn("🎁 Manage Trial", callback_data="adm_trial", style="primary"),
        btn("💳 Pending Payments", callback_data="adm_pending", style="primary"),
        btn("💵 Manage Balance", callback_data="adm_balance", style="primary"),
        btn("👑 Admins", callback_data="adm_admin_list", style="primary"),
        btn("⚙️ Settings", callback_data="adm_settings", style="primary"),
        btn("🔄 Refresh Sales", callback_data="adm_refresh_sales", style="primary"),
    ]
    return InlineKeyboardMarkup(rows(btns, 2))


def back_button(cb):
    """Shared 'Back' button used throughout the bot. Customizable via
    Settings -> Customize Buttons (key: 'back') for both label text and
    a 3D custom emoji icon."""
    return btn(db.get_setting("btn_label_back", "🔙 Back"), callback_data=cb, style="danger", icon=get_icon("back"))


def back_btn(cb):
    return InlineKeyboardMarkup([[back_button(cb)]])


def user_list_kb(users):
    btns = [btn(f"👤 {u['first_name'] or u['username'] or u['telegram_id']}",
                callback_data=f"adm_u_{u['telegram_id']}", style="primary") for u in users]
    kb = rows(btns, 2)
    kb.append([back_button("adm_back_main")])
    return InlineKeyboardMarkup(kb)


def user_detail_kb(tid):
    return InlineKeyboardMarkup([
        [btn("⬆️ Promote to Reseller", callback_data=f"adm_promote_{tid}", style="success")],
        [btn("🚫 Ban User", callback_data=f"adm_ban_{tid}", style="danger")],
        [back_button("adm_users")],
    ])


def banned_user_list_kb(users):
    btns = [btn(f"🚫 {u['first_name'] or u['username'] or u['telegram_id']}",
                callback_data=f"adm_bu_{u['telegram_id']}", style="primary") for u in users]
    kb = rows(btns, 2)
    kb.append([back_button("adm_back_main")])
    return InlineKeyboardMarkup(kb)


def banned_user_detail_kb(tid):
    return InlineKeyboardMarkup([
        [btn("✅ Unban User", callback_data=f"adm_unban_{tid}", style="success")],
        [back_button("adm_banned")],
    ])


def reseller_list_kb(resellers):
    btns = [btn(f"🔴 {r['first_name'] or r['username'] or r['telegram_id']}",
                callback_data=f"adm_r_{r['telegram_id']}", style="primary") for r in resellers]
    kb = rows(btns, 2)
    kb.append([back_button("adm_back_main")])
    return InlineKeyboardMarkup(kb)


def reseller_detail_kb(tid):
    return InlineKeyboardMarkup([
        [btn("⬇️ Demote to User", callback_data=f"adm_demote_{tid}", style="danger")],
        [back_button("adm_resellers")],
    ])


def categories_kb(categories, prefix="adm_cat"):
    kb = [[btn(f"🟢 {c['name']}", callback_data=f"{prefix}_{c['id']}", style="primary")] for c in categories]
    if prefix == "adm_cat":
        kb.append([btn("➕ Add Category", callback_data="adm_addcat", style="success")])
    kb.append([back_button("adm_back_main")])
    return InlineKeyboardMarkup(kb)


def products_kb(products, cat_id):
    btns = [btn(f"📦 {p['name']}" + (" 🔴 Reseller" if p.get('visibility') == 'reseller_only' else ""),
                callback_data=f"adm_prod_{p['id']}", style="primary") for p in products]
    kb = rows(btns, 2)
    kb.append([btn("➕ Add Product", callback_data=f"adm_addprod_{cat_id}", style="success")])
    kb.append([btn("✏️ Rename Category", callback_data=f"adm_renamecat_{cat_id}", style="primary")])
    kb.append([btn("🗑 Delete Category", callback_data=f"adm_delcat_{cat_id}", style="danger")])
    kb.append([back_button("adm_products")])
    return InlineKeyboardMarkup(kb)


def product_visibility_kb():
    return InlineKeyboardMarkup([
        [btn("🌍 All Users (User + Reseller)", callback_data="adm_prodvis_all", style="primary")],
        [btn("🔴 Reseller Only", callback_data="adm_prodvis_reseller", style="danger")],
    ])


def durations_kb(durations, product_id, cat_id):
    btns = [btn(f"⏳ {d['label']}", callback_data=f"adm_dur_{d['id']}", style="primary") for d in durations]
    kb = rows(btns, 2)
    kb.append([btn("➕ Add Duration", callback_data=f"adm_adddur_{product_id}", style="success")])
    kb.append([btn("✏️ Rename Product", callback_data=f"adm_renameprod_{product_id}", style="primary")])
    kb.append([btn("🔗 Get Share Link", callback_data=f"adm_sharelink_{product_id}", style="primary")])
    kb.append([btn("🗑 Delete Product", callback_data=f"adm_delprod_{product_id}_{cat_id}", style="danger")])
    kb.append([back_button(f"adm_cat_{cat_id}")])
    return InlineKeyboardMarkup(kb)


def duration_detail_kb(duration_id, product_id):
    return InlineKeyboardMarkup([
        [btn("🔑 Stock Key", callback_data=f"adm_stock_{duration_id}", style="primary")],
        [btn("💰 Set Price", callback_data=f"adm_setprice_{duration_id}", style="primary")],
        [btn("✏️ Rename Duration", callback_data=f"adm_renamedur_{duration_id}", style="primary")],
        [btn("🗑 Delete Duration", callback_data=f"adm_deldur_{duration_id}_{product_id}", style="danger")],
        [back_button(f"adm_prod_{product_id}")],
    ])


# ================= TRIAL (ADMIN) =================

def admin_trial_menu_kb(trial_products):
    btns = [btn(f"🎁 {tp['name']}", callback_data=f"adm_trialprod_{tp['id']}", style="primary")
            for tp in trial_products]
    kb = rows(btns, 2)
    kb.append([btn("➕ Add Trial Product", callback_data="adm_addtrial", style="success")])
    kb.append([back_button("adm_back_main")])
    return InlineKeyboardMarkup(kb)


def admin_trial_product_kb(trial_product_id):
    link_set = bool(db.get_trial_product(trial_product_id).get("link"))
    link_label = "🔗 Change Link" if link_set else "🔗 Set Link"
    return InlineKeyboardMarkup([
        [btn("🔑 Add Trial Key(s)", callback_data=f"adm_addtrialkeys_{trial_product_id}", style="primary")],
        [btn(link_label, callback_data=f"adm_settriallink_{trial_product_id}", style="success")],
        [btn("✏️ Rename", callback_data=f"adm_renametrial_{trial_product_id}", style="primary")],
        [btn("🗑 Delete Trial Product", callback_data=f"adm_deltrial_{trial_product_id}", style="danger")],
        [back_button("adm_trial")],
    ])


def price_scope_kb(duration_id):
    return InlineKeyboardMarkup([
        [btn("🌍 All User", callback_data=f"adm_price_all_{duration_id}", style="primary")],
        [btn("🔴 Reseller", callback_data=f"adm_price_reseller_{duration_id}", style="primary")],
        [btn("🎯 Specific User", callback_data=f"adm_price_user_{duration_id}", style="primary")],
        [back_button(f"adm_dur_{duration_id}")],
    ])


def pending_item_kb(kind, item_id):
    return InlineKeyboardMarkup([
        [btn("✅ Verify", callback_data=f"adm_v{kind}_{item_id}", style="success"),
         btn("❌ Reject", callback_data=f"adm_r{kind}_{item_id}", style="danger")]
    ])


def order_review_kb(order_id):
    return InlineKeyboardMarkup([
        [btn("✅ Approve Order", callback_data=f"adm_vorder_{order_id}", style="success"),
         btn("❌ Decline Order", callback_data=f"adm_rorder_{order_id}", style="danger")]
    ])


def deposit_review_kb(deposit_id):
    return InlineKeyboardMarkup([
        [btn("✅ Approve Deposit", callback_data=f"adm_vdep_{deposit_id}", style="success"),
         btn("❌ Decline Deposit", callback_data=f"adm_rdep_{deposit_id}", style="danger")]
    ])


def settings_kb():
    return InlineKeyboardMarkup([
        [btn("✉️ Welcome Msg", callback_data="adm_setwelcome", style="primary"),
         btn("🏪 Shop Name", callback_data="adm_setshopname", style="primary")],
        [btn("💳 UPI ID", callback_data="adm_setupi", style="primary"),
         btn("🏷 Payee Name", callback_data="adm_setpayee", style="primary")],
        [btn("🎥 How-To Link", callback_data="adm_sethowto", style="primary"),
         btn("📂 File Link", callback_data="adm_setfiles", style="primary")],
        [btn("📩 Pay Proof Link", callback_data="adm_setpayproof", style="primary"),
         btn("🆘 Support User", callback_data="adm_setsupport", style="primary")],
        [btn("💱 USD Rate", callback_data="adm_setusdrate", style="primary"),
         btn("💱 BDT Rate", callback_data="adm_setbdtrate", style="primary")],
        [btn("🟡 Binance Pay ID", callback_data="adm_setbinpayid", style="primary")],
        [btn("🔑 Binance API Key", callback_data="adm_setbinkey", style="primary"),
         btn("🔒 Binance API Secret", callback_data="adm_setbinsecret", style="primary")],
        [btn("📱 bKash Number", callback_data="adm_setbkash", style="primary"),
         btn("📱 Nagad Number", callback_data="adm_setnagad", style="primary")],
        [btn("🧾 FamPay API Key", callback_data="adm_setfampaykey", style="primary")],
        [btn("🔗 Earnlinks API Token", callback_data="adm_setearnlinkskey", style="primary")],
        [btn("🎨 Customize Buttons", callback_data="adm_custombtns", style="primary"),
         btn("📝 Customize Text", callback_data="adm_customtexts", style="primary")],
        [btn("🏷 Customize Headers", callback_data="adm_customheaders", style="primary"),
         btn("🌈 Button Colors", callback_data="adm_custombtncolors", style="primary")],
        [btn("🎟️ Manage Coupons", callback_data="adm_coupons", style="primary")],
        [btn("📢 Broadcast", callback_data="adm_broadcast", style="primary")],
        [back_button("adm_back_main")],
    ])


def broadcast_target_kb():
    return InlineKeyboardMarkup([
        [btn("🌍 All Users", callback_data="adm_bc_all", style="primary"),
         btn("🔴 Resellers", callback_data="adm_bc_reseller", style="primary")],
        [btn("🎯 Specific User", callback_data="adm_bc_specific", style="primary")],
        [back_button("adm_settings")],
    ])


def coupons_list_kb(coupons):
    btns = [btn(f"🎟️ {c['code']} ({'ON' if c['active'] else 'OFF'})",
                callback_data=f"adm_coupon_{c['code']}", style="primary") for c in coupons]
    kb = rows(btns, 2)
    kb.append([btn("➕ Add Coupon", callback_data="adm_addcoupon", style="success")])
    kb.append([back_button("adm_settings")])
    return InlineKeyboardMarkup(kb)


def coupon_detail_kb(code):
    return InlineKeyboardMarkup([
        [btn("🗑 Delete Coupon", callback_data=f"adm_delcoupon_{code}", style="danger")],
        [back_button("adm_coupons")],
    ])


def coupon_type_kb():
    return InlineKeyboardMarkup([
        [btn("% Percent Off", callback_data="adm_coupontype_percent", style="primary"),
         btn("₹ Flat Amount Off", callback_data="adm_coupontype_flat", style="primary")],
    ])


def coupon_target_kb():
    return InlineKeyboardMarkup([
        [btn("🌍 All Users (except Reseller)", callback_data="adm_coupontarget_all_except_reseller", style="primary")],
        [btn("🔴 Reseller Only", callback_data="adm_coupontarget_reseller", style="primary")],
    ])


def coupon_duration_kb():
    return InlineKeyboardMarkup([
        [btn("6 Hours", callback_data="adm_coupondur_6", style="primary"),
         btn("12 Hours", callback_data="adm_coupondur_12", style="primary")],
        [btn("24 Hours", callback_data="adm_coupondur_24", style="primary")],
    ])


def coupon_limit_kb():
    return InlineKeyboardMarkup([
        [btn("1", callback_data="adm_couponlimit_1", style="primary"),
         btn("2", callback_data="adm_couponlimit_2", style="primary"),
         btn("5", callback_data="adm_couponlimit_5", style="primary")],
        [btn("♾️ Unlimited", callback_data="adm_couponlimit_unlimited", style="success")],
    ])


STYLE_GROUPS = [
    ("shop", "Shop Now", "success"),
    ("deposit", "Deposit", "primary"),
    ("profile", "Profile", "primary"),
    ("orders", "Order History", "success"),
    ("payproof", "Pay Proof", "success"),
    ("howto", "How To Use", "primary"),
    ("files", "Updated File", "primary"),
    ("support", "Contact Support", "danger"),
    ("referral", "Referral Button", "primary"),
    ("reseller_upgrade", "Upgrade to Reseller Button", "success"),
    ("category", "Category Buttons", "primary"),
    ("product", "Product Buttons", "primary"),
    ("duration", "Duration Buttons", "primary"),
    ("paybalance", "Pay with Balance", "success"),
    ("payqr", "Pay with QR", "primary"),
    ("trial", "Free Trial Button", "success"),
    ("trial_product", "Trial Product Buttons", "primary"),
]

STYLE_EMOJI = {"primary": "🔵", "success": "🟢", "danger": "🔴"}


def get_style(key, default="primary"):
    if get_theme() == "basic":
        return None  # no colour -> Telegram renders a plain grey button
    return db.get_setting(f"style_{key}", default)


def button_colors_kb():
    btns = [btn(f"{STYLE_EMOJI.get(get_style(key, default), '')} {label}",
                callback_data=f"adm_colorgrp_{key}", style="success")
            for key, label, default in STYLE_GROUPS]
    kb = rows(btns, 2)
    kb.append([back_button("adm_settings")])
    return InlineKeyboardMarkup(kb)


def color_choice_kb(key):
    return InlineKeyboardMarkup([
        [btn("🔵 Blue", callback_data=f"adm_setcolor_{key}_primary", style="primary")],
        [btn("🟢 Green", callback_data=f"adm_setcolor_{key}_success", style="success")],
        [btn("🔴 Red", callback_data=f"adm_setcolor_{key}_danger", style="danger")],
        [back_button("adm_custombtncolors")],
    ])


CUSTOMIZABLE_BUTTONS = [
    ("shop", "Shop Now"),
    ("deposit", "Deposit"),
    ("profile", "Profile"),
    ("orders", "Order History"),
    ("payproof", "Pay Proof"),
    ("howto", "How To Use"),
    ("files", "Updated File"),
    ("support", "Contact Support"),
    ("referral", "Referral Button (main menu)"),
    ("category", "Category Buttons"),
    ("product", "Product Buttons"),
    ("duration", "Duration Buttons"),
    ("paid_qr", "I Have Paid (UPI/QR)"),
    ("verify_payment", "Verify Payment (UPI gateway QR — live-checks payment status)"),
    ("paid_binance", "I Have Paid — Send Screenshot (Binance)"),
    ("cancel_order", "Cancel Order"),
    ("contact_proof", "Contact Admin with Payment Proof"),
    ("pay_upi", "Pay via UPI (applies to EVERY Pay via UPI button — orders, deposits, reseller upgrade)"),
    ("pay_binance", "Pay via Binance (applies to EVERY Pay via Binance button — orders, deposits, reseller upgrade)"),
    ("paybalance", "Pay with Balance (payment method)"),
    ("apply_coupon", "Apply Coupon Code"),
    ("back_plans", "Back to Plans"),
    ("back", "Back Button (used everywhere)"),
    ("contact_admin", "Contact Admin (stock-out message)"),
    ("reseller_upgrade", "Upgrade to Reseller (main menu button)"),
    ("trial", "Free Trial (main menu button)"),
    ("trial_product", "Trial Product Buttons"),
]


def _short_label(label, max_len=24):
    """Trims a long admin-facing label (which may carry placeholder docs like
    '(placeholders: {x}, {y})' or a trailing '— description') down to just the
    short, readable part, for compact display on a 2-column button."""
    short = re.split(r"\s*\(|\s+—", label)[0].strip()
    if len(short) > max_len:
        short = short[:max_len].rstrip() + "…"
    return short


def customize_buttons_kb():
    btns = []
    for key, label in CUSTOMIZABLE_BUTTONS:
        short_label = _short_label(label)
        current = db.get_setting(f"btn_label_{key}", label)
        short_current = current if len(current) <= 14 else current[:14].rstrip() + "…"
        btns.append(btn(f"{short_label}: {short_current}", callback_data=f"adm_editbtn_{key}", style="success"))
    kb = rows(btns, 2)
    kb.append([back_button("adm_settings")])
    return InlineKeyboardMarkup(kb)


# ============ CUSTOMIZABLE HEADERS ============
# These are the bold titles shown between the "━━━━" separator lines in the
# Shop Now flow (Shop -> Category -> Product -> Duration/Order Summary).
# Each entry is (key, admin-facing label, default text). The saved value is
# always rendered bold via HTML <b> tags at the call site.
#
# Every word is editable, including the shop/category/product name — those
# are inserted via {placeholder} tokens so the admin can keep them, move
# them, or remove them entirely. A mistyped/removed placeholder is left as
# literal text instead of crashing the bot.
CUSTOMIZABLE_HEADERS = [
    ("shop_header", "Shop Now page header", "🛍 SHOP"),
    ("category_header", "Category page header (placeholders: {shop_name}, {category_name})",
     "🤖 {shop_name} — 🤖 {category_name}\n✅"),
    ("product_header", "Product page header (placeholder: {product_name})", "📦 {product_name}"),
    ("duration_header", "Duration / Order Summary page header (placeholder: {product_name})", "📄 ORDER SUMMARY"),
    ("qr_order_message",
     "UPI/QR order payment message (placeholders: {order_id}, {customer}, {product_name}, {duration_label}, "
     "{amount_due}, {amount_usd}, {upi_id}, {balance_note})",
     "🛒 <b>ORDER RESERVED &amp; PAYMENT</b> 🛒\n\n"
     "🧾 <b>Order ID:</b> #{order_id}\n"
     "👤 <b>Customer:</b> {customer}\n"
     "📦 <b>Product:</b> {product_name} ({duration_label})\n"
     "💰 <b>Amount Due:</b> ₹{amount_due} (${amount_usd})\n"
     "🎯 <b>Merchant UPI ID:</b> <code>{upi_id}</code>\n\n"
     "📲 Scan the QR code below using GPay, PhonePe, Paytm, or BHIM to pay instantly.\n\n"
     "🚨 <b>IMPORTANT:</b> Once payment is sent, you MUST send the transaction screenshot "
     "image in this chat to link with Order ID #{order_id}. The admin will immediately "
     "review and deliver your product!\n\n"
     "💡 <i>Note: Your wallet balance is {balance_note} To buy without depositing, "
     "pay directly using the QR below!</i>"),
    ("binance_order_message",
     "Binance order payment message (placeholders: {amount_usd}, {pay_id}, {reference})",
     "━━━━━━━━━━━━━━━━━━━━\n"
     "🟡 <b>BINANCE PAY — ORDER PAYMENT</b> · <i>Auto-Verified</i>\n"
     "━━━━━━━━━━━━━━━━━━━━\n\n"
     "💰 <b>Amount:</b> ${amount_usd} USDT\n"
     "🆔 <b>Pay ID:</b> <code>{pay_id}</code>\n"
     "🔒 <b>Reference:</b> {reference}\n\n"
     "ℹ️ <b>Steps</b>\n"
     "1️⃣ Open Binance app → Pay → Send\n"
     "2️⃣ Enter Pay ID: <code>{pay_id}</code>\n"
     "3️⃣ Send exactly ${amount_usd} USDT\n"
     "4️⃣ Tap below and submit your Binance Order ID for instant verification\n\n"
     "ℹ️ <i>Your payment is verified automatically within seconds — no admin wait needed.</i>"),
    ("bkash_order_message",
     "bKash order payment message (placeholders: {amount}, {number}, {reference})",
     "━━━━━━━━━━━━━━━━━━━━\n"
     "📱 <b>bKash — ORDER PAYMENT</b> · <i>Manually Verified</i>\n"
     "━━━━━━━━━━━━━━━━━━━━\n\n"
     "💰 <b>Amount:</b> ৳{amount}\n"
     "🆔 <b>bKash Number:</b> <code>{number}</code>\n"
     "🔒 <b>Reference:</b> {reference}\n\n"
     "ℹ️ <b>Steps</b>\n"
     "1️⃣ Open bKash app → Send Money\n"
     "2️⃣ Enter Number: <code>{number}</code>\n"
     "3️⃣ Send exactly ৳{amount}\n"
     "4️⃣ Tap below and send a screenshot of your payment\n\n"
     "ℹ️ <i>The QR above is scan-to-copy only — it won't auto-fill the amount in "
     "the bKash app. An admin will verify your screenshot and deliver your order shortly.</i>"),
    ("nagad_order_message",
     "Nagad order payment message (placeholders: {amount}, {number}, {reference})",
     "━━━━━━━━━━━━━━━━━━━━\n"
     "📱 <b>Nagad — ORDER PAYMENT</b> · <i>Manually Verified</i>\n"
     "━━━━━━━━━━━━━━━━━━━━\n\n"
     "💰 <b>Amount:</b> ৳{amount}\n"
     "🆔 <b>Nagad Number:</b> <code>{number}</code>\n"
     "🔒 <b>Reference:</b> {reference}\n\n"
     "ℹ️ <b>Steps</b>\n"
     "1️⃣ Open Nagad app → Send Money\n"
     "2️⃣ Enter Number: <code>{number}</code>\n"
     "3️⃣ Send exactly ৳{amount}\n"
     "4️⃣ Tap below and send a screenshot of your payment\n\n"
     "ℹ️ <i>The QR above is scan-to-copy only — it won't auto-fill the amount in "
     "the Nagad app. An admin will verify your screenshot and deliver your order shortly.</i>"),
    ("bkash_deposit_message",
     "bKash deposit payment message (placeholders: {amount}, {number}, {reference})",
     "━━━━━━━━━━━━━━━━━━━━\n"
     "📱 <b>bKash DEPOSIT</b> · <i>Manually Verified</i>\n"
     "━━━━━━━━━━━━━━━━━━━━\n\n"
     "💰 <b>Amount:</b> ৳{amount}\n"
     "🆔 <b>bKash Number:</b> <code>{number}</code>\n"
     "🔒 <b>Reference:</b> {reference}\n\n"
     "ℹ️ <b>Steps</b>\n"
     "1️⃣ Open bKash app → Send Money\n"
     "2️⃣ Enter Number: <code>{number}</code>\n"
     "3️⃣ Send exactly ৳{amount}\n"
     "4️⃣ Tap below and send a screenshot of your payment\n\n"
     "ℹ️ <i>An admin will verify your screenshot and update your balance shortly.</i>"),
    ("nagad_deposit_message",
     "Nagad deposit payment message (placeholders: {amount}, {number}, {reference})",
     "━━━━━━━━━━━━━━━━━━━━\n"
     "📱 <b>Nagad DEPOSIT</b> · <i>Manually Verified</i>\n"
     "━━━━━━━━━━━━━━━━━━━━\n\n"
     "💰 <b>Amount:</b> ৳{amount}\n"
     "🆔 <b>Nagad Number:</b> <code>{number}</code>\n"
     "🔒 <b>Reference:</b> {reference}\n\n"
     "ℹ️ <b>Steps</b>\n"
     "1️⃣ Open Nagad app → Send Money\n"
     "2️⃣ Enter Number: <code>{number}</code>\n"
     "3️⃣ Send exactly ৳{amount}\n"
     "4️⃣ Tap below and send a screenshot of your payment\n\n"
     "ℹ️ <i>An admin will verify your screenshot and update your balance shortly.</i>"),
    ("binance_deposit_message",
     "Binance deposit payment message (placeholders: {amount_usd}, {pay_id}, {reference})",
     "━━━━━━━━━━━━━━━━━━━━\n"
     "🟡 <b>BINANCE PAY DEPOSIT</b> · <i>Auto-Verified</i>\n"
     "━━━━━━━━━━━━━━━━━━━━\n\n"
     "💰 <b>Amount:</b> ${amount_usd} USDT\n"
     "🆔 <b>Pay ID:</b> <code>{pay_id}</code>\n"
     "🔒 <b>Reference:</b> {reference}\n\n"
     "ℹ️ <b>Steps</b>\n"
     "1️⃣ Open Binance app → Pay → Send\n"
     "2️⃣ Enter Pay ID: <code>{pay_id}</code>\n"
     "3️⃣ Send exactly ${amount_usd} USDT\n"
     "4️⃣ Tap below and submit your Binance Order ID for instant verification\n\n"
     "ℹ️ <i>Your balance is updated automatically within seconds — no admin wait needed.</i>"),
    ("profile_message",
     "My Profile message (placeholders: {user_id}, {username}, {phone}, {role}, {balance_inr}, "
     "{balance_usd}, {total_deposit}, {orders_completed})",
     "━━━━━━━━━━━━━━━━━━━━\n"
     "👤 <b>MY PROFILE</b>\n"
     "━━━━━━━━━━━━━━━━━━━━\n\n"
     "🆔 <b>User ID:</b> <code>{user_id}</code>\n\n"
     "🔖 <b>Username:</b> {username}\n\n"
     "📱 <b>Phone Number:</b> {phone}\n\n"
     "🪪 <b>Role:</b> {role}\n\n"
     "💰 <b>Current Balance:</b> ₹{balance_inr} (${balance_usd})\n\n"
     "💵 <b>Total Deposited:</b> ₹{total_deposit}\n\n"
     "📦 <b>Orders Completed:</b> {orders_completed}"),
    ("payment_expired_message",
     "Payment expired message (placeholder: {reference})",
     "━━━━━━━━━━━━━━━━━━━━\n"
     "⏰ <b>PAYMENT EXPIRED</b>\n"
     "━━━━━━━━━━━━━━━━━━━━\n\n"
     "🔒 <b>Reference:</b> {reference}\n"
     "❌ Not paid within 5 minutes\n"
     "🔒 QR / payment details are no longer valid\n\n"
     "<i>Tap /start to begin a new order.</i>"),
    ("payment_not_received_message",
     "Shown when the customer taps 'Verify Payment' but the payment hasn't landed yet "
     "(deposit, order, and reseller-upgrade flows) (placeholder: {shop_name})",
     "🏪 <b>{shop_name}</b>\n\n"
     "❌ <b>PAYMENT NOT RECEIVED</b>\n\n"
     "We haven't received your payment yet. If you've already paid, please wait a "
     "few seconds and tap 'Verify Payment' again — it'll auto-confirm the instant it lands."),
    ("order_summary_body",
     "Order summary body — below the header (placeholders: {product_name}, {duration_label}, "
     "{unit_price_usd}, {coupon_line}, {final_total_usd})",
     "🔑 <b>Product:</b> {product_name}\n"
     "🔑 <b>Plan:</b> {duration_label}\n"
     "📄 <b>Quantity:</b> 1\n"
     "💲 <b>Unit price:</b> ${unit_price_usd} USD\n"
     "━━━━━━━━━━━━━━━━━━━━\n\n"
     "{coupon_line}"
     "💲 <b>Final Total:</b> ${final_total_usd} USD\n\n"
     "👇 <b>Choose your payment method</b>\n"
     "<i>Pick any option below — each button shows the exact amount in that currency. "
     "If you have wallet balance, you can pay instantly with it.</i>"),
    ("verification_required_message",
     "Phone verification required message (placeholders: {shop_name}, {name})",
     "🏪 <b>{shop_name}</b>\n\n"
     "🎉 Welcome, {name}!\n\n"
     "━━━━━━━━━━━━━━━━━━━━\n"
     "🔒 <b>VERIFICATION REQUIRED</b>\n"
     "━━━━━━━━━━━━━━━━━━━━\n\n"
     "To start shopping, please verify your phone number.\n\n"
     "✅ <b>Why we need this:</b>\n"
     "• Secure your purchases\n"
     "• Deliver keys to you\n"
     "• Protect your account\n\n"
     "<i>Tap the button below to share your contact.</i>"),
    ("phone_verified_message", "Message shown right after phone verification",
     "✅ Thank you! Your contact has been verified."),
    ("screenshot_request_message", "Payment screenshot request message (order & deposit flows)",
     "📸 Please send your payment screenshot for verification."),
    ("screenshot_received_message", "Screenshot received / pending review message (order & deposit flows)",
     "✅ Screenshot received. The admin will verify it shortly.\n\n"
     "💡 If you're sure you've already paid, tap below to contact the admin directly with your payment proof."),
    ("key_delivered_message",
     "Key delivered after payment is verified — used for Binance auto-verify, UPI auto-verify, admin QR "
     "approval, AND Pay-with-Balance purchases (placeholders: {order_id}, {product_name}, {duration_label}, "
     "{price}, {key}, {payment_mode})",
     "🎉 <b>YOUR ORDER HAS BEEN CONFIRMED!</b> 🎉\n\n"
     "🧾 <b>Order ID:</b> #{order_id}\n"
     "📦 <b>Product:</b> {product_name}\n"
     "⏳ <b>Duration:</b> {duration_label}\n"
     "💰 <b>Price:</b> ₹{price}\n"
     "💳 <b>Payment Mode:</b> {payment_mode}\n\n"
     "🔑 <b>Your Digital Item/License Code:</b>\nKey: <code>{key}</code>\n\n"
     "✨ Thank you for shopping with us! Have a great day."),
    ("deposit_confirmed_message",
     "Deposit auto-confirmed message — shown to the customer the moment their UPI deposit is verified "
     "(placeholders: {amount}, {previous_balance}, {new_balance})",
     "🎉 <b>CONGRATULATIONS! YOUR DEPOSIT HAS BEEN CONFIRMED.</b> 🎉\n\n"
     "💰 <b>Amount Deposited:</b> ₹{amount}\n"
     "📊 <b>Previous Balance:</b> ₹{previous_balance}\n"
     "✨ <b>Updated Balance:</b> ₹{new_balance}\n\n"
     "🙏 Thank you for topping up!"),
    ("stock_out_message", "Payment verified but stock ran out message",
     "✅ Payment verified, but stock has run out. Please contact the admin."),
    ("insufficient_balance_message",
     "Insufficient balance message (placeholders: {balance}, {required})",
     "⚠️ Insufficient balance. Your balance: ₹{balance}, Required: ₹{required}\nPlease deposit first."),
    ("binance_order_id_request_message",
     "Ask user for their Binance Order ID (order & deposit flows)",
     "🔢 <b>Send your Binance Order ID</b> to verify this payment instantly.\n\n"
     "<i>Find it in Binance app → Pay → this transaction → \"Order ID\" (or \"Transaction ID\").</i>"),
    ("out_of_stock_message", "Out of stock message (before payment is taken)",
     "⚠️ Out of stock. Please contact the admin."),
    ("order_history_header", "Order History page header/title",
     "📜 <b>ORDER HISTORY</b>\n<i>Your last 5 orders</i>"),
    ("order_history_empty_message", "Order History — message shown when user has NO orders yet",
     "📜 You don't have any order history yet."),
    ("order_history_entry",
     "Order History — template for EACH order in the list (placeholders: {reference}, {product_name}, "
     "{duration_label}, {price_inr}, {price_usd}, {method}, {date}, {time}, {license_key})",
     "✅ <b>{reference}</b>\n"
     "🔑 {product_name} - <i>{duration_label}</i>\n"
     "💰 ₹{price_inr} (${price_usd}) · {method}\n"
     "🕐 {date} · {time} IST\n"
     "🔑 <code>{license_key}</code>"),
    ("deposit_history_header", "Transaction History page header/title",
     "📄 <b>TRANSACTION HISTORY</b> 📄\n<i>Your last 5 successful deposits</i>"),
    ("deposit_history_empty_message", "Transaction History — message shown when user has NO successful deposits yet",
     "📄 You don't have any successful deposits yet."),
    ("deposit_history_entry",
     "Transaction History — template for EACH deposit in the list (placeholders: {reference}, {amount}, "
     "{balance_before}, {balance_after}, {method}, {date}, {time})",
     "✅ <b>{reference}</b>\n"
     "💰 <b>Amount Deposited:</b> ₹{amount}\n"
     "📊 <b>Balance Before:</b> ₹{balance_before}\n"
     "✨ <b>Balance After:</b> ₹{balance_after}\n"
     "💳 <b>Mode of Payment:</b> {method}\n"
     "🕐 {date} · {time} IST"),
    ("reseller_upgrade_congrats_message",
     "Message sent to user right after they're upgraded to Reseller (placeholder: {credit_line} — "
     "leave this placeholder in; it auto-fills with the wallet-credit line when applicable, or stays blank)",
     "🎉 <b>Congratulations! You are now a Reseller!</b> 🎉\n\n"
     "🏷️ Lowest prices are now active on your account.\n"
     "🚀 High priority support unlocked.\n"
     "👑 You're officially a member of the Infinity Family.\n"
     "🔁 Access to all product reset bots.{credit_line}"),
    ("referral_page_message",
     "Referral page — shown when user taps the Referral button (placeholders: {referral_link}, "
     "{total_referred}, {total_bonus_earned}, {commission_percent})",
     "🎁 <b>Refer &amp; Earn</b>\n\n"
     "Invite friends using your link. When someone you refer makes a successful deposit or "
     "product purchase, you instantly earn <b>{commission_percent}%</b> of what they paid — "
     "credited straight to your wallet balance!\n\n"
     "🔗 <b>Your Referral Link:</b>\n{referral_link}\n\n"
     "📊 <b>Your Stats:</b>\n"
     "👥 Total Referred: <b>{total_referred}</b>\n"
     "💎 Total Bonuses Earned: <b>₹{total_bonus_earned}</b>\n\n"
     "📜 <b>Rules:</b>\n"
     "• Bonus = {commission_percent}% of every deposit/purchase your referral makes\n"
     "• Only counts for genuinely NEW users who join via your link\n"
     "• ⏳ You keep earning only while your referral stays a regular User — once they "
     "upgrade to Reseller, no further commission applies from them"),
    ("deposit_add_balance_page_message",
     "Add Balance page — shown when user taps Deposit (placeholders: {current_balance}, {min_amount}, "
     "{max_amount}, {deposit_count}, {plural})",
     "━━━━━━━━━━━━━━━━━━━━\n"
     "💳 <b>Add Balance</b>\n"
     "━━━━━━━━━━━━━━━━━━━━\n\n"
     "💰 Current balance: ${current_balance} USD\n"
     "📥 Min: ${min_amount} USD · 📤 Max: ${max_amount} USD\n\n"
     "<i>Pick an amount below. Local-currency total appears on the gateway button.</i>\n\n"
     "📄 You have {deposit_count} successful deposit{plural} in your history."),
    ("deposit_method_select_message",
     "Deposit amount confirmed — payment method selection prompt (placeholder: {amount})",
     "💵 <b>Deposit amount:</b> ${amount}\n\n👇 Choose a payment method:"),
    ("payment_declined_message",
     "Payment declined message — used for BOTH order declines and deposit declines (set once, "
     "applies everywhere). Placeholders: {id_label} ('Order ID' or 'Deposit ID'), {id_value}, "
     "{details_line} (product info — auto-blank for deposits), {amount}, {reason}",
     "❌ <b>PAYMENT DECLINED</b> ❌\n\n"
     "🧾 <b>{id_label}:</b> #{id_value}\n"
     "{details_line}"
     "💰 <b>Amount:</b> ₹{amount}\n\n"
     "⚠️ <b>Reason for Decline:</b>\n{reason}\n\n"
     "Please contact support if you believe this is a mistake or re-submit proof with a valid "
     "payment transaction screenshot."),
    ("method_label_upi", "Payment method label — UPI (shown in Order History)", "📷 UPI"),
    ("method_label_binance", "Payment method label — Binance (shown in Order History)", "🟡 Binance"),
    ("method_label_bkash", "Payment method label — bKash (shown in Order History)", "📱 bKash"),
    ("method_label_nagad", "Payment method label — Nagad (shown in Order History)", "📱 Nagad"),
    ("method_label_balance", "Payment method label — Wallet Balance (shown in Order History)", "💳 Wallet"),
    ("reseller_info_message",
     "Reseller upgrade page — full text (everything from 'UPGRADE TO RESELLER' down to 'Choose a "
     "payment method below', all in one editable block; placeholder: {fee})",
     "━━━━━━━━━━━━━━━━━━━━\n"
     "👑 <b>UPGRADE TO RESELLER</b> 👑\n"
     "━━━━━━━━━━━━━━━━━━━━\n\n"
     "✨ <b>What you get as a Reseller:</b>\n\n"
     "🔻 Lowest prices on every product\n"
     "🚀 High priority support\n"
     "👑 Member of the Infinity Family\n"
     "🔁 Access to all product reset bots\n\n"
     "⚠️ <b>DISCLAIMER: The Reseller upgrade fee is ₹{fee}, set by the admin.</b>\n\n"
     "👇 Choose a payment method below:"),
    ("upi_gateway_deposit_message",
     "UPI gateway deposit — QR payment caption (placeholders: {deposit_id}, {amount}, {usd_label}, {upi_id})",
     "💳 <b>DEPOSIT &amp; PAYMENT</b> 💳\n\n"
     "🔐 <b>Deposit ID:</b> {deposit_id}\n"
     "💰 <b>Amount:</b> ₹{amount} ({usd_label})\n"
     "🎯 <b>Merchant UPI ID:</b> <code>{upi_id}</code>\n\n"
     "📲 Scan the QR code below using GPay, PhonePe, Paytm, or BHIM to pay instantly.\n\n"
     "⚡ <b>Auto-Verify:</b> No screenshot needed! Your balance updates automatically the "
     "moment payment is confirmed.\n\n"
     "⏳ <i>This QR expires in 5 minutes.</i>"),
    ("reseller_qr_message",
     "Reseller upgrade — UPI QR payment caption (placeholder: {amount})",
     "📷 Scan &amp; Pay ₹{amount} (Reseller Upgrade Fee)\n\n"
     "This QR expires in 5 minutes."),
    ("reseller_binance_message",
     "Reseller upgrade — Binance payment message (placeholders: {amount_usd}, {pay_id}, {reference})",
     "━━━━━━━━━━━━━━━━━━━━\n"
     "🟡 <b>BINANCE PAY — RESELLER UPGRADE</b> · <i>Auto-Verified</i>\n"
     "━━━━━━━━━━━━━━━━━━━━\n\n"
     "💰 <b>Amount:</b> ${amount_usd} USDT\n"
     "🆔 <b>Pay ID:</b> <code>{pay_id}</code>\n"
     "🔒 <b>Reference:</b> {reference}\n\n"
     "ℹ️ <b>Steps</b>\n"
     "1️⃣ Open Binance app → Pay → Send\n"
     "2️⃣ Enter Pay ID: <code>{pay_id}</code>\n"
     "3️⃣ Send exactly ${amount_usd} USDT\n"
     "4️⃣ Tap below and submit your Binance Order ID for instant verification\n\n"
     "ℹ️ <i>Your account is upgraded automatically within seconds — no admin wait needed.</i>"),
    ("binance_verifying_message", "Shown right after the user submits their Binance Order ID, while it's being checked",
     "⏳ Checking your payment on Binance... this takes a few seconds."),
    ("binance_id_duplicate_message",
     "Shown when the submitted Binance Order ID was already used on another order/deposit",
     "⚠️ This Binance Order ID has already been used for another payment.\n\n"
     "Please double-check and send the correct Order ID from THIS payment."),
    ("binance_verify_pending_message",
     "Shown when auto-verify couldn't instantly confirm the payment (sent for admin review as a fallback)",
     "🔎 We couldn't auto-confirm this instantly. Your Order ID has been saved and sent for a quick admin "
     "review — you'll be notified the moment it's confirmed.\n\n"
     "💡 If you're sure you've already paid the correct amount, please double check the Order ID you sent."),
]

class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def get_header(_header_key, **placeholders):
    """Return the admin's custom text for header `_header_key`, or its default,
    with any {placeholder} tokens filled in from `placeholders`. The param is
    named `_header_key` (not `key`) so callers can freely pass key=... as a
    placeholder (e.g. license keys) without an argument-name collision."""
    default = next((d for k, _, d in CUSTOMIZABLE_HEADERS if k == _header_key), _header_key)
    template = db.get_setting(f"header_{_header_key}", default)
    return template.format_map(_SafeDict(**placeholders))


def customize_headers_kb():
    btns = []
    for key, label, default in CUSTOMIZABLE_HEADERS:
        short_label = _short_label(label)
        current = db.get_setting(f"header_{key}", default).replace("\n", " ")
        plain = _HTML_TAG_RE.sub("", current).strip()  # preview only — real value keeps its HTML/emoji tags
        preview = plain if len(plain) <= 16 else plain[:16].rstrip() + "…"
        btns.append(btn(f"{short_label}: {preview}", callback_data=f"adm_editheader_{key}", style="success"))
    kb = rows(btns, 2)
    kb.append([back_button("adm_settings")])
    return InlineKeyboardMarkup(kb)


CUSTOMIZABLE_TEXTS = [
    ("shop_subtitle", "Shop Now subtitle"),
    ("category_prompt", "Category page prompt"),
    ("product_prompt", "Product page prompt"),
    ("duration_prompt", "Duration/payment prompt"),
    ("payment_unverified_msg", "Payment not auto-verified message"),
]


def customize_texts_kb():
    kb = [[btn(label, callback_data=f"adm_edittext_{key}", style="primary")] for key, label in CUSTOMIZABLE_TEXTS]
    kb.append([back_button("adm_settings")])
    return InlineKeyboardMarkup(kb)


# ================= USER =================

def user_main_menu(role=None):
    kb = [
        [btn(db.get_setting("btn_label_shop", "🛍 Shop Now"), callback_data="u_shop",
             style=get_style("shop", "success"), icon=get_icon("shop"))],
    ]
    if db.is_trial_button_enabled():
        kb.append([btn(db.get_setting("btn_label_trial", "🎁 Free Trial"), callback_data="u_trial",
                        style=get_style("trial", "success"), icon=get_icon("trial"))])
    kb += [
        [btn(db.get_setting("btn_label_deposit", "💵 Deposit"), callback_data="u_deposit",
             style=get_style("deposit", "primary"), icon=get_icon("deposit")),
         btn(db.get_setting("btn_label_profile", "👤 Profile"), callback_data="u_profile",
             style=get_style("profile", "primary"), icon=get_icon("profile"))],
        [btn(db.get_setting("btn_label_orders", "📜 Order History"), callback_data="u_orders",
             style=get_style("orders", "success"), icon=get_icon("orders")),
         btn(db.get_setting("btn_label_payproof", "📩 Pay Proof"),
             url=db.get_setting("pay_proof_group_link", "https://t.me/"),
             style=get_style("payproof", "success"), icon=get_icon("payproof"))],
        [btn(db.get_setting("btn_label_howto", "📘 How To Use"),
             url=db.get_setting("how_to_use_link", "https://t.me/"),
             style=get_style("howto", "primary"), icon=get_icon("howto")),
         btn(db.get_setting("btn_label_files", "📂 Updated File"),
             url=db.get_setting("updated_file_group_link", "https://t.me/"),
             style=get_style("files", "primary"), icon=get_icon("files"))],
        [btn(db.get_setting("btn_label_support", "🆘 Contact Support"),
             url=f"https://t.me/{db.get_setting('support_username', '')}",
             style=get_style("support", "danger"), icon=get_icon("support")),
         btn(db.get_setting("btn_label_referral", "🔗 Referral"), callback_data="u_referral",
             style=get_style("referral", "primary"), icon=get_icon("referral"))],
    ]
    if role != "reseller" and db.is_reseller_button_enabled():
        kb.append([btn(db.get_setting("btn_label_reseller_upgrade", "🟢 Upgrade to Reseller"),
                        callback_data="u_reseller_info", style=get_style("reseller_upgrade", "success"),
                        icon=get_icon("reseller_upgrade"))])
    return InlineKeyboardMarkup(kb)


def reseller_info_kb():
    return InlineKeyboardMarkup([
        [btn(db.get_setting("btn_label_pay_upi", "📷 Pay via UPI"), callback_data="u_reseller_pay_upi",
             style="success", icon=get_icon("pay_upi"))],
        [btn(db.get_setting("btn_label_pay_binance", "🟡 Pay via Binance"), callback_data="u_reseller_pay_binance",
             style="primary", icon=get_icon("pay_binance"))],
        [back_button("u_back_main")],
    ])


def user_categories_kb(categories):
    btns = [btn(c['name'], callback_data=f"u_cat_{c['id']}",
                style=get_style("category", "primary"),
                icon=c.get('icon') or get_icon("category")) for c in categories]
    kb = rows(btns, 1)
    kb.append([back_button("u_back_main")])
    return InlineKeyboardMarkup(kb)


def user_trial_products_kb(trial_products):
    btns = [btn(tp['name'], callback_data=f"u_trialget_{tp['id']}",
                style=get_style("trial_product", "primary"),
                icon=tp.get('icon') or get_icon("trial_product")) for tp in trial_products]
    kb = rows(btns, 1)
    kb.append([back_button("u_back_main")])
    return InlineKeyboardMarkup(kb)


def user_products_kb(products, cat_id):
    btns = [btn(p['name'], callback_data=f"u_prod_{p['id']}",
                style=get_style("product", "primary"),
                icon=p.get('icon') or get_icon("product")) for p in products]
    kb = rows(btns, 1)
    kb.append([back_button("u_shop")])
    return InlineKeyboardMarkup(kb)


def user_durations_kb(duration_price_pairs, product_id, cat_id):
    btns = [btn(f"{label} - ₹{price} (${db.inr_to_usd(price)})", callback_data=f"u_dur_{did}",
                style=get_style("duration", "primary"),
                icon=icon or get_icon("duration"))
            for did, label, price, icon in duration_price_pairs]
    kb = rows(btns, 1)
    kb.append([back_button(f"u_cat_{cat_id}")])
    return InlineKeyboardMarkup(kb)


def payment_method_kb(duration_id, product_id, price_inr):
    usd = db.inr_to_usd(price_inr)
    bdt = db.inr_to_bdt(price_inr)
    payqr_label = db.get_setting("btn_label_pay_upi", "📷 Pay via UPI")
    paybin_label = db.get_setting("btn_label_pay_binance", "🟡 Pay via Binance")
    paybkash_label = db.get_setting("btn_label_pay_bkash", "📱 Pay via bKash")
    paynagad_label = db.get_setting("btn_label_pay_nagad", "📱 Pay via Nagad")
    paybal_label = db.get_setting("btn_label_paybalance", "💰 Pay with Balance")
    coupon_label = db.get_setting("btn_label_apply_coupon", "🎟️ Apply Coupon Code")
    back_label = db.get_setting("btn_label_back_plans", "↩️ Back to Plans")
    return InlineKeyboardMarkup([
        [btn(f"{payqr_label} — ₹{price_inr}", callback_data=f"u_payqr_{duration_id}",
             style=get_style("payqr", "success"), icon=get_icon("pay_upi"))],
        [btn(f"{paybin_label} — ${usd} USDT", callback_data=f"u_paybin_{duration_id}",
             style=get_style("paybinance", "success"), icon=get_icon("pay_binance"))],
        [btn(f"{paybkash_label} — ৳{bdt}", callback_data=f"u_paybkash_{duration_id}", style="success")],
        [btn(f"{paynagad_label} — ৳{bdt}", callback_data=f"u_paynagad_{duration_id}", style="success")],
        [btn(f"{paybal_label} — ₹{price_inr}", callback_data=f"u_paybal_{duration_id}",
             style=get_style("paybalance", "success"), icon=get_icon("paybalance"))],
        [btn(coupon_label, callback_data="u_apply_coupon", style="primary", icon=get_icon("apply_coupon"))],
        [btn(back_label, callback_data=f"u_prod_{product_id}", style="danger", icon=get_icon("back_plans"))],
    ])


def order_qr_kb(order_id):
    return InlineKeyboardMarkup([
        [btn(db.get_setting("btn_label_paid_qr", "✅ I Have Paid"), callback_data=f"u_paid_order_{order_id}",
             style="success", icon=get_icon("paid_qr"))],
        [btn(db.get_setting("btn_label_cancel_order", "❌ Cancel Order"), callback_data=f"u_reject_order_{order_id}",
             style="danger", icon=get_icon("cancel_order"))],
        [back_button("u_back_main")],
    ])


def order_qr_gateway_kb(order_id):
    """Used for FamPay gateway-backed product orders — auto-verified in the background,
    with a manual 'Verify Payment' button that live-checks the gateway on demand."""
    return InlineKeyboardMarkup([
        [btn(db.get_setting("btn_label_verify_payment", "🔍 Verify Payment"),
             callback_data=f"u_order_check_{order_id}", style="success", icon=get_icon("verify_payment"))],
        [back_button("u_back_main")],
    ])


def order_binance_kb(order_id):
    return InlineKeyboardMarkup([
        [btn(db.get_setting("btn_label_paid_binance", "📋 I Paid — Submit Order ID"),
             callback_data=f"u_paid_bin_order_{order_id}", style="success", icon=get_icon("paid_binance"))],
        [btn(db.get_setting("btn_label_cancel_order", "❌ Cancel Order"), callback_data=f"u_reject_order_{order_id}",
             style="danger", icon=get_icon("cancel_order"))],
        [back_button("u_back_main")],
    ])


def deposit_presets_kb(history_count=0, is_admin=False):
    amounts = [1, 2, 5, 10, 15, 20, 50, 100]
    btns = [btn(f"${a} USD", callback_data=f"u_dep_preset_{a}", style="success") for a in amounts]
    rows_ = rows(btns, 2)
    rows_.append([btn("⏱ Custom Amount (USD)", callback_data="u_dep_custom", style="success")])
    if is_admin:
        rows_.append([btn("🧪 Admin Test ₹1 (UPI auto-verify)", callback_data="u_dep_admin_test1", style="primary")])
    rows_.append([btn(f"📋 Transaction History ({history_count})", callback_data="u_deposit_history", style="primary")])
    rows_.append([btn("↩ Back to Home", callback_data="u_back_main", style="danger")])
    return InlineKeyboardMarkup(rows_)


def deposit_amount_kb(current):
    rows_ = []
    nums = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "⌫", "0", "✅"]
    line = []
    for i, n in enumerate(nums, 1):
        style = "success" if n == "✅" else ("danger" if n == "⌫" else "primary")
        line.append(btn(n, callback_data=f"u_dep_key_{n}", style=style))
        if i % 3 == 0:
            rows_.append(line)
            line = []
    rows_.append([back_button("u_deposit")])
    return InlineKeyboardMarkup(rows_)


def deposit_method_kb(usd_amount):
    return InlineKeyboardMarkup([
        [btn(db.get_setting("btn_label_pay_binance", "🟡 Pay via Binance"),
             callback_data=f"u_dep_method_binance_{usd_amount}", style="primary", icon=get_icon("pay_binance"))],
        [btn(db.get_setting("btn_label_pay_upi", "📷 Pay via UPI"),
             callback_data=f"u_dep_method_upi_{usd_amount}", style="success", icon=get_icon("pay_upi"))],
        [btn(db.get_setting("btn_label_pay_bkash", "📱 Pay via bKash"),
             callback_data=f"u_dep_method_bkash_{usd_amount}", style="success")],
        [btn(db.get_setting("btn_label_pay_nagad", "📱 Pay via Nagad"),
             callback_data=f"u_dep_method_nagad_{usd_amount}", style="success")],
        [back_button("u_deposit")],
    ])


def deposit_qr_kb(deposit_id):
    return InlineKeyboardMarkup([
        [btn(db.get_setting("btn_label_paid_qr", "✅ I Have Paid"), callback_data=f"u_paid_dep_{deposit_id}",
             style="success", icon=get_icon("paid_qr"))],
        [btn("❌ Reject Deposit", callback_data=f"u_reject_dep_{deposit_id}", style="danger")],
        [back_button("u_back_main")],
    ])


def deposit_gateway_qr_kb(deposit_id):
    """Used for FamPay gateway-backed UPI deposits (and reseller-upgrade fee payments) —
    auto-verified in the background, with a manual 'Verify Payment' button that
    live-checks the gateway on demand."""
    return InlineKeyboardMarkup([
        [btn(db.get_setting("btn_label_verify_payment", "🔍 Verify Payment"),
             callback_data=f"u_dep_check_{deposit_id}", style="success", icon=get_icon("verify_payment"))],
        [back_button("u_back_main")],
    ])


def deposit_binance_kb(deposit_id):
    return InlineKeyboardMarkup([
        [btn(db.get_setting("btn_label_paid_binance", "📋 I Paid — Submit Order ID"),
             callback_data=f"u_paid_bin_dep_{deposit_id}", style="success", icon=get_icon("paid_binance"))],
        [btn("❌ Cancel Deposit", callback_data=f"u_reject_dep_{deposit_id}", style="danger")],
        [back_button("u_back_main")],
    ])


def back_main_kb():
    return InlineKeyboardMarkup([[back_button("u_back_main")]])


def review_pending_kb():
    support_username = db.get_setting("support_username", "")
    return InlineKeyboardMarkup([
        [btn(db.get_setting("btn_label_contact_proof", "🆘 Contact Admin with Payment Proof"),
             url=f"https://t.me/{support_username}", style="primary", icon=get_icon("contact_proof"))],
        [back_button("u_back_main")],
    ])


def stock_out_kb():
    support_username = db.get_setting("support_username", "")
    return InlineKeyboardMarkup([
        [btn(db.get_setting("btn_label_contact_admin", "🆘 Contact Admin"),
             url=f"https://t.me/{support_username}", style="primary", icon=get_icon("contact_admin"))],
        [back_button("u_back_main")],
    ])


def declined_kb():
    support_username = db.get_setting("support_username", "")
    return InlineKeyboardMarkup([
        [btn(db.get_setting("btn_label_contact_admin", "🆘 Contact Admin"),
             url=f"https://t.me/{support_username}", style="primary", icon=get_icon("contact_admin"))],
        [back_button("u_back_main")],
    ])


def contact_request_kb():
    from telegram import ReplyKeyboardMarkup, KeyboardButton
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Share Phone Number", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )


def daily_result_kb():
    return InlineKeyboardMarkup([[btn("🎲 Back To Menu", callback_data="u_back_main", style="danger")]])
