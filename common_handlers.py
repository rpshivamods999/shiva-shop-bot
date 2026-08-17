from telegram import Update
from telegram.ext import ContextTypes

import database as db
import keyboards as kb
from config import ADMIN_IDS
from text_style import strip_emoji_tags


def _extract_custom_emoji(update: Update):
    """Look for a Telegram Premium custom emoji entity in the incoming message.
    Returns (clean_text, custom_emoji_id_or_None, debug_str) where clean_text
    has the placeholder emoji removed (so it isn't duplicated alongside the
    icon). debug_str is a temporary diagnostic dump of what Telegram actually
    sent for this message, to help pin down why an emoji isn't detected."""
    raw = update.message.text
    custom_emoji_entity = None
    custom_emoji_id = None
    for ent in (update.message.entities or []):
        if ent.type == "custom_emoji":
            custom_emoji_id = ent.custom_emoji_id
            custom_emoji_entity = ent
            break

    clean_text = raw.strip()
    if custom_emoji_entity:
        # offset/length are UTF-16 code units, so slice via a UTF-16
        # round-trip to correctly strip the placeholder emoji.
        utf16 = raw.encode("utf-16-le")
        start = custom_emoji_entity.offset * 2
        end = start + custom_emoji_entity.length * 2
        stripped_utf16 = utf16[:start] + utf16[end:]
        clean_text = stripped_utf16.decode("utf-16-le").strip()

    clean_text = strip_emoji_tags(clean_text)

    # --- TEMPORARY DEBUG (remove once the issue is diagnosed) ---
    entities_repr = [(e.type, e.offset, e.length,
                       getattr(e, "custom_emoji_id", None)) for e in (update.message.entities or [])]
    debug_str = (
        f"🔍 <b>Debug</b>\n"
        f"raw text: <code>{raw!r}</code>\n"
        f"entities: <code>{entities_repr!r}</code>\n"
        f"has_sticker: <code>{update.message.sticker is not None}</code>\n"
    )
    if update.message.sticker:
        debug_str += (
            f"sticker.type: <code>{update.message.sticker.type}</code>\n"
            f"sticker.custom_emoji_id: <code>{getattr(update.message.sticker, 'custom_emoji_id', None)}</code>\n"
        )

    return clean_text, custom_emoji_id, debug_str


def _embed_custom_emoji_html(update: Update):
    """For long-form header/paragraph text (not button labels): converts any Telegram
    Premium custom-emoji ('3D emoji') entities the admin included into
    <tg-emoji emoji-id="..."> HTML tags, so they render as the real animated/3D emoji
    wherever this text is later sent with parse_mode='HTML' — instead of collapsing
    to a plain fallback emoji character. Multiple custom emoji in one message are all
    preserved, each in its original position."""
    raw = update.message.text
    entities = sorted(
        [e for e in (update.message.entities or []) if e.type == "custom_emoji"],
        key=lambda e: e.offset, reverse=True)
    if not entities:
        return raw.strip()
    utf16 = raw.encode("utf-16-le")
    for ent in entities:
        start = ent.offset * 2
        end = start + ent.length * 2
        placeholder = utf16[start:end].decode("utf-16-le")
        tag = f'<tg-emoji emoji-id="{ent.custom_emoji_id}">{placeholder}</tg-emoji>'.encode("utf-16-le")
        utf16 = utf16[:start] + tag + utf16[end:]
    return utf16.decode("utf-16-le").strip()


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return  # e.g. an edited message or non-text update - nothing to process
    state = context.user_data.get("state")
    if not state:
        return  # no pending input expected, ignore
    action = state.get("action")
    text = update.message.text.strip()
    tid = update.effective_user.id

    # ---------------- ADMIN STATES ----------------
    if action == "await_balance_user_id":
        if not text.isdigit():
            await update.message.reply_text("⚠️ Please send a numeric Telegram ID only.")
            return
        target_id = int(text)
        target_user = db.get_user(target_id)
        if not target_user:
            await update.message.reply_text("⚠️ No user found with that ID.")
            context.user_data.pop("state", None)
            return
        context.user_data["state"] = {"action": "await_balance_adjust", "target_id": target_id}
        name = target_user["first_name"] or target_user["username"] or str(target_id)
        await update.message.reply_text(
            f"👤 User: {name}\n💰 Current Balance: ₹{target_user['balance']}\n\n"
            "✏️ Enter the amount to add or subtract.\nExample: 20 to add ₹20, -15 to subtract ₹15"
        )
        return

    if action == "await_balance_adjust":
        try:
            delta = float(text)
        except ValueError:
            await update.message.reply_text("⚠️ Please send a valid number, e.g. 20 or -15")
            return
        target_id = state["target_id"]
        db.adjust_balance(target_id, delta, "admin_adjustment", f"Admin balance adjustment: {delta:+g}")
        target_user = db.get_user(target_id)
        context.user_data.pop("state", None)
        name = target_user["first_name"] or target_user["username"] or str(target_id)
        await update.message.reply_text(
            f"✅ Balance updated.\n👤 User: {name}\n💰 New Balance: ₹{target_user['balance']}",
            reply_markup=kb.admin_main_menu()
        )
        try:
            await context.bot.send_message(
                target_id,
                f"💰 Your balance has been updated by the admin.\nNew Balance: ₹{target_user['balance']}"
            )
        except Exception:
            pass
        return

    if action == "await_reject_reason_order":
        reason = text
        order_id = state["order_id"]
        o = db.get_order(order_id)
        context.user_data.pop("state", None)
        if not o or o["status"] != "review":
            await update.message.reply_text("⚠️ This order is no longer pending review.")
            return
        db.set_order_status(order_id, "rejected")
        product = db.get_product(o["product_id"])
        duration = db.get_duration(o["duration_id"])
        try:
            details_line = (f"📦 <b>Product:</b> {product['name'] if product else '-'} "
                             f"({duration['label'] if duration else '-'})\n")
            await context.bot.send_message(
                o["telegram_id"],
                kb.get_header("payment_declined_message", id_label="Order ID", id_value=order_id,
                              order_id=order_id, deposit_id=order_id,
                              details_line=details_line, amount=f"{o['price']:.2f}", reason=reason),
                parse_mode="HTML", reply_markup=kb.declined_kb())
        except Exception:
            try:
                await context.bot.send_message(
                    o["telegram_id"],
                    f"❌ Your order #{order_id} has been declined.\nReason: {reason}",
                    reply_markup=kb.declined_kb())
            except Exception:
                pass
        await update.message.reply_text("❌ Order declined and customer notified.")
        return

    if action == "await_reject_reason_deposit":
        reason = text
        dep_id = state["deposit_id"]
        dep = db.get_deposit(dep_id)
        context.user_data.pop("state", None)
        if not dep or dep["status"] != "review":
            await update.message.reply_text("⚠️ This deposit is no longer pending review.")
            return
        db.set_deposit_status(dep_id, "rejected")
        try:
            await context.bot.send_message(
                dep["telegram_id"],
                kb.get_header("payment_declined_message", id_label="Deposit ID", id_value=dep_id,
                              order_id=dep_id, deposit_id=dep_id,
                              details_line="", amount=dep['amount'], reason=reason),
                parse_mode="HTML", reply_markup=kb.declined_kb())
        except Exception:
            try:
                await context.bot.send_message(
                    dep["telegram_id"],
                    f"❌ Your deposit #{dep_id} has been declined.\nReason: {reason}",
                    reply_markup=kb.declined_kb())
            except Exception:
                pass
        await update.message.reply_text("❌ Deposit declined and customer notified.")
        return

    if action == "await_add_product":
        context.user_data["state"] = {"action": "await_add_product_visibility", "cat_id": state["cat_id"], "name": text}
        await update.message.reply_text(
            f"📦 Product name: {text}\n\nWho should be able to see this product?",
            reply_markup=kb.product_visibility_kb())
        return

    if action == "await_add_duration":
        text, icon, debug = _extract_custom_emoji(update)
        db.add_duration(state["product_id"], text, icon=icon)
        context.user_data.pop("state", None)
        durations = db.list_durations(state["product_id"])
        p = db.get_product(state["product_id"])
        icon_note = "\n💎 3D icon saved too." if icon else ""
        await update.message.reply_text(f"✅ Duration '{text}' added.{icon_note}\n\n📦 <b>{p['name']}</b>", parse_mode="HTML",
                                         reply_markup=kb.durations_kb(durations, state["product_id"], p["category_id"]))
        await update.message.reply_text(debug, parse_mode="HTML")
        return

    if action == "await_add_category":
        text, icon, debug = _extract_custom_emoji(update)
        cat_id = db.add_category(text, icon=icon)
        context.user_data.pop("state", None)
        cats = db.list_categories()
        icon_note = "\n💎 3D icon saved too." if icon else ""
        await update.message.reply_text(f"✅ Category '{text}' added.{icon_note}\n\n🟢 <b>Manage Products</b>\n\nChoose a category:",
                                         parse_mode="HTML", reply_markup=kb.categories_kb(cats))
        await update.message.reply_text(debug, parse_mode="HTML")
        return

    if action == "await_rename_category":
        text, icon, debug = _extract_custom_emoji(update)
        db.update_category_name(state["cat_id"], text, icon=icon)
        context.user_data.pop("state", None)
        products = db.list_products(state["cat_id"])
        icon_note = "\n💎 3D icon saved too." if icon else ""
        await update.message.reply_text(f"✅ Category renamed to '{text}'.{icon_note}\n\n📦 <b>{text}</b>\n\nProducts:",
                                         parse_mode="HTML",
                                         reply_markup=kb.products_kb(products, state["cat_id"]))
        await update.message.reply_text(debug, parse_mode="HTML")
        return

    if action == "await_rename_product":
        text, icon, debug = _extract_custom_emoji(update)
        db.update_product_name(state["product_id"], text, icon=icon)
        context.user_data.pop("state", None)
        p = db.get_product(state["product_id"])
        durations = db.list_durations(state["product_id"])
        icon_note = "\n💎 3D icon saved too." if icon else ""
        await update.message.reply_text(f"✅ Product renamed to '{text}'.{icon_note}\n\n📦 <b>{text}</b>\n\nDurations:",
                                         parse_mode="HTML",
                                         reply_markup=kb.durations_kb(durations, state["product_id"], p["category_id"]))
        await update.message.reply_text(debug, parse_mode="HTML")
        return

    if action == "await_rename_duration":
        text, icon, debug = _extract_custom_emoji(update)
        db.update_duration_label(state["duration_id"], text, icon=icon)
        context.user_data.pop("state", None)
        d = db.get_duration(state["duration_id"])
        avail = db.count_available_keys(state["duration_id"])
        icon_note = "\n💎 3D icon saved too." if icon else ""
        await update.message.reply_text(
            f"✅ Duration renamed to '{text}'.{icon_note}\n\n⏳ <b>{text}</b>\n🔑 Available stock: {avail}",
            parse_mode="HTML", reply_markup=kb.duration_detail_kb(state["duration_id"], d["product_id"]))
        await update.message.reply_text(debug, parse_mode="HTML")
        return

    if action == "await_add_trial_product":
        text, icon, debug = _extract_custom_emoji(update)
        db.add_trial_product(text, icon=icon)
        context.user_data.pop("state", None)
        trial_products = db.list_trial_products()
        icon_note = "\n💎 3D icon saved too." if icon else ""
        await update.message.reply_text(
            f"✅ Trial product '{text}' added.{icon_note}\n\n🎁 <b>Manage Trial</b>",
            parse_mode="HTML", reply_markup=kb.admin_trial_menu_kb(trial_products))
        await update.message.reply_text(debug, parse_mode="HTML")
        return

    if action == "await_set_trial_link":
        trial_product_id = state["trial_product_id"]
        link = None if text.strip().lower() == "clear" else text.strip()
        db.update_trial_product_link(trial_product_id, link)
        context.user_data.pop("state", None)
        tp = db.get_trial_product(trial_product_id)
        avail = db.count_available_trial_keys(trial_product_id)
        confirm = "✅ Link removed — back to the auto-generated key link." if link is None else f"✅ Link saved: {link}"
        link_line = f"\n🔗 Link: {tp['link']}" if tp.get("link") else "\n🔗 Link: (not set — using auto-generated key link)"
        await update.message.reply_text(
            f"{confirm}\n\n🎁 <b>{tp['name']}</b>\n🔑 Available trial stock: {avail}{link_line}",
            parse_mode="HTML", reply_markup=kb.admin_trial_product_kb(trial_product_id))
        return

    if action == "await_rename_trial_product":
        text, icon, debug = _extract_custom_emoji(update)
        db.update_trial_product_name(state["trial_product_id"], text, icon=icon)
        context.user_data.pop("state", None)
        avail = db.count_available_trial_keys(state["trial_product_id"])
        icon_note = "\n💎 3D icon saved too." if icon else ""
        await update.message.reply_text(
            f"✅ Renamed to '{text}'.{icon_note}\n\n🎁 <b>{text}</b>\n🔑 Available trial stock: {avail}",
            parse_mode="HTML", reply_markup=kb.admin_trial_product_kb(state["trial_product_id"]))
        await update.message.reply_text(debug, parse_mode="HTML")
        return

    if action == "await_add_trial_keys":
        keys = [k for k in text.splitlines() if k.strip()]
        db.add_trial_keys(state["trial_product_id"], keys)
        context.user_data.pop("state", None)
        avail = db.count_available_trial_keys(state["trial_product_id"])
        tp = db.get_trial_product(state["trial_product_id"])
        await update.message.reply_text(
            f"✅ {len(keys)} trial key(s) added.\n🎁 <b>{tp['name']}</b>\n🔑 Available trial stock: {avail}",
            parse_mode="HTML", reply_markup=kb.admin_trial_product_kb(state["trial_product_id"]))
        return

    if action == "await_stock_key":
        keys = [k for k in text.splitlines() if k.strip()]
        db.add_keys(state["duration_id"], keys)
        context.user_data.pop("state", None)
        avail = db.count_available_keys(state["duration_id"])
        d = db.get_duration(state["duration_id"])
        await update.message.reply_text(
            f"✅ {len(keys)} key(s) added.\n⏳ <b>{d['label']}</b>\n🔑 Available stock: {avail}",
            parse_mode="HTML", reply_markup=kb.duration_detail_kb(state["duration_id"], d["product_id"]))
        return

    if action in ("await_price_all", "await_price_reseller"):
        try:
            price = float(text)
        except ValueError:
            await update.message.reply_text("⚠️ Please send a number only, e.g. 199")
            return
        d = db.get_duration(state["duration_id"])
        if action == "await_price_all":
            db.set_price_all(state["duration_id"], price)
        else:
            db.set_price_reseller(state["duration_id"], price)
        context.user_data.pop("state", None)
        await update.message.reply_text(f"✅ Price set to ₹{price}.\n⏳ <b>{d['label']}</b>", parse_mode="HTML",
                                         reply_markup=kb.duration_detail_kb(state["duration_id"], d["product_id"]))
        return

    if action == "await_price_user_id":
        if not text.isdigit():
            await update.message.reply_text("⚠️ Please send a numeric Telegram ID only.")
            return
        state["target_id"] = int(text)
        state["action"] = "await_price_user_price"
        context.user_data["state"] = state
        await update.message.reply_text("✏️ Now send the price for this user (numeric):")
        return

    if action == "await_price_user_price":
        try:
            price = float(text)
        except ValueError:
            await update.message.reply_text("⚠️ Please send a number only, e.g. 199")
            return
        d = db.get_duration(state["duration_id"])
        db.set_price_user(state["duration_id"], state["target_id"], price)
        context.user_data.pop("state", None)
        await update.message.reply_text(
            f"✅ Price set to ₹{price} for user <code>{state['target_id']}</code>.\n⏳ <b>{d['label']}</b>",
            parse_mode="HTML", reply_markup=kb.duration_detail_kb(state["duration_id"], d["product_id"]))
        return

    if action == "await_welcome":
        db.set_setting("welcome_message", text)
        context.user_data.pop("state", None)
        await update.message.reply_text("✅ Welcome message updated.", reply_markup=kb.settings_kb())
        return

    if action == "await_shopname":
        db.set_setting("shop_name", text)
        context.user_data.pop("state", None)
        await update.message.reply_text("✅ Shop name updated.", reply_markup=kb.settings_kb())
        return

    if action == "await_upi_id":
        db.set_setting("upi_id", text)
        context.user_data.pop("state", None)
        await update.message.reply_text(f"✅ UPI ID set to: <code>{text}</code>", parse_mode="HTML",
                                         reply_markup=kb.settings_kb())
        return

    if action == "await_payee_name":
        db.set_setting("payee_name", text)
        context.user_data.pop("state", None)
        await update.message.reply_text(f"✅ Payee name set to: {text}", reply_markup=kb.settings_kb())
        return

    if action == "await_howto_link":
        db.set_setting("how_to_use_link", text)
        context.user_data.pop("state", None)
        await update.message.reply_text(f"✅ How To Use link set to:\n{text}", reply_markup=kb.settings_kb())
        return

    if action == "await_files_link":
        db.set_setting("updated_file_group_link", text)
        context.user_data.pop("state", None)
        await update.message.reply_text(f"✅ Updated File link set to:\n{text}", reply_markup=kb.settings_kb())
        return

    if action == "await_usd_rate":
        try:
            rate = float(text)
            if rate <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("⚠️ Please send a valid positive number, e.g. 90")
            return
        db.set_setting("usd_rate", str(rate))
        context.user_data.pop("state", None)
        await update.message.reply_text(f"✅ Rate set: ₹{rate} = $1", reply_markup=kb.settings_kb())
        return

    if action == "await_bdt_rate":
        try:
            rate = float(text)
            if rate <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("⚠️ Please send a valid positive number, e.g. 115")
            return
        db.set_setting("bdt_rate", str(rate))
        context.user_data.pop("state", None)
        await update.message.reply_text(f"✅ Rate set: ৳{rate} = $1", reply_markup=kb.settings_kb())
        return

    if action == "await_bkash_number":
        db.set_setting("bkash_number", text)
        context.user_data.pop("state", None)
        await update.message.reply_text(f"✅ bKash Number set to: <code>{text}</code>", parse_mode="HTML",
                                         reply_markup=kb.settings_kb())
        return

    if action == "await_nagad_number":
        db.set_setting("nagad_number", text)
        context.user_data.pop("state", None)
        await update.message.reply_text(f"✅ Nagad Number set to: <code>{text}</code>", parse_mode="HTML",
                                         reply_markup=kb.settings_kb())
        return

    if action == "await_binance_pay_id":
        db.set_setting("binance_pay_id", text)
        context.user_data.pop("state", None)
        await update.message.reply_text(f"✅ Binance Pay ID set to: {text}", reply_markup=kb.settings_kb())
        return

    if action == "await_binance_api_key":
        db.set_setting("binance_api_key", text)
        context.user_data.pop("state", None)
        await update.message.reply_text("✅ Binance API Key saved.", reply_markup=kb.settings_kb())
        return

    if action == "await_binance_api_secret":
        db.set_setting("binance_api_secret", text)
        context.user_data.pop("state", None)
        await update.message.reply_text("✅ Binance API Secret saved.", reply_markup=kb.settings_kb())
        return

    if action == "await_fampay_api_key":
        db.set_setting("fampay_api_key", text.strip())
        context.user_data.pop("state", None)
        await update.message.reply_text("✅ FamPay API Key saved. UPI deposits will now auto-verify.",
                                         reply_markup=kb.settings_kb())
        return

    if action == "await_earnlinks_api_key":
        db.set_setting("earnlinks_api_token", text.strip())
        context.user_data.pop("state", None)
        await update.message.reply_text("✅ Earnlinks API Token saved. Trial links will now be shortened.",
                                         reply_markup=kb.settings_kb())
        return

    if action == "await_payproof_link":
        db.set_setting("pay_proof_group_link", text)
        context.user_data.pop("state", None)
        await update.message.reply_text(f"✅ Pay Proof group link set to:\n{text}", reply_markup=kb.settings_kb())
        return

    if action == "await_support_username":
        username = text.lstrip("@").strip()
        db.set_setting("support_username", username)
        context.user_data.pop("state", None)
        await update.message.reply_text(f"✅ Support username set to: @{username}",
                                         reply_markup=kb.settings_kb())
        return

    if action == "await_edit_button":
        key = state["key"]

        # Bot API 9.4: detect a Telegram Premium custom emoji in the message
        # and save its custom_emoji_id as this button's 3D icon.
        icon_note = ""
        custom_emoji_id = None
        custom_emoji_entity = None
        for ent in (update.message.entities or []):
            if ent.type == "custom_emoji":
                custom_emoji_id = ent.custom_emoji_id
                custom_emoji_entity = ent
                break

        label_text = text
        if custom_emoji_entity:
            # entity offset/length are UTF-16 code units, so slice via a
            # UTF-16 round-trip to correctly strip the placeholder emoji
            # (which would otherwise duplicate the icon shown on the button).
            raw = update.message.text
            utf16 = raw.encode("utf-16-le")
            start = custom_emoji_entity.offset * 2
            end = start + custom_emoji_entity.length * 2
            stripped_utf16 = utf16[:start] + utf16[end:]
            label_text = stripped_utf16.decode("utf-16-le").strip()

        db.set_setting(f"btn_label_{key}", label_text)

        if custom_emoji_id:
            db.set_setting(f"icon_{key}", custom_emoji_id)
            icon_note = "\n💎 3D icon saved too."

        context.user_data.pop("state", None)
        await update.message.reply_text(
            f"✅ Button updated: {label_text}{icon_note}\n\nApplied instantly for all users.",
            reply_markup=kb.customize_buttons_kb())
        return

    if action == "await_edit_text":
        key = state["key"]
        db.set_setting(f"text_{key}", text)
        context.user_data.pop("state", None)
        await update.message.reply_text("✅ Text updated.\n\nApplied instantly for all users.", parse_mode="HTML",
                                         reply_markup=kb.customize_texts_kb())
        return

    if action == "await_edit_header":
        key = state["key"]
        final_text = _embed_custom_emoji_html(update)
        db.set_setting(f"header_{key}", final_text)
        context.user_data.pop("state", None)
        icon_note = "\n💎 3D emoji embedded." if "<tg-emoji" in final_text else ""
        await update.message.reply_text(
            f"✅ Header updated:\n<b>{final_text}</b>{icon_note}\n\nApplied instantly for all users.",
            parse_mode="HTML", reply_markup=kb.customize_headers_kb())
        return

    if action == "await_broadcast_specific_id":
        if not text.isdigit():
            await update.message.reply_text("⚠️ Please send a numeric Telegram ID only.")
            return
        context.user_data["state"] = {"action": "await_broadcast_content", "target": "specific",
                                       "target_id": int(text)}
        await update.message.reply_text("✏️ Now send the text/photo/video/voice you want to broadcast:")
        return

    if action == "await_broadcast_content":
        await _do_broadcast(update, context, state)
        context.user_data.pop("state", None)
        return

    if action == "await_coupon_new_code":
        code = text.strip().upper()
        context.user_data["state"] = {"action": "await_coupon_new_type", "code": code,
                                       "target_role": state["target_role"]}
        await update.message.reply_text(f"🎟️ Coupon code: {code}\n\nWhat type of discount?",
                                         reply_markup=kb.coupon_type_kb())
        return

    if action == "await_coupon_new_value":
        try:
            value = float(text)
        except ValueError:
            await update.message.reply_text("⚠️ Please send a valid number.")
            return
        context.user_data["state"] = {**state, "action": "await_coupon_new_duration", "value": value}
        await update.message.reply_text("⏰ How long should this coupon stay valid?",
                                         reply_markup=kb.coupon_duration_kb())
        return

    if action == "await_coupon_code":
        import user_handlers as uh
        duration_id = state["duration_id"]
        code = text.strip().upper()
        context.user_data.pop("state", None)
        tid = update.effective_user.id
        u = db.get_user(tid)
        coupon, error = db.validate_coupon(code, tid, u["role"])
        if error:
            await update.message.reply_text(error + "\nPlease try again from the plan screen.")
            return
        context.user_data["coupon_code"] = code
        summary_text, keyboard = uh._build_order_summary(duration_id, tid, u["role"], context)
        await update.message.reply_text(f"✅ Coupon '{code}' applied!\n\n{summary_text}", parse_mode="HTML",
                                         reply_markup=keyboard)
        return


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state")
    if not state:
        return
    action = state.get("action")
    photo_id = update.message.photo[-1].file_id

    if action == "await_order_screenshot":
        order_id = state["order_id"]
        db.set_order_status(order_id, "review", screenshot_file_id=photo_id)
        context.user_data.pop("state", None)
        await update.message.reply_text(
            kb.get_header("screenshot_received_message"), parse_mode="HTML",
            reply_markup=kb.review_pending_kb())
        await _notify_admins_order(context, order_id)
        return

    if action == "await_deposit_screenshot":
        deposit_id = state["deposit_id"]
        db.set_deposit_status(deposit_id, "review", screenshot_file_id=photo_id)
        context.user_data.pop("state", None)
        await update.message.reply_text(
            kb.get_header("screenshot_received_message"), parse_mode="HTML",
            reply_markup=kb.review_pending_kb())
        await _notify_admins_deposit(context, deposit_id)
        return

    if action == "await_broadcast_content":
        await _do_broadcast(update, context, state, photo_id=photo_id)
        context.user_data.pop("state", None)
        return


async def handle_other_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles video/voice/document/audio for broadcast only."""
    state = context.user_data.get("state")
    if not state or state.get("action") != "await_broadcast_content":
        return
    await _do_broadcast(update, context, state)
    context.user_data.pop("state", None)


def _referrer_display(referrer_id):
    if not referrer_id:
        return ""
    r = db.get_user(referrer_id)
    if not r:
        return f"ID {referrer_id}"
    username_display = f"@{r['username']}" if r["username"] else "(no username)"
    return f"{username_display} (ID: {referrer_id})"


async def _notify_admins_order(context, order_id):
    order = db.get_order(order_id)
    u = db.get_user(order["telegram_id"])
    d = db.get_duration(order["duration_id"])
    p = db.get_product(d["product_id"])
    cat = db.get_category(p["category_id"])
    username_display = f"@{u['username']}" if u["username"] else "(no username)"
    binance_line = f"\n🟡 <b>Binance Order ID:</b> {order['binance_order_id']}" if order.get("binance_order_id") else ""
    ref_line = f"\n🔗 <b>Referred By:</b> {_referrer_display(u.get('referred_by'))}" if u.get("referred_by") else ""
    cap = (
        "🚨 <b>NEW SHOP ORDER RECEIVED</b> 🚨\n\n"
        f"🧾 <b>Order ID:</b> #{order['id']}\n"
        f"👤 <b>Customer:</b> {username_display} (ID: {order['telegram_id']})\n"
        f"🔷 <b>Category:</b> {cat['name']}\n"
        f"🔷 <b>Product:</b> {p['name']}\n"
        f"🔷 <b>License:</b> {d['label']}\n"
        f"💰 <b>Amount Paid:</b> ₹{order['price']}"
        f"{binance_line}{ref_line}\n\n"
        "👇 Select an action below to review this transaction:"
    )
    for admin_id in ADMIN_IDS:
        try:
            if order["screenshot_file_id"]:
                await context.bot.send_photo(admin_id, order["screenshot_file_id"], caption=cap,
                                              parse_mode="HTML", reply_markup=kb.order_review_kb(order_id))
            else:
                await context.bot.send_message(admin_id, cap, parse_mode="HTML",
                                                reply_markup=kb.order_review_kb(order_id))
        except Exception:
            pass


async def _notify_admins_deposit(context, deposit_id):
    dep = db.get_deposit(deposit_id)
    u = db.get_user(dep["telegram_id"])
    username_display = f"@{u['username']}" if u["username"] else "(no username)"
    binance_line = f"\n🟡 <b>Binance Order ID:</b> {dep['binance_order_id']}" if dep.get("binance_order_id") else ""
    ref_line = f"\n🔗 <b>Referred By:</b> {_referrer_display(u.get('referred_by'))}" if u.get("referred_by") else ""
    header = ("🚨 <b>NEW RESELLER UPGRADE FEE RECEIVED</b> 🚨" if dep.get("purpose") == "reseller_upgrade"
              else "🚨 <b>NEW DEPOSIT RECEIVED</b> 🚨")
    cap = (
        f"{header}\n\n"
        f"🧾 <b>Deposit ID:</b> #{dep['id']}\n"
        f"👤 <b>Customer:</b> {username_display} (ID: {dep['telegram_id']})\n"
        f"💰 <b>Amount:</b> ₹{dep['amount']}"
        f"{binance_line}{ref_line}\n\n"
        "👇 Select an action below to review this transaction:"
    )
    for admin_id in ADMIN_IDS:
        try:
            if dep["screenshot_file_id"]:
                await context.bot.send_photo(admin_id, dep["screenshot_file_id"], caption=cap,
                                              parse_mode="HTML", reply_markup=kb.deposit_review_kb(deposit_id))
            else:
                await context.bot.send_message(admin_id, cap, parse_mode="HTML",
                                                reply_markup=kb.deposit_review_kb(deposit_id))
        except Exception:
            pass


async def notify_admins_deposit_completed(context, deposit_id, payment_mode):
    """Fires on EVERY completed deposit (balance actually credited), no matter which
    path completed it — FamPay auto-verify, Binance auto-verify, or admin manual
    approval. Sends: username, user id, mobile number, amount deposited, updated
    balance, and mode of payment."""
    dep = db.get_deposit(deposit_id)
    u = db.get_user(dep["telegram_id"])
    username_display = f"@{u['username']}" if u["username"] else "(no username)"
    mobile_display = u.get("phone_number") or "Not shared"
    ref_line = ""
    if u.get("referred_by") and u.get("role") == "user":
        commission = round(dep["amount"] * db.REFERRAL_COMMISSION_RATE, 2)
        ref_line = (f"\n🔗 <b>Referred By:</b> {_referrer_display(u['referred_by'])} "
                    f"(earned ₹{commission} commission)")
    text = (
        "🚨 <b>DEPOSIT ALERT</b> 🚨\n\n"
        f"👤 <b>Username:</b> {username_display}\n"
        f"🆔 <b>User ID:</b> {dep['telegram_id']}\n"
        f"📱 <b>Mobile Number:</b> {mobile_display}\n"
        f"💰 <b>Amount Deposited:</b> ₹{dep['amount']}\n"
        f"💳 <b>Updated Balance:</b> ₹{u['balance']}\n"
        f"🏦 <b>Mode of Payment:</b> {payment_mode}"
        f"{ref_line}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception:
            pass


async def notify_admins_amount_mismatch(context, kind, record_id, expected_amount, paid_amount, raw):
    """Fires when FamPay confirms a payment (status:"success") for a QR order/deposit
    but the confirmed amount is LESS than what the QR was generated for — the
    signature of a customer editing the 'am=' parameter of the UPI intent link
    extracted from the QR before paying. The order/deposit is left 'pending' (NOT
    auto-completed) so an admin can decide: refund the shortfall request, ask the
    customer to top up the difference, or manually approve at their discretion."""
    if kind == "deposit":
        rec = db.get_deposit(record_id)
    else:
        rec = db.get_order(record_id)
    if not rec:
        return
    u = db.get_user(rec["telegram_id"])
    username_display = f"@{u['username']}" if u and u.get("username") else "(no username)"
    utr = (raw or {}).get("data", {}).get("utr", "N/A")
    sender_name = (raw or {}).get("data", {}).get("sender_name", "N/A")
    paid_display = f"₹{paid_amount}" if paid_amount is not None else "unknown (missing from gateway response)"
    text = (
        "🚨 <b>PAYMENT AMOUNT MISMATCH</b> 🚨\n\n"
        f"⚠️ Possible tampered-QR underpayment — NOT auto-completed.\n\n"
        f"🧾 <b>{'Deposit' if kind == 'deposit' else 'Order'} ID:</b> #{record_id}\n"
        f"👤 <b>Username:</b> {username_display}\n"
        f"🆔 <b>User ID:</b> {rec['telegram_id']}\n"
        f"💰 <b>Expected Amount:</b> ₹{expected_amount}\n"
        f"💸 <b>Gateway Confirms Received:</b> {paid_display}\n"
        f"🏦 <b>UTR:</b> {utr}\n"
        f"🙋 <b>Sender Name (per gateway):</b> {sender_name}\n\n"
        f"<i>Review manually and approve, refund, or ask the customer to pay the remaining amount.</i>"
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception:
            pass


async def notify_admins_order_completed(context, order_id, payment_mode, key):
    """Fires on EVERY completed product order (key handed to the customer, or stock
    ran out), no matter which path completed it — FamPay auto-verify, Binance
    auto-verify, wallet balance, or admin manual approval. Sends: username, mobile
    number, product, duration, role, price, and the key delivered."""
    order = db.get_order(order_id)
    u = db.get_user(order["telegram_id"])
    d = db.get_duration(order["duration_id"])
    p = db.get_product(order["product_id"])
    username_display = f"@{u['username']}" if u["username"] else "(no username)"
    mobile_display = u.get("phone_number") or "Not shared"
    role_label = "Reseller" if u["role"] == "reseller" else "User"
    key_line = f"<code>{key}</code>" if key else "⚠️ Out of stock — not delivered"
    ref_line = ""
    if u.get("referred_by") and u["role"] == "user":
        commission = round(order["price"] * db.REFERRAL_COMMISSION_RATE, 2)
        ref_line = (f"\n🔗 <b>Referred By:</b> {_referrer_display(u['referred_by'])} "
                    f"(earned ₹{commission} commission)")
    text = (
        "🛒 <b>PRODUCT PURCHASE ALERT</b> 🛒\n\n"
        f"👤 <b>Username:</b> {username_display}\n"
        f"📱 <b>Mobile Number:</b> {mobile_display}\n"
        f"🔷 <b>Product:</b> {p['name']}\n"
        f"⏳ <b>Duration:</b> {d['label']}\n"
        f"🎭 <b>Role:</b> {role_label}\n"
        f"💰 <b>Price:</b> ₹{order['price']}\n"
        f"🔑 <b>Key Delivered:</b> {key_line}"
        f"{ref_line}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception:
            pass


async def complete_reseller_upgrade(context, deposit_id, payment_mode):
    """Called the moment a reseller-upgrade fee is confirmed paid — via FamPay
    auto-verify, Binance auto-verify, or admin manual approval. Promotes the user to
    'reseller' (reseller pricing kicks in immediately, and the Upgrade to Reseller
    button disappears for them on the next menu render). Per the fee rule: if the fee
    is under ₹100 it is NOT credited to the wallet; ₹100 or more IS credited."""
    dep = db.get_deposit(deposit_id)
    tid = dep["telegram_id"]
    fee = dep["amount"]
    db.credit_referral_commission(tid, fee, f"reseller upgrade fee #{deposit_id}")
    db.set_role(tid, "reseller")
    credited = fee >= 100
    if credited:
        db.adjust_balance(tid, fee, "deposit", f"Reseller upgrade fee #{deposit_id} credited to wallet")
    u = db.get_user(tid)
    credit_line = (f"\n💳 Your ₹{fee:.0f} fee has also been credited to your wallet "
                   f"(new balance: ₹{u['balance']:.0f})." if credited else "")
    try:
        await context.bot.send_message(
            tid,
            kb.get_header("reseller_upgrade_congrats_message", credit_line=credit_line),
            parse_mode="HTML", reply_markup=kb.back_main_kb())
    except Exception:
        pass
    username_display = f"@{u['username']}" if u["username"] else "(no username)"
    mobile_display = u.get("phone_number") or "Not shared"
    text = (
        "👑 <b>RESELLER UPGRADE ALERT</b> 👑\n\n"
        f"👤 <b>Username:</b> {username_display}\n"
        f"🆔 <b>User ID:</b> {tid}\n"
        f"📱 <b>Mobile Number:</b> {mobile_display}\n"
        f"💰 <b>Fee Paid:</b> ₹{fee:.0f}\n"
        f"🏦 <b>Mode of Payment:</b> {payment_mode}\n"
        f"💳 <b>Balance Credited:</b> {'Yes (₹' + f'{fee:.0f}' + ')' if credited else 'No (fee below ₹100)'}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception:
            pass


async def _do_broadcast(update, context, state, photo_id=None):
    target = state["target"]
    if target == "all":
        recipients = [u["telegram_id"] for u in db.list_users(role="user")]
    elif target == "reseller":
        recipients = [u["telegram_id"] for u in db.list_users(role="reseller")]
    else:
        recipients = [state["target_id"]]

    sent, failed = 0, 0
    for rid in recipients:
        try:
            await context.bot.copy_message(chat_id=rid, from_chat_id=update.effective_chat.id,
                                            message_id=update.message.message_id)
            sent += 1
        except Exception:
            failed += 1
    await update.message.reply_text(f"📢 Broadcast sent.\n✅ Sent: {sent}  ❌ Failed: {failed}",
                                     reply_markup=kb.settings_kb())
