import asyncio
import datetime
import json
import logging
import secrets
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes

import database as db
import keyboards as kb
from config import SUPPORT_ADMIN_USERNAME, ADMIN_IDS
from qr_utils import generate_upi_qr, generate_text_qr
from text_style import stylize
import fampay_utils as fp
import earnlinks_utils as el
import binance_utils as bu
import common_handlers as ch

logger = logging.getLogger("user_handlers")


def fp_shorten_or_fallback(destination_url):
    """Shortens destination_url via Earnlinks; if the token isn't set or the API
    call fails, falls back to the direct link so a trial claim never just breaks."""
    short = el.shorten_url(destination_url)
    if short:
        return short
    logger.warning("Earnlinks shorten failed/unconfigured, falling back to direct link: %s", destination_url)
    return destination_url


def build_welcome_text(first_name):
    shop_name = stylize(db.get_setting("shop_name", "Satyam's Shop"))
    name = stylize(first_name or "there")
    template = db.get_setting("welcome_message", "Welcome to {shop_name}, {name}! 🎉")
    return template.format(shop_name=shop_name, name=name)


async def _send_payment_not_received(context, chat_id):
    """Sends the shop-branded 'payment not received' message in chat. Used by every
    Verify Payment flow (deposit, order, reseller upgrade) whenever the gateway
    hasn't confirmed the payment yet."""
    shop_name = stylize(db.get_setting("shop_name", "Satyam's Shop"))
    try:
        await context.bot.send_message(
            chat_id,
            kb.get_header("payment_not_received_message", shop_name=shop_name),
            parse_mode="HTML")
    except Exception:
        pass


def _binance_card(message_key, reference, amount_usd):
    pay_id = db.get_setting("binance_pay_id", "") or "(not set)"
    return kb.get_header(message_key, amount_usd=amount_usd, pay_id=pay_id, reference=reference)


async def _send_upi_gateway_deposit(q, context, chat_id, tid, inr_amount, usd_label, purpose="deposit"):
    """Creates a FamPay order for this deposit and shows the QR with auto-verify running
    in the background. Falls back to the old static UPI-ID QR (manual review) if the
    gateway call fails for any reason, so deposits never get completely stuck."""
    deposit_id = db.create_deposit(tid, inr_amount, method="upi", purpose=purpose)
    order = fp.create_order(inr_amount)
    if order:
        db.set_deposit_gateway_order(deposit_id, order["order_id"], order.get("expires_at"))
        if purpose == "reseller_upgrade":
            caption = kb.get_header("reseller_qr_message", amount=f"{inr_amount:.0f}")
        else:
            upi_id = db.get_setting("upi_id", "") or "(not set)"
            caption = kb.get_header("upi_gateway_deposit_message", deposit_id=deposit_id,
                                     amount=f"{inr_amount:.0f}", usd_label=usd_label, upi_id=upi_id)
        markup = kb.deposit_gateway_qr_kb(deposit_id)
        if order.get("qr_url"):
            sent = await context.bot.send_photo(chat_id, order["qr_url"], caption=caption,
                                                 parse_mode="HTML", reply_markup=markup)
        else:
            sent = await context.bot.send_message(chat_id, caption, parse_mode="HTML", reply_markup=markup)
        try:
            await q.delete_message()
        except Exception:
            pass
        return sent

    # ---- Fallback: gateway unreachable / API key missing -> old manual flow ----
    upi_id = db.get_setting("upi_id", "")
    payee_name = db.get_setting("payee_name", "Shop")
    caption = (f"📷 Scan &amp; Pay ₹{inr_amount} ({usd_label})\n\n"
               "Once paid, tap 'I Have Paid' below.")
    if upi_id:
        qr_img = generate_upi_qr(upi_id, payee_name, inr_amount, f"Deposit{deposit_id}")
        markup = kb.deposit_qr_kb(deposit_id)
        sent = await context.bot.send_photo(chat_id, qr_img, caption=caption, parse_mode="HTML",
                                             reply_markup=markup)
        try:
            await q.delete_message()
        except Exception:
            pass
        return sent
    note = caption + "\n\n(The admin hasn't set a UPI ID yet.)"
    markup = kb.deposit_qr_kb(deposit_id)
    return await q.edit_message_text(note, parse_mode="HTML", reply_markup=markup)


def _effective_price(duration_id, tid, role, context):
    base_price = db.get_price_for_user(duration_id, tid, role)
    code = context.user_data.get("coupon_code")
    if code:
        new_price, ok = db.apply_coupon_discount(base_price, code)
        if ok:
            return new_price
        context.user_data.pop("coupon_code", None)
    return base_price


def _build_order_summary(duration_id, tid, role, context):
    d = db.get_duration(duration_id)
    p = db.get_product(d["product_id"])
    base_price = db.get_price_for_user(duration_id, tid, role)
    final_price = _effective_price(duration_id, tid, role, context)
    code = context.user_data.get("coupon_code")
    coupon_line = f"🎟️ <b>Coupon:</b> {code} applied\n" if code else ""
    usd_unit = db.inr_to_usd(base_price)
    usd_final = db.inr_to_usd(final_price)
    text = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>{kb.get_header('duration_header', product_name=p['name'])}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        + kb.get_header(
            "order_summary_body",
            product_name=p['name'],
            duration_label=d['label'],
            unit_price_usd=usd_unit,
            coupon_line=coupon_line,
            final_total_usd=usd_final,
        )
    )
    keyboard = kb.payment_method_kb(duration_id, d["product_id"], final_price)
    return text, keyboard


async def deliver_order_key(context, order_id, o=None, method="upi"):
    """Pops a key for a completed order and messages the customer. Shared by the
    UPI-gateway and Binance auto-verify flows so it matches exactly what admin
    manual-verify does. `method` picks the "Payment Mode" label shown to the
    customer/admin ('upi' or 'binance').
    Returns True if a key was delivered, False if out of stock (still marks completed)."""
    o = o or db.get_order(order_id)
    duration = db.get_duration(o["duration_id"])
    product = db.get_product(o["product_id"])
    key = db.pop_key(o["duration_id"], o["telegram_id"])
    db.set_order_status(order_id, "completed")
    db.credit_referral_commission(o["telegram_id"], o["price"], f"product order #{order_id}")
    method_label = kb.get_header(f"method_label_{method}")
    if key:
        db.set_order_delivered_key(order_id, key)
        if o.get("coupon_code"):
            db.record_coupon_usage(o["coupon_code"], o["telegram_id"])
        try:
            await context.bot.send_message(
                o["telegram_id"],
                kb.get_header("key_delivered_message", order_id=order_id, product_name=product['name'],
                              duration_label=duration['label'], price=f"{o['price']:.2f}", key=key,
                              payment_mode=f"{method_label} · Auto-Verified"),
                parse_mode="HTML")
        except Exception:
            pass
        await ch.notify_admins_order_completed(context, order_id, f"{method_label} (Auto-Verified)", key)
        return True
    try:
        await context.bot.send_message(o["telegram_id"], kb.get_header("stock_out_message"), parse_mode="HTML",
                                        reply_markup=kb.stock_out_kb())
    except Exception:
        pass
    await ch.notify_admins_order_completed(context, order_id, f"{method_label} (Auto-Verified)", None)
    return False


async def handle_binance_order_id_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the Binance Order ID the user sends after tapping 'I Paid — Submit Order ID'
    on an order, deposit, or reseller-upgrade Binance payment card. Verifies the payment
    automatically against the shop's Binance account transaction history (via
    binance_utils.find_matching_payment, using the regular-account API key/secret set in
    Admin > Settings). If auto-verify can't confirm it instantly (API hiccup, payment not
    reflected yet, etc.), it falls back to the existing admin-review queue so nothing gets
    stuck — the submitted Binance Order ID is shown to the admin either way."""
    state = context.user_data.get("state") or {}
    kind = state.get("kind")
    record_id = state.get("record_id")
    tid = update.effective_user.id
    binance_order_id = (update.message.text or "").strip()

    if not binance_order_id:
        await update.message.reply_text("⚠️ Please send a valid Binance Order ID.")
        return

    if kind not in ("order", "deposit") or not record_id:
        context.user_data.pop("state", None)
        return

    if db.is_binance_order_id_used(binance_order_id, exclude_kind=kind, exclude_id=record_id):
        await update.message.reply_text(kb.get_header("binance_id_duplicate_message"), parse_mode="HTML")
        return  # keep state — let them try again with the correct ID

    checking_msg = await update.message.reply_text(kb.get_header("binance_verifying_message"), parse_mode="HTML")

    if kind == "order":
        o = db.get_order(record_id)
        if not o or o["telegram_id"] != tid or o["status"] != "pending":
            context.user_data.pop("state", None)
            await update.message.reply_text("⚠️ This order is no longer pending.")
            return
        db.set_order_binance_id(record_id, binance_order_id)
        expected_usd = db.inr_to_usd(o["price"])
        matched = bu.find_matching_payment(binance_order_id, expected_usd)
        context.user_data.pop("state", None)
        try:
            await checking_msg.delete()
        except Exception:
            pass
        if matched:
            await deliver_order_key(context, record_id, o, method="binance")
        else:
            db.set_order_status(record_id, "review")
            await update.message.reply_text(kb.get_header("binance_verify_pending_message"), parse_mode="HTML",
                                             reply_markup=kb.review_pending_kb())
            await ch._notify_admins_order(context, record_id)
        return

    # kind == "deposit"
    dep = db.get_deposit(record_id)
    if not dep or dep["telegram_id"] != tid or dep["status"] != "pending":
        context.user_data.pop("state", None)
        await update.message.reply_text("⚠️ This deposit is no longer pending.")
        return
    db.set_deposit_binance_id(record_id, binance_order_id)
    expected_usd = db.inr_to_usd(dep["amount"])
    matched = bu.find_matching_payment(binance_order_id, expected_usd)
    context.user_data.pop("state", None)
    try:
        await checking_msg.delete()
    except Exception:
        pass

    if not matched:
        db.set_deposit_status(record_id, "review")
        await update.message.reply_text(kb.get_header("binance_verify_pending_message"), parse_mode="HTML",
                                         reply_markup=kb.review_pending_kb())
        await ch._notify_admins_deposit(context, record_id)
        return

    if dep.get("purpose") == "reseller_upgrade":
        db.set_deposit_status(record_id, "completed")
        await ch.complete_reseller_upgrade(context, record_id, "Binance (Auto-Verified)")
        return

    u = db.get_user(tid)
    previous_balance = u["balance"]
    db.set_deposit_status(record_id, "completed")
    db.adjust_balance(tid, dep["amount"], "deposit", f"Deposit #{record_id} auto-verified (Binance)")
    db.set_deposit_balances(record_id, previous_balance, previous_balance + dep["amount"])
    db.credit_referral_commission(tid, dep["amount"], f"deposit #{record_id}")
    await context.bot.send_message(
        tid,
        kb.get_header("deposit_confirmed_message", amount=dep["amount"], previous_balance=previous_balance,
                      new_balance=previous_balance + dep["amount"]),
        parse_mode="HTML")
    await ch.notify_admins_deposit_completed(context, record_id, "Binance (Auto-Verified)")


async def _send_qr_gateway_order(q, context, chat_id, tid, order_id, price, caption):
    """Creates a FamPay order for this product purchase and shows the QR with auto-verify
    running in the background. Falls back to the old static UPI-ID QR (manual review) if
    the gateway call fails, so orders never get completely stuck."""
    order = fp.create_order(price)
    if order:
        db.set_order_gateway_order(order_id, order["order_id"], order.get("expires_at"))
        gw_caption = caption + "\n\nThis QR expires in 5 minutes."
        markup = kb.order_qr_gateway_kb(order_id)
        if order.get("qr_url"):
            sent = await context.bot.send_photo(chat_id, order["qr_url"], caption=gw_caption,
                                                 parse_mode="HTML", reply_markup=markup)
        else:
            sent = await context.bot.send_message(chat_id, gw_caption, parse_mode="HTML", reply_markup=markup)
        try:
            await q.delete_message()
        except Exception:
            pass
        return sent

    # ---- Fallback: gateway unreachable / API key missing -> old manual flow ----
    upi_id = db.get_setting("upi_id", "")
    payee_name = db.get_setting("payee_name", "Shop")
    markup = kb.order_qr_kb(order_id)
    if upi_id:
        qr_img = generate_upi_qr(upi_id, payee_name, price, f"Order{order_id}")
        sent = await context.bot.send_photo(chat_id, qr_img, caption=caption, parse_mode="HTML", reply_markup=markup)
        try:
            await q.delete_message()
        except Exception:
            pass
        return sent
    note = caption + "\n\n(The admin hasn't set a UPI ID yet.)"
    return await q.edit_message_text(note, parse_mode="HTML", reply_markup=markup)


async def _send_mfs_order(q, context, chat_id, order_id, price, method):
    """Manual bKash/Nagad order payment: shows a scan-to-copy QR (number + amount +
    reference encoded as text — NOT an auto-fill payment intent like UPI, since
    bKash/Nagad have no public deep-link standard for that) and reuses the same
    'I Have Paid -> screenshot -> admin review' flow as the UPI fallback."""
    number = db.get_setting(f"{method}_number", "")
    reference = db.get_order(order_id)["reference"]
    label = "bKash" if method == "bkash" else "Nagad"
    bdt_amount = db.inr_to_bdt(price)
    caption = kb.get_header(f"{method}_order_message", amount=f"{bdt_amount:.0f}",
                             number=number or "(not set)", reference=reference)
    markup = kb.order_qr_kb(order_id)
    if number:
        qr_img = generate_text_qr(f"{label} Number: {number}\nAmount: {bdt_amount:.0f}\nRef: ORDER{order_id}")
        sent = await context.bot.send_photo(chat_id, qr_img, caption=caption, parse_mode="HTML", reply_markup=markup)
        try:
            await q.delete_message()
        except Exception:
            pass
    else:
        note = caption + f"\n\n(The admin hasn't set a {label} number yet.)"
        sent = await q.edit_message_text(note, parse_mode="HTML", reply_markup=markup)
    return sent



async def _send_mfs_deposit(q, context, chat_id, deposit_id, inr_amount, method):
    """Manual bKash/Nagad deposit payment — same scan-to-copy QR + screenshot review
    pattern as _send_mfs_order, but for wallet deposits."""
    number = db.get_setting(f"{method}_number", "")
    reference = db.get_deposit(deposit_id)["reference"]
    label = "bKash" if method == "bkash" else "Nagad"
    bdt_amount = db.inr_to_bdt(inr_amount)
    caption = kb.get_header(f"{method}_deposit_message", amount=f"{bdt_amount:.0f}",
                             number=number or "(not set)", reference=reference)
    markup = kb.deposit_qr_kb(deposit_id)
    if number:
        qr_img = generate_text_qr(f"{label} Number: {number}\nAmount: {bdt_amount:.0f}\nRef: DEP{deposit_id}")
        sent = await context.bot.send_photo(chat_id, qr_img, caption=caption, parse_mode="HTML", reply_markup=markup)
        try:
            await q.delete_message()
        except Exception:
            pass
    else:
        note = caption + f"\n\n(The admin hasn't set a {label} number yet.)"
        sent = await q.edit_message_text(note, parse_mode="HTML", reply_markup=markup)
    return sent


async def send_product_plans(update_or_query, context, product_id, tid, role, is_callback):
    """Shared by both the normal Shop flow and the /start deep-link flow."""
    p = db.get_product(product_id)
    durations = db.list_durations(product_id)
    pairs = []
    for d in durations:
        price = db.get_price_for_user(d["id"], tid, role)
        if price is not None:
            pairs.append((d["id"], d["label"], price, d.get("icon")))
    if not pairs:
        text = "⚠️ Pricing for this product hasn't been set yet."
        markup = kb.back_main_kb()
    else:
        prompt = db.get_setting("text_product_prompt", "Choose your package to purchase:")
        header_line = kb.get_header("product_header", product_name=stylize(p['name'].upper()))
        text = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>{header_line}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{prompt}"
        )
        markup = kb.user_durations_kb(pairs, product_id, p["category_id"])
    if is_callback:
        await update_or_query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await update_or_query.reply_text(text, parse_mode="HTML", reply_markup=markup)


def _start_checkout_timer(context, chat_id, message_id, kind, item_id, base_text, has_photo, keyboard):
    """No-op: live countdown editing was removed per request. The order/deposit still
    auto-cancels after 5 minutes via the global cleanup job in main.py, which also
    sends the PAYMENT EXPIRED message — this function is kept only so existing call
    sites don't need to change."""
    return


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_new_user = db.get_user(user.id) is None
    u = db.get_or_create_user(user.id, user.username, user.first_name)
    if u["banned"]:
        await update.message.reply_text("🚫 You are banned from this bot.")
        return

    if is_new_user and context.args and context.args[0].startswith("ref_"):
        try:
            referrer_id = int(context.args[0].split("_", 1)[1])
            db.set_referrer(user.id, referrer_id)
        except ValueError:
            pass

    if is_new_user:
        username_display = f"@{user.username}" if user.username else "(no username)"
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"🆕 <b>New user started the bot!</b>\n\n"
                    f"👤 Name: {user.first_name or ''}\n"
                    f"🔖 Username: {username_display}\n"
                    f"🆔 ID: <code>{user.id}</code>",
                    parse_mode="HTML")
            except Exception:
                pass

    deep_link_product_id = None
    if context.args and context.args[0].startswith("prod_"):
        try:
            deep_link_product_id = int(context.args[0].split("_", 1)[1])
        except ValueError:
            deep_link_product_id = None

    trial_token = None
    if context.args and context.args[0].startswith("trialkey_"):
        trial_token = context.args[0].split("_", 1)[1]

    if not u["phone_number"]:
        if deep_link_product_id:
            context.user_data["pending_deeplink_product"] = deep_link_product_id
        if trial_token:
            context.user_data["pending_trial_token"] = trial_token
        shop_name = db.get_setting("shop_name", "Satyam's Shop")
        name = user.first_name or "there"
        text = kb.get_header("verification_required_message", shop_name=stylize(shop_name.upper()), name=name)
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb.contact_request_kb())
        return

    if trial_token:
        return await deliver_trial_key(update.message, user.id, trial_token)

    if deep_link_product_id and db.get_product(deep_link_product_id):
        return await send_product_plans(update.message, context, deep_link_product_id, user.id, u["role"],
                                         is_callback=False)

    text = build_welcome_text(user.first_name)
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb.user_main_menu(u["role"]))


async def deliver_trial_key(message, tid, token):
    """Redeems a one-time trial-key link created in user_callback (u_trialget_...).
    This is where the key actually gets popped from stock / the claim flag actually
    gets set — ONLY once the user has completed the shortener and opened this
    deep-link, so a shortener left unfinished never consumes stock or a claim."""
    if not db.is_trial_button_enabled():
        await message.reply_text("⚠️ Free Trial is currently unavailable.")
        return
    raw = db.get_setting(f"trialtoken_{token}", None)
    if not raw:
        await message.reply_text(
            "⚠️ This link has already been used or has expired.\n"
            "Go to 🎁 Free Trial in the menu to claim a fresh one if you haven't already.")
        return
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        db.delete_setting(f"trialtoken_{token}")
        await message.reply_text("⚠️ Something went wrong reading this link. Please try claiming again.")
        return
    db.delete_setting(f"trialtoken_{token}")  # one-time use, redeemed either way from here on
    if data.get("tid") != tid:
        await message.reply_text("⚠️ This link isn't for your account.")
        return

    trial_product_id = data.get("trial_product_id")
    tp = db.get_trial_product(trial_product_id)
    if not tp:
        await message.reply_text("⚠️ This trial product no longer exists.")
        return
    name = tp["name"]

    if data.get("mode") == "link":
        await message.reply_text(
            f"🎁 <b>{name} — Trial Unlocked!</b>\n\nTap below to open it.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔓 Open", url=tp["link"])]]))
    else:
        key = db.pop_trial_key(trial_product_id, tid)
        if not key:
            await message.reply_text("😔 Out of trial stock right now, check back later.")
            return
        await message.reply_text(
            f"🎁 <b>{name} — Your Key</b>\n\n"
            f"🔑 <code>{key}</code>\n\n"
            "Enjoy! 🎉",
            parse_mode="HTML")


async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    user = update.effective_user
    if not contact:
        return
    if contact.user_id and contact.user_id != user.id:
        await update.message.reply_text("⚠️ Please share your own contact, not someone else's.")
        return
    db.set_phone_number(user.id, contact.phone_number)
    await update.message.reply_text(kb.get_header("phone_verified_message"), parse_mode="HTML",
                                     reply_markup=ReplyKeyboardRemove())
    pending_product_id = context.user_data.pop("pending_deeplink_product", None)
    pending_trial_token = context.user_data.pop("pending_trial_token", None)
    u = db.get_user(user.id)
    if pending_trial_token:
        return await deliver_trial_key(update.message, user.id, pending_trial_token)
    if pending_product_id and db.get_product(pending_product_id):
        return await send_product_plans(update.message, context, pending_product_id, user.id, u["role"],
                                         is_callback=False)
    text = build_welcome_text(user.first_name)
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb.user_main_menu(u["role"]))


async def user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    tid = update.effective_user.id
    data = q.data

    # Fast path: keypad digit/backspace taps skip the DB round-trip entirely for snappier response.
    # (The "✅" confirm still goes through the normal path below, which does validate against the DB.)
    if data.startswith("u_dep_key_") and data.split("_")[-1] != "✅":
        key = data.split("_")[-1]
        cur = context.user_data.get("deposit_amount", "")
        if key == "⌫":
            cur = cur[:-1]
        elif len(cur) < 6:
            cur += key
        context.user_data["deposit_amount"] = cur
        await asyncio.gather(
            q.answer(),
            q.edit_message_text(f"💵 Enter the amount (USD) you'd like to deposit:\n\nAmount: ${cur or 0}",
                                 reply_markup=kb.deposit_amount_kb(cur)),
        )
        return

    u = db.get_user(tid)
    if not u or u["banned"]:
        await q.answer("🚫 Banned.", show_alert=True)
        return
    await q.answer()

    if data == "u_back_main":
        text = build_welcome_text(update.effective_user.first_name)
        try:
            return await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb.user_main_menu(u["role"]))
        except Exception:
            try:
                await q.message.delete()
            except Exception:
                pass
            return await context.bot.send_message(update.effective_chat.id, text, parse_mode="HTML",
                                                    reply_markup=kb.user_main_menu(u["role"]))

    # ---------- SHOP ----------
    if data == "u_shop":
        cats = db.list_categories()
        subtitle = db.get_setting("text_shop_subtitle", "")
        header = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>{kb.get_header('shop_header')}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{subtitle}"
        )
        return await q.edit_message_text(header, parse_mode="HTML", reply_markup=kb.user_categories_kb(cats))

    # ---------- TRIAL ----------
    if data == "u_trial":
        if not db.is_trial_button_enabled():
            await q.answer("⚠️ Free Trial is currently unavailable.", show_alert=True)
            return
        trial_products = db.list_trial_products()
        header = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "<b>🎁 FREE TRIAL</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Pick a product below to instantly claim a free trial key."
        )
        if not trial_products:
            return await q.edit_message_text(header + "\n\n⚠️ No trial products available right now.",
                                              parse_mode="HTML", reply_markup=kb.back_btn("u_back_main"))
        return await q.edit_message_text(header, parse_mode="HTML",
                                          reply_markup=kb.user_trial_products_kb(trial_products))

    if data.startswith("u_trialget_"):
        if not db.is_trial_button_enabled():
            await q.answer("⚠️ Free Trial is currently unavailable.", show_alert=True)
            return
        trial_product_id = int(data.split("_")[-1])
        tp = db.get_trial_product(trial_product_id)
        if not tp:
            await q.answer("⚠️ This trial product no longer exists.", show_alert=True)
            trial_products = db.list_trial_products()
            return await q.edit_message_text("🎁 <b>FREE TRIAL</b>", parse_mode="HTML",
                                              reply_markup=kb.user_trial_products_kb(trial_products))

        # Trial claims are unlimited: no cooldown, no "already claimed" block.
        # A user can claim this product's trial as many times as they like, and
        # each attempt gets its own fresh one-time deep-link + shortener link.
        #
        # IMPORTANT: we do NOT pop a key here. That only happens in
        # deliver_trial_key, once the user has actually completed the shortener
        # and opened the deep-link back to the bot. This check here is just
        # advisory (avoid handing out a token that's obviously dead on arrival) —
        # the real, authoritative check happens at redemption time.
        if tp.get("link"):
            payload = {"tid": tid, "trial_product_id": trial_product_id, "mode": "link"}
        else:
            if db.count_available_trial_keys(trial_product_id) <= 0:
                await q.answer("😔 Out of trial stock right now, check back later.", show_alert=True)
                return
            payload = {"tid": tid, "trial_product_id": trial_product_id, "mode": "key"}

        # Every trial delivery (key or link) goes through this same one-time deep-link
        # token, so it can be wrapped by the shortener below - the user only reaches
        # deliver_trial_key (which does the real claim + hands over the key/link) by
        # completing it.
        token = secrets.token_urlsafe(16)
        db.set_setting(f"trialtoken_{token}", json.dumps(payload))
        bot_username = (await context.bot.get_me()).username
        deep_link = f"https://t.me/{bot_username}?start=trialkey_{token}"

        # shorten_url does a blocking network call — run it off the event loop so a
        # slow/unreachable shortener can't freeze the whole bot for everyone else.
        try:
            link = await asyncio.to_thread(fp_shorten_or_fallback, deep_link)
        except Exception:
            logger.exception("u_trialget_: shortener call blew up, falling back to direct link")
            link = deep_link

        note = ("🔗 Tap the button below, complete it, and you'll land back here with your trial.\n"
                "⚠️ One-time link — it only works once and only for you, so don't share it.")
        text = f"🎁 <b>{tp['name']} — Trial Claimed!</b>\n\n{note}"
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔑 Get Your Key", url=link)],
            [kb.back_button("u_trial")],
        ])
        # Same message may be a photo (caption) or plain text depending on how the
        # user got here — pick the right edit call, and if editing fails for any
        # reason, still get the link to the user instead of failing silently.
        target = q.message.edit_caption if q.message.caption else q.edit_message_text
        try:
            await target(text, parse_mode="HTML", reply_markup=markup)
        except Exception:
            logger.exception("u_trialget_: edit failed, sending as a new message instead")
            await context.bot.send_message(update.effective_chat.id, text, parse_mode="HTML", reply_markup=markup)
        return

    if data.startswith("u_cat_"):
        cat_id = int(data.split("_")[-1])
        products = db.list_products(cat_id, role=u["role"])
        cat = db.get_category(cat_id)
        shop_name = db.get_setting("shop_name", "Satyam's Shop")
        prompt = db.get_setting("text_category_prompt", "Choose a product")
        header_line = kb.get_header("category_header",
                                     shop_name=stylize(shop_name.upper()),
                                     category_name=stylize(cat['name'].upper()))
        header = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>{header_line}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{prompt}"
        )
        if not products:
            return await q.edit_message_text(header + "\n\n⚠️ No products available yet.", parse_mode="HTML",
                                              reply_markup=kb.user_categories_kb(db.list_categories()))
        return await q.edit_message_text(header, parse_mode="HTML", reply_markup=kb.user_products_kb(products, cat_id))

    if data.startswith("u_prod_"):
        product_id = int(data.split("_")[-1])
        p = db.get_product(product_id)
        durations = db.list_durations(product_id)
        pairs = []
        for d in durations:
            price = db.get_price_for_user(d["id"], tid, u["role"])
            if price is not None:
                pairs.append((d["id"], d["label"], price, d.get("icon")))
        if not pairs:
            return await q.edit_message_text("⚠️ Pricing for this product hasn't been set yet.",
                                              reply_markup=kb.back_btn(f"u_cat_{p['category_id']}"))
        prompt = db.get_setting("text_product_prompt", "Choose your package to purchase:")
        header_line = kb.get_header("product_header", product_name=stylize(p['name'].upper()))
        header = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>{header_line}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{prompt}"
        )
        return await q.edit_message_text(header, parse_mode="HTML",
                                          reply_markup=kb.user_durations_kb(pairs, product_id, p["category_id"]))

    if data.startswith("u_dur_"):
        duration_id = int(data.split("_")[-1])
        context.user_data["pending_duration"] = duration_id
        context.user_data.pop("coupon_code", None)
        text, keyboard = _build_order_summary(duration_id, tid, u["role"], context)
        return await q.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)

    if data == "u_apply_coupon":
        duration_id = context.user_data.get("pending_duration")
        if not duration_id:
            await q.answer("Session expired, please pick a plan again.", show_alert=True)
            return
        context.user_data["state"] = {"action": "await_coupon_code", "duration_id": duration_id}
        return await q.edit_message_text("🎟️ Enter your coupon code:",
                                          reply_markup=kb.back_btn(f"u_dur_{duration_id}"))

    if data.startswith("u_paybal_"):
        duration_id = int(data.split("_")[-1])
        d = db.get_duration(duration_id)
        price = _effective_price(duration_id, tid, u["role"], context)
        if u["balance"] < price:
            return await q.edit_message_text(
                kb.get_header("insufficient_balance_message", balance=u['balance'], required=price),
                parse_mode="HTML", reply_markup=kb.back_main_kb())
        key = db.pop_key(duration_id, tid)
        if not key:
            return await q.edit_message_text(kb.get_header("out_of_stock_message"), parse_mode="HTML",
                                              reply_markup=kb.stock_out_kb())
        db.adjust_balance(tid, -price, "purchase", f"Bought {d['label']}")
        applied_code = context.user_data.pop("coupon_code", None)
        order_id = db.create_order(tid, d["product_id"], duration_id, price, "balance", coupon_code=applied_code)
        db.set_order_status(order_id, "completed")
        db.set_order_delivered_key(order_id, key)
        db.credit_referral_commission(tid, price, f"product order #{order_id}")
        if applied_code:
            db.record_coupon_usage(applied_code, tid)
        product = db.get_product(d["product_id"])
        await ch.notify_admins_order_completed(context, order_id, "Wallet Balance", key)
        try:
            return await q.edit_message_text(
                kb.get_header("key_delivered_message", order_id=order_id, product_name=product['name'],
                              duration_label=d['label'], price=price, key=key,
                              payment_mode=kb.get_header('method_label_balance')),
                parse_mode="HTML", reply_markup=kb.back_main_kb())
        except Exception:
            return await q.edit_message_text(
                f"🎉 YOUR PAYMENT HAS BEEN APPROVED! 🎉\n\n"
                f"🧾 Order ID: #{order_id}\n📦 Product: {product['name']} - {d['label']}\n"
                f"💰 Price: ₹{price}\n\n🔑 Your Digital Item/License Code:\nKey: {key}\n\n"
                f"Thank you for shopping with us! Have a great day.",
                reply_markup=kb.back_main_kb())

    if data.startswith("u_payqr_"):
        duration_id = int(data.split("_")[-1])
        d = db.get_duration(duration_id)
        p = db.get_product(d["product_id"])
        price = _effective_price(duration_id, tid, u["role"], context)
        order_id = db.create_order(tid, d["product_id"], duration_id, price, "qr", coupon_code=context.user_data.get("coupon_code"))
        context.user_data.pop("coupon_code", None)
        upi_id = db.get_setting("upi_id", "")
        username_display = f"@{update.effective_user.username}" if update.effective_user.username else "(no username)"
        balance_note = f"₹{u['balance']} (Insufficient)." if u["balance"] < price else f"₹{u['balance']}."
        caption = kb.get_header(
            "qr_order_message",
            order_id=order_id,
            customer=f"{username_display} (ID: {tid})",
            product_name=p['name'],
            duration_label=d['label'],
            amount_due=price,
            amount_usd=db.inr_to_usd(price),
            upi_id=upi_id or '(not set)',
            balance_note=balance_note,
        )
        await _send_qr_gateway_order(q, context, update.effective_chat.id, tid, order_id, price, caption)
        return

    if data.startswith("u_order_check_"):
        order_id = int(data.split("_")[-1])
        o = db.get_order(order_id)
        if not o or o["telegram_id"] != tid:
            return await q.answer("⚠️ Order not found.", show_alert=True)
        if o["status"] != "pending" or not o.get("gateway_order_id"):
            return await q.answer("This order is no longer pending.", show_alert=True)
        status, raw = fp.verify_order(o["gateway_order_id"])
        if status == "success" and not fp.amount_is_sufficient(raw, o["price"]):
            paid = fp.get_paid_amount(raw)
            logger.warning("u_order_check_%s: UNDERPAID — expected ₹%s, got ₹%s. raw=%s",
                            order_id, o["price"], paid, raw)
            try:
                await ch.notify_admins_amount_mismatch(context, "order", order_id, o["price"], paid, raw)
            except Exception:
                pass
            await q.answer(
                "⚠️ We received a payment for this order, but the amount doesn't match. "
                "Please contact support with your reference.", show_alert=True)
        elif status == "success":
            await deliver_order_key(context, order_id, o)
            await q.answer("✅ Payment Received! Check your messages for the key.", show_alert=True)
        elif status in ("failed", "expired"):
            db.set_order_status(order_id, "cancelled")
            await q.answer("❌ Payment Not Received.", show_alert=True)
            await _send_payment_not_received(context, update.effective_chat.id)
        else:
            await q.answer("❌ Payment Not Received yet.", show_alert=True)
            await _send_payment_not_received(context, update.effective_chat.id)
        return

    if data.startswith("u_paybin_"):
        duration_id = int(data.split("_")[-1])
        d = db.get_duration(duration_id)
        price = _effective_price(duration_id, tid, u["role"], context)
        usd_price = db.inr_to_usd(price)
        order_id = db.create_order(tid, d["product_id"], duration_id, price, "binance", coupon_code=context.user_data.get("coupon_code"))
        context.user_data.pop("coupon_code", None)
        order = db.get_order(order_id)
        text = _binance_card("binance_order_message", order["reference"], usd_price)
        markup = kb.order_binance_kb(order_id)
        sent = await q.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
        _start_checkout_timer(context, update.effective_chat.id, sent.message_id, "order", order_id,
                               text, has_photo=False, keyboard=markup)
        return

    if data.startswith("u_paybkash_") or data.startswith("u_paynagad_"):
        method = "bkash" if data.startswith("u_paybkash_") else "nagad"
        duration_id = int(data.split("_")[-1])
        d = db.get_duration(duration_id)
        price = _effective_price(duration_id, tid, u["role"], context)
        order_id = db.create_order(tid, d["product_id"], duration_id, price, method, coupon_code=context.user_data.get("coupon_code"))
        context.user_data.pop("coupon_code", None)
        await _send_mfs_order(q, context, update.effective_chat.id, order_id, price, method)
        return

    if data.startswith("u_paid_bin_order_"):
        order_id = int(data.split("_")[-1])
        context.user_data["state"] = {"action": "await_binance_order_id", "kind": "order", "record_id": order_id}
        msg = kb.get_header("binance_order_id_request_message")
        try:
            await q.edit_message_text(msg, parse_mode="HTML")
        except Exception:
            await context.bot.send_message(update.effective_chat.id, msg, parse_mode="HTML")
        return

    if data.startswith("u_paid_order_"):
        order_id = int(data.split("_")[-1])
        context.user_data["state"] = {"action": "await_order_screenshot", "order_id": order_id}
        target = q.message.edit_caption if q.message.caption else q.edit_message_text
        msg = kb.get_header("screenshot_request_message")
        try:
            await target(msg, parse_mode="HTML")
        except Exception:
            await context.bot.send_message(update.effective_chat.id, msg, parse_mode="HTML")
        return

    if data.startswith("u_reject_order_"):
        order_id = int(data.split("_")[-1])
        db.set_order_status(order_id, "cancelled")
        try:
            await q.message.delete()
        except Exception:
            pass
        text = "❌ Your order has been cancelled.\n\n" + build_welcome_text(update.effective_user.first_name)
        await context.bot.send_message(update.effective_chat.id, text, parse_mode="HTML",
                                        reply_markup=kb.user_main_menu(u["role"]))
        return

    # ---------- RESELLER UPGRADE ----------
    if data == "u_reseller_info":
        if u["role"] == "reseller":
            await q.answer("🎉 You're already a Reseller!", show_alert=True)
            return
        if not db.is_reseller_button_enabled():
            await q.answer("⚠️ Reseller upgrades aren't available right now.", show_alert=True)
            return
        fee = db.get_reseller_fee()
        text = kb.get_header("reseller_info_message", fee=f"{fee:.0f}")
        return await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb.reseller_info_kb())

    if data == "u_reseller_pay_upi":
        if u["role"] == "reseller" or not db.is_reseller_button_enabled():
            await q.answer("⚠️ This offer is no longer available.", show_alert=True)
            return
        fee = db.get_reseller_fee()
        if fee <= 0:
            await q.answer("⚠️ Reseller upgrade isn't available right now.", show_alert=True)
            return
        await _send_upi_gateway_deposit(q, context, update.effective_chat.id, tid, fee,
                                         "Reseller Upgrade Fee", purpose="reseller_upgrade")
        return

    if data == "u_reseller_pay_binance":
        if u["role"] == "reseller" or not db.is_reseller_button_enabled():
            await q.answer("⚠️ This offer is no longer available.", show_alert=True)
            return
        fee = db.get_reseller_fee()
        if fee <= 0:
            await q.answer("⚠️ Reseller upgrade isn't available right now.", show_alert=True)
            return
        usd_amount = db.inr_to_usd(fee)
        deposit_id = db.create_deposit(tid, fee, method="binance", purpose="reseller_upgrade")
        deposit = db.get_deposit(deposit_id)
        text = _binance_card("reseller_binance_message", deposit["reference"], usd_amount)
        markup = kb.deposit_binance_kb(deposit_id)
        sent = await q.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
        _start_checkout_timer(context, update.effective_chat.id, sent.message_id, "deposit", deposit_id,
                               text, has_photo=False, keyboard=markup)
        return

    # ---------- DEPOSIT ----------
    if data == "u_deposit":
        usd_balance = db.inr_to_usd(u["balance"])
        completed_count = db.count_completed_deposits(tid)
        plural = "s" if completed_count != 1 else ""
        header = kb.get_header(
            "deposit_add_balance_page_message",
            current_balance=usd_balance, min_amount=1, max_amount=200,
            deposit_count=completed_count, plural=plural,
        )
        return await q.edit_message_text(header, parse_mode="HTML",
                                          reply_markup=kb.deposit_presets_kb(completed_count,
                                                                              is_admin=tid in ADMIN_IDS))

    if data == "u_deposit_history":
        deposits = db.list_recent_completed_deposits(tid, limit=5)
        if not deposits:
            return await q.edit_message_text(kb.get_header("deposit_history_empty_message"),
                                              parse_mode="HTML", reply_markup=kb.back_btn("u_deposit"))
        method_labels = {
            "upi": kb.get_header("method_label_upi"),
            "qr": kb.get_header("method_label_upi"),
            "binance": kb.get_header("method_label_binance"),
            "bkash": kb.get_header("method_label_bkash"),
            "nagad": kb.get_header("method_label_nagad"),
        }
        blocks = [kb.get_header("deposit_history_header")]
        for d in deposits:
            try:
                created = datetime.datetime.fromisoformat(d["created_at"]) + datetime.timedelta(hours=5, minutes=30)
                date_str, time_str = created.strftime("%b %d"), created.strftime("%H:%M")
            except Exception:
                date_str, time_str = "-", "-"
            blocks.append(kb.get_header(
                "deposit_history_entry",
                reference=d.get("reference") or f"#{d['id']}",
                amount=d["amount"],
                balance_before=d.get("balance_before") if d.get("balance_before") is not None else "-",
                balance_after=d.get("balance_after") if d.get("balance_after") is not None else "-",
                method=method_labels.get(d.get("method"), d.get("method", "-")),
                date=date_str, time=time_str,
            ))
        return await q.edit_message_text("\n\n".join(blocks), parse_mode="HTML", reply_markup=kb.back_btn("u_deposit"))

    if data.startswith("u_dep_preset_"):
        usd_amount = float(data.split("_")[-1])
        return await q.edit_message_text(
            kb.get_header("deposit_method_select_message", amount=usd_amount),
            parse_mode="HTML", reply_markup=kb.deposit_method_kb(usd_amount))

    if data == "u_dep_custom":
        context.user_data["deposit_amount"] = ""
        return await q.edit_message_text("💵 Enter the amount (USD) you'd like to deposit:\n\nAmount: $0",
                                          reply_markup=kb.deposit_amount_kb(""))

    if data.startswith("u_dep_key_"):
        key = data.split("_")[-1]
        cur = context.user_data.get("deposit_amount", "")
        if key == "⌫":
            cur = cur[:-1]
        elif key == "✅":
            if not cur or int(cur) <= 0:
                await q.answer("Please enter an amount first.", show_alert=True)
                return
            usd_amount = float(cur)
            context.user_data["deposit_amount"] = ""
            return await q.edit_message_text(
                kb.get_header("deposit_method_select_message", amount=usd_amount),
                parse_mode="HTML", reply_markup=kb.deposit_method_kb(usd_amount))
        else:
            if len(cur) < 6:
                cur += key
        context.user_data["deposit_amount"] = cur
        return await q.edit_message_text(f"💵 Enter the amount (USD) you'd like to deposit:\n\nAmount: ${cur or 0}",
                                          reply_markup=kb.deposit_amount_kb(cur))

    if data.startswith("u_dep_method_upi_"):
        usd_amount = float(data.split("_")[-1])
        inr_amount = db.usd_to_inr(usd_amount)
        await _send_upi_gateway_deposit(q, context, update.effective_chat.id, tid, inr_amount, f"${usd_amount}")
        return

    if data == "u_dep_admin_test1":
        if tid not in ADMIN_IDS:
            return await q.answer("Admin only.", show_alert=True)
        await _send_upi_gateway_deposit(q, context, update.effective_chat.id, tid, 1, "₹1 test")
        return

    if data.startswith("u_dep_check_"):
        deposit_id = int(data.split("_")[-1])
        dep = db.get_deposit(deposit_id)
        if not dep or dep["telegram_id"] != tid:
            return await q.answer("⚠️ Deposit not found.", show_alert=True)
        if dep["status"] != "pending" or not dep.get("gateway_order_id"):
            return await q.answer("This deposit is no longer pending.", show_alert=True)
        status, raw = fp.verify_order(dep["gateway_order_id"])
        if status == "success" and not fp.amount_is_sufficient(raw, dep["amount"]):
            paid = fp.get_paid_amount(raw)
            logger.warning("u_dep_check_%s: UNDERPAID — expected ₹%s, got ₹%s. raw=%s",
                            deposit_id, dep["amount"], paid, raw)
            try:
                await ch.notify_admins_amount_mismatch(context, "deposit", deposit_id, dep["amount"], paid, raw)
            except Exception:
                pass
            await q.answer(
                "⚠️ We received a payment for this deposit, but the amount doesn't match. "
                "Please contact support with your reference.", show_alert=True)
        elif status == "success":
            if dep.get("purpose") == "reseller_upgrade":
                db.set_deposit_status(deposit_id, "completed")
                await q.answer("✅ Payment Received! Upgrading your account...", show_alert=True)
                await ch.complete_reseller_upgrade(context, deposit_id, "UPI (Auto-Verified)")
            else:
                previous_balance = u["balance"]
                db.set_deposit_status(deposit_id, "completed")
                db.adjust_balance(tid, dep["amount"], "deposit", f"Deposit #{deposit_id} auto-verified")
                db.set_deposit_balances(deposit_id, previous_balance, previous_balance + dep["amount"])
                db.credit_referral_commission(tid, dep["amount"], f"deposit #{deposit_id}")
                await q.answer("✅ Payment Received! Balance updated.", show_alert=True)
                await context.bot.send_message(
                    update.effective_chat.id,
                    kb.get_header("deposit_confirmed_message", amount=dep["amount"],
                                  previous_balance=previous_balance,
                                  new_balance=previous_balance + dep["amount"]),
                    parse_mode="HTML")
                await ch.notify_admins_deposit_completed(context, deposit_id, "UPI (Auto-Verified)")
        elif status in ("failed", "expired"):
            db.set_deposit_status(deposit_id, "cancelled")
            await q.answer("❌ Payment Not Received.", show_alert=True)
            await _send_payment_not_received(context, update.effective_chat.id)
        else:
            await q.answer("❌ Payment Not Received yet.", show_alert=True)
            await _send_payment_not_received(context, update.effective_chat.id)
        return

    if data.startswith("u_dep_method_binance_"):
        usd_amount = float(data.split("_")[-1])
        inr_amount = db.usd_to_inr(usd_amount)
        deposit_id = db.create_deposit(tid, inr_amount, method="binance")
        deposit = db.get_deposit(deposit_id)
        text = _binance_card("binance_deposit_message", deposit["reference"], usd_amount)
        markup = kb.deposit_binance_kb(deposit_id)
        sent = await q.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
        _start_checkout_timer(context, update.effective_chat.id, sent.message_id, "deposit", deposit_id,
                               text, has_photo=False, keyboard=markup)
        return

    if data.startswith("u_dep_method_bkash_") or data.startswith("u_dep_method_nagad_"):
        method = "bkash" if data.startswith("u_dep_method_bkash_") else "nagad"
        usd_amount = float(data.split("_")[-1])
        inr_amount = db.usd_to_inr(usd_amount)
        deposit_id = db.create_deposit(tid, inr_amount, method=method)
        await _send_mfs_deposit(q, context, update.effective_chat.id, deposit_id, inr_amount, method)
        return

    if data.startswith("u_paid_bin_dep_"):
        deposit_id = int(data.split("_")[-1])
        context.user_data["state"] = {"action": "await_binance_order_id", "kind": "deposit", "record_id": deposit_id}
        msg = kb.get_header("binance_order_id_request_message")
        try:
            await q.edit_message_text(msg, parse_mode="HTML")
        except Exception:
            await context.bot.send_message(update.effective_chat.id, msg, parse_mode="HTML")
        return

    if data.startswith("u_paid_dep_"):
        deposit_id = int(data.split("_")[-1])
        context.user_data["state"] = {"action": "await_deposit_screenshot", "deposit_id": deposit_id}
        msg = kb.get_header("screenshot_request_message")
        try:
            await q.message.edit_caption(msg, parse_mode="HTML")
        except Exception:
            await context.bot.send_message(update.effective_chat.id, msg, parse_mode="HTML")
        return

    if data.startswith("u_reject_dep_"):
        deposit_id = int(data.split("_")[-1])
        db.set_deposit_status(deposit_id, "cancelled")
        try:
            await q.message.delete()
        except Exception:
            pass
        text = "❌ Your deposit has been cancelled.\n\n" + build_welcome_text(update.effective_user.first_name)
        await context.bot.send_message(update.effective_chat.id, text, parse_mode="HTML",
                                        reply_markup=kb.user_main_menu(u["role"]))
        return

    # ---------- REFERRAL ----------
    if data == "u_referral":
        bot_username = (await context.bot.get_me()).username
        referral_link = f"https://t.me/{bot_username}?start=ref_{tid}"
        total_referred = db.count_referrals(tid)
        text = kb.get_header(
            "referral_page_message",
            referral_link=referral_link,
            total_referred=total_referred,
            total_bonus_earned=f"{u.get('referral_bonus_earned', 0):.2f}",
            commission_percent=int(db.REFERRAL_COMMISSION_RATE * 100),
        )
        return await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb.back_main_kb())

    # ---------- PROFILE ----------
    if data == "u_profile":
        stats = db.get_user_stats(tid)
        role_label = "Reseller 🔴" if u["role"] == "reseller" else "User 👤"
        username_display = f"@{u['username']}" if u["username"] else "(not set)"
        phone_display = u["phone_number"] or "(not shared)"
        usd_balance = db.inr_to_usd(u["balance"])
        text = kb.get_header(
            "profile_message",
            user_id=tid,
            username=username_display,
            phone=phone_display,
            role=role_label,
            balance_inr=u['balance'],
            balance_usd=usd_balance,
            total_deposit=stats['total_deposit'],
            orders_completed=stats['completed_orders'],
        )
        return await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb.back_main_kb())

    # ---------- ORDER HISTORY ----------
    if data == "u_orders":
        orders = db.list_user_orders(tid, limit=5)
        if not orders:
            return await q.edit_message_text(kb.get_header("order_history_empty_message"),
                                              parse_mode="HTML", reply_markup=kb.back_main_kb())
        method_labels = {
            "balance": kb.get_header("method_label_balance"),
            "qr": kb.get_header("method_label_upi"),
            "binance": kb.get_header("method_label_binance"),
            "bkash": kb.get_header("method_label_bkash"),
            "nagad": kb.get_header("method_label_nagad"),
        }
        blocks = [kb.get_header("order_history_header")]
        for o in orders:
            d = db.get_duration(o["duration_id"])
            p = db.get_product(o["product_id"])
            try:
                created = datetime.datetime.fromisoformat(o["created_at"]) + datetime.timedelta(hours=5, minutes=30)
                date_str, time_str = created.strftime("%b %d"), created.strftime("%H:%M")
            except Exception:
                date_str, time_str = "-", "-"
            blocks.append(kb.get_header(
                "order_history_entry",
                reference=o.get("reference") or f"#{o['id']}",
                product_name=p['name'] if p else '-',
                duration_label=d['label'] if d else '-',
                price_inr=o['price'],
                price_usd=db.inr_to_usd(o['price']),
                method=method_labels.get(o.get('method'), o.get('method', '-')),
                date=date_str, time=time_str,
                license_key=o.get('delivered_key') or '-',
            ))
        return await q.edit_message_text("\n\n".join(blocks), parse_mode="HTML", reply_markup=kb.back_main_kb())

    # ---------- DAILY GIFT ----------
    if data == "u_daily":
        is_admin_user = tid in ADMIN_IDS
        if not is_admin_user:
            remaining = db.time_until_next_gift(tid)
            if remaining:
                total_minutes = int(remaining.total_seconds() // 60)
                hours, minutes = divmod(total_minutes, 60)
                denied_text = (
                    "<blockquote>🛡️✅ <b>ACCESS DENIED!</b> 📇</blockquote>\n\n"
                    f"⏳ Please wait {hours}h {minutes}m before you can earn again. 🧨\n\n"
                    "➡️ Please try again tomorrow. 💧💧"
                )
                return await q.edit_message_text(denied_text, parse_mode="HTML",
                                                  reply_markup=kb.daily_result_kb())
        try:
            await q.message.delete()
        except Exception:
            pass
        dice_msg = await context.bot.send_dice(chat_id=update.effective_chat.id, emoji="🎲")
        dice_value = dice_msg.dice.value
        reward = db.claim_daily_gift(tid, dice_value)
        await asyncio.sleep(4)  # wait for Telegram's native dice roll animation to finish
        new_balance = db.get_user(tid)["balance"]
        result_text = (
            "<blockquote>💲 <b>LUCKY DICE RESULT</b> 🛠️</blockquote>\n\n"
            f"🎲 <b>Dice Value:</b> {dice_value}\n\n"
            f"🎁 <b>You Won:</b> ₹{reward}\n\n"
            f"💰 <b>Total Balance:</b> ₹{new_balance}\n\n"
            + ("👑 Admin mode: unlimited spins!" if is_admin_user else "Congratulations! Come back in 24 hours.")
        )
        await context.bot.send_message(update.effective_chat.id, result_text, parse_mode="HTML",
                                        reply_markup=kb.daily_result_kb())
        return
