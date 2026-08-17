import os
import datetime
import logging

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

import database as db
import keyboards as kb
import common_handlers as ch
from config import ADMIN_IDS, DB_PATH

logger = logging.getLogger("admin_handlers")


def _build_profile_text(tid):
    u = db.get_user(tid)
    stats = db.get_user_stats(tid)
    role_label = "Reseller 🔴" if u["role"] == "reseller" else "User 👤"
    username_display = f"@{u['username']}" if u["username"] else "(not set)"
    name = u["first_name"] or u["username"] or str(tid)
    phone_display = u["phone_number"] or "(not shared)"
    banned_note = "\n\n🚫 <b>Status:</b> Banned" if u["banned"] else ""
    usd_balance = db.inr_to_usd(u["balance"])
    return (
        f"👤 <b>{name}</b>\n\n"
        f"🆔 <b>User ID:</b> <code>{tid}</code>\n\n"
        f"🔖 <b>Username:</b> {username_display}\n\n"
        f"📱 <b>Phone Number:</b> {phone_display}\n\n"
        f"🪪 <b>Role:</b> {role_label}\n\n"
        f"💰 <b>Current Balance:</b> ₹{u['balance']} (${usd_balance})\n\n"
        f"💵 <b>Total Deposited:</b> ₹{stats['total_deposit']}\n\n"
        f"📦 <b>Orders Completed:</b> {stats['completed_orders']}\n\n"
        f"🎁 <b>Earned From Daily Gift:</b> ₹{stats['gift_earned']}"
        f"{banned_note}"
    )


async def _safe_edit_status(q, note):
    try:
        if q.message.caption is not None:
            return await q.edit_message_caption(caption=(q.message.caption or "") + f"\n\n{note}")
        return await q.edit_message_text((q.message.text or "") + f"\n\n{note}", parse_mode="HTML")
    except Exception:
        try:
            return await q.answer(note, show_alert=True)
        except Exception:
            pass


async def hide_reseller_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db.is_admin(update.effective_user.id):
        return
    db.set_reseller_button_enabled(False)
    await update.message.reply_text(
        "✅ The <b>Upgrade to Reseller</b> button is now hidden for all users, and reseller "
        "upgrade payments will no longer be accepted until you run /addresellerbutton again.",
        parse_mode="HTML")


async def add_reseller_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db.is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text(
            "Usage: <code>/addresellerbutton &lt;amount&gt;</code>\nExample: <code>/addresellerbutton 500</code>",
            parse_mode="HTML")
        return
    try:
        fee = float(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Invalid amount. Usage: /addresellerbutton <amount>")
        return
    if fee <= 0:
        await update.message.reply_text("⚠️ Amount must be greater than 0.")
        return
    db.set_reseller_button_enabled(True, fee=fee)
    await update.message.reply_text(
        f"✅ The <b>Upgrade to Reseller</b> button is now visible for all non-reseller users.\n"
        f"💰 <b>Reseller fee:</b> ₹{fee:.0f}",
        parse_mode="HTML")


async def hide_trial_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db.is_admin(update.effective_user.id):
        return
    db.set_trial_button_enabled(False)
    await update.message.reply_text(
        "✅ The <b>Free Trial</b> button is now hidden for all users, and trial claims "
        "will no longer work until you run /addtrail again.",
        parse_mode="HTML")


async def add_trial_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db.is_admin(update.effective_user.id):
        return
    db.set_trial_button_enabled(True)
    await update.message.reply_text(
        "✅ The <b>Free Trial</b> button is now visible for all users, and trial claims are enabled.",
        parse_mode="HTML")


async def premium_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/premium - admin-only. Switches the ENTIRE bot's look to premium:
    coloured buttons + 3D custom-emoji icons (wherever one is saved via
    Customize Buttons) come back on, everywhere in the bot."""
    if not db.is_admin(update.effective_user.id):
        await update.message.reply_text(
            f"🚫 Not authorized.\nYour Telegram ID: <code>{update.effective_user.id}</code>\n"
            f"This ID isn't in config.py's ADMIN_IDS list.", parse_mode="HTML")
        return
    kb.set_theme("premium")
    await update.message.reply_text(
        "✨ <b>Premium look activated!</b>\n\n"
        "🎨 Coloured buttons and 3D emoji icons are now ON across the whole bot.",
        parse_mode="HTML")


async def basic_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/basic - admin-only. Switches the ENTIRE bot's look to basic:
    plain grey buttons, no 3D icons, anywhere in the bot. Nothing saved
    per-button is deleted - /premium instantly brings it all back."""
    if not db.is_admin(update.effective_user.id):
        await update.message.reply_text(
            f"🚫 Not authorized.\nYour Telegram ID: <code>{update.effective_user.id}</code>\n"
            f"This ID isn't in config.py's ADMIN_IDS list.", parse_mode="HTML")
        return
    kb.set_theme("basic")
    await update.message.reply_text(
        "🔘 <b>Basic look activated!</b>\n\n"
        "Buttons are now plain (no colour, no 3D icons) across the whole bot.",
        parse_mode="HTML")


async def maintenance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db.is_admin(update.effective_user.id):
        await update.message.reply_text(
            f"🚫 Not authorized.\nYour Telegram ID: <code>{update.effective_user.id}</code>\n"
            f"This ID isn't in config.py's ADMIN_IDS list.", parse_mode="HTML")
        return

    current = db.is_maintenance_mode()
    arg = context.args[0].lower() if context.args else None

    if arg in ("on", "off"):
        new_state = (arg == "on")
    elif arg is None:
        new_state = not current  # no arg -> toggle
    else:
        await update.message.reply_text(
            "Usage: <code>/maintenance</code> (toggles) or <code>/maintenance on</code> / "
            "<code>/maintenance off</code>", parse_mode="HTML")
        return

    db.set_maintenance_mode(new_state)

    if new_state:
        await update.message.reply_text(
            "🚧 <b>Maintenance mode is now ON</b>\n\n"
            "All users and resellers are locked out of the bot until you turn this off — "
            "they'll get a short \"under maintenance\" message instead. Only admins can use "
            "the bot while this is active.\n\n"
            "Run <code>/maintenance off</code> when you're done making changes.",
            parse_mode="HTML")
    else:
        await update.message.reply_text(
            "✅ <b>Maintenance mode is now OFF</b>\n\n"
            "The bot is open again for all users and resellers.",
            parse_mode="HTML")


async def admin_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db.is_admin(update.effective_user.id):
        if update.message:
            await update.message.reply_text(
                f"🚫 Not authorized.\nYour Telegram ID: <code>{update.effective_user.id}</code>\n"
                f"This ID isn't in config.py's ADMIN_IDS list.",
                parse_mode="HTML")
        return
    total_sales = 0
    with db.get_conn() as conn:
        row = conn.execute("SELECT COALESCE(SUM(price),0) s FROM orders WHERE status='completed'").fetchone()
        total_sales = row["s"]
        users_count = conn.execute("SELECT COUNT(*) c FROM users WHERE role='user'").fetchone()["c"]
        resellers_count = conn.execute("SELECT COUNT(*) c FROM users WHERE role='reseller'").fetchone()["c"]
    now_str = datetime.datetime.now().strftime("%H:%M:%S")
    text = (
        "📊 <b>Admin Dashboard</b>\n\n"
        f"💵 Total Sales: ₹{total_sales}\n"
        f"👤 Users: {users_count}\n"
        f"🔴 Resellers: {resellers_count}\n\n"
        "Use the options below to manage your store 👇\n\n"
        f"<i>🕐 Last refreshed: {now_str}</i>"
    )
    if update.message:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb.admin_main_menu())
    else:
        try:
            await update.callback_query.edit_message_text(text, parse_mode="HTML",
                                                            reply_markup=kb.admin_main_menu())
        except Exception as e:
            if "not modified" not in str(e).lower():
                raise
            await update.callback_query.answer("🔄 Already up to date!")


async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db.is_admin(update.effective_user.id):
        await update.message.reply_text(
            f"🚫 Not authorized.\nYour Telegram ID: <code>{update.effective_user.id}</code>\n"
            f"This ID isn't in config.py's ADMIN_IDS list.", parse_mode="HTML")
        return
    if not os.path.exists(DB_PATH):
        await update.message.reply_text("⚠️ Database file not found on disk — nothing to back up.")
        return
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
    try:
        with open(DB_PATH, "rb") as f:
            await update.message.reply_document(
                document=f, filename=f"shop_bot_backup_{timestamp}.db",
                caption=f"💾 <b>Database Backup</b>\n🕐 {timestamp}\n\n"
                        "⚠️ Keep this file safe — it contains ALL users, orders, deposits, balances "
                        "and stock keys. To restore: stop the bot, replace shop_bot.db with this file "
                        "(rename it back to shop_bot.db), then start the bot again.",
                parse_mode="HTML")
    except Exception as e:
        logger.error("backup_cmd failed: %s", e)
        await update.message.reply_text(f"❌ Backup failed: {e}")


async def promote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db.is_admin(update.effective_user.id):
        await update.message.reply_text(
            f"🚫 Not authorized.\nYour Telegram ID: <code>{update.effective_user.id}</code>\n"
            f"This ID isn't in config.py's ADMIN_IDS list.", parse_mode="HTML")
        return
    if not context.args:
        await update.message.reply_text("Usage: <code>/promote USER_ID</code>", parse_mode="HTML")
        return
    try:
        tid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ That doesn't look like a valid Telegram user ID.")
        return
    u = db.get_user(tid)
    if u and u["role"] == "reseller":
        await update.message.reply_text(f"ℹ️ User <code>{tid}</code> is already a Reseller.", parse_mode="HTML")
        return
    u, was_new = db.set_role_pre_start(tid, "reseller")
    username_display = f"@{u['username']}" if u["username"] else "(no username)"
    note = ("\n\n📥 This person hasn't started the bot yet — as soon as they do, "
            "they'll already see Reseller pricing." if was_new else "")
    await update.message.reply_text(
        f"✅ <b>{username_display}</b> (ID: <code>{tid}</code>) has been promoted to <b>Reseller</b>.\n"
        f"Reseller pricing now applies to them.{note}", parse_mode="HTML")
    try:
        await context.bot.send_message(
            tid, kb.get_header("reseller_upgrade_congrats_message", credit_line=""),
            parse_mode="HTML", reply_markup=kb.back_main_kb())
    except Exception:
        pass


async def demote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db.is_admin(update.effective_user.id):
        await update.message.reply_text(
            f"🚫 Not authorized.\nYour Telegram ID: <code>{update.effective_user.id}</code>\n"
            f"This ID isn't in config.py's ADMIN_IDS list.", parse_mode="HTML")
        return
    if not context.args:
        await update.message.reply_text("Usage: <code>/demote USER_ID</code>", parse_mode="HTML")
        return
    try:
        tid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ That doesn't look like a valid Telegram user ID.")
        return
    u = db.get_user(tid)
    if not u:
        await update.message.reply_text(f"⚠️ No user found with ID <code>{tid}</code>.", parse_mode="HTML")
        return
    if u["role"] == "user":
        await update.message.reply_text(f"ℹ️ User <code>{tid}</code> is already a regular User.", parse_mode="HTML")
        return
    db.set_role(tid, "user")
    username_display = f"@{u['username']}" if u["username"] else "(no username)"
    await update.message.reply_text(
        f"✅ <b>{username_display}</b> (ID: <code>{tid}</code>) has been demoted to <b>User</b>.\n"
        f"Regular user pricing now applies to them.", parse_mode="HTML")
    try:
        await context.bot.send_message(
            tid, "ℹ️ Your account has been moved back to a regular <b>User</b>. Reseller pricing no "
                 "longer applies.", parse_mode="HTML")
    except Exception:
        pass


async def stock_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db.is_admin(update.effective_user.id):
        await update.message.reply_text(
            f"🚫 Not authorized.\nYour Telegram ID: <code>{update.effective_user.id}</code>\n"
            f"This ID isn't in config.py's ADMIN_IDS list.",
            parse_mode="HTML")
        return

    categories = db.list_categories()
    if not categories:
        await update.message.reply_text("📦 No categories found yet.")
        return

    blocks = []
    for cat in categories:
        lines = [f"🗂️ <b>{cat['name']}</b>"]
        products = db.list_products(cat["id"])  # role=None -> admin sees everything
        if not products:
            lines.append("   <i>(no products)</i>")
        for p in products:
            lines.append(f"\n   📦 <b>{p['name']}</b>")
            durations = db.list_durations(p["id"])
            if not durations:
                lines.append("      <i>(no durations)</i>")
            for d in durations:
                stock = db.count_available_keys(d["id"])
                stock_icon = "✅" if stock > 0 else "🚫"
                lines.append(f"      {stock_icon} {d['label']}: <b>{stock}</b> in stock")
        blocks.append("\n".join(lines))

    header = "📊 <b>FULL STOCK REPORT</b> 📊\n"
    full_text = header + "\n\n" + "\n\n".join(blocks)

    # Telegram messages cap at 4096 chars — split into safe chunks if needed.
    chunk, chunks = "", []
    for block in full_text.split("\n\n"):
        candidate = f"{chunk}\n\n{block}" if chunk else block
        if len(candidate) > 3800:
            chunks.append(chunk)
            chunk = block
        else:
            chunk = candidate
    if chunk:
        chunks.append(chunk)

    for c in chunks:
        await update.message.reply_text(c, parse_mode="HTML")


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not db.is_admin(update.effective_user.id):
        await q.answer("Not authorized.", show_alert=True)
        return
    await q.answer()
    data = q.data

    # ---------- main nav ----------
    if data == "adm_back_main":
        return await admin_entry(update, context)

    if data == "adm_refresh_sales":
        return await admin_entry(update, context)

    # ---------- USERS ----------
    if data == "adm_users":
        users = db.list_users(role="user")
        if not users:
            return await q.edit_message_text("No users found.", reply_markup=kb.back_btn("adm_back_main"))
        return await q.edit_message_text("👤 <b>Users</b>\n\nSelect a user:", parse_mode="HTML",
                                          reply_markup=kb.user_list_kb(users))

    if data.startswith("adm_u_"):
        tid = int(data.split("_")[-1])
        text = _build_profile_text(tid)
        return await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb.user_detail_kb(tid))

    # ---------- ADMINS ----------
    if data == "adm_admin_list":
        blocks = ["👑 <b>Admins</b>\n"]
        for aid in ADMIN_IDS:
            u = db.get_user(aid)
            if u:
                username_display = f"@{u['username']}" if u["username"] else "(no username)"
                mobile_display = u.get("phone_number") or "Not shared"
                blocks.append(
                    f"👤 <b>Username:</b> {username_display}\n"
                    f"🆔 <b>User ID:</b> {aid}\n"
                    f"📱 <b>Mobile Number:</b> {mobile_display}\n"
                    f"💰 <b>Balance:</b> ₹{u['balance']}"
                )
            else:
                blocks.append(
                    f"👤 <b>Username:</b> (never started the bot)\n"
                    f"🆔 <b>User ID:</b> {aid}\n"
                    f"📱 <b>Mobile Number:</b> Not shared\n"
                    f"💰 <b>Balance:</b> ₹0"
                )
        text = "\n\n".join(blocks)
        return await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb.back_btn("adm_back_main"))

    if data.startswith("adm_promote_"):
        tid = int(data.split("_")[-1])
        db.set_role(tid, "reseller")
        await q.answer("Promoted to Reseller ✅", show_alert=True)
        users = db.list_users(role="user")
        return await q.edit_message_text("👤 <b>Users</b>", parse_mode="HTML", reply_markup=kb.user_list_kb(users))

    if data.startswith("adm_ban_"):
        tid = int(data.split("_")[-1])
        db.ban_user(tid)
        await q.answer("User banned 🚫", show_alert=True)
        users = db.list_users(role="user")
        return await q.edit_message_text("👤 <b>Users</b>", parse_mode="HTML", reply_markup=kb.user_list_kb(users))

    # ---------- BANNED USERS ----------
    if data == "adm_banned":
        banned = db.list_banned_users()
        if not banned:
            return await q.edit_message_text("✅ No banned users.", reply_markup=kb.back_btn("adm_back_main"))
        return await q.edit_message_text("🚫 <b>Banned Users</b>\n\nSelect a user to unban:", parse_mode="HTML",
                                          reply_markup=kb.banned_user_list_kb(banned))

    if data.startswith("adm_bu_"):
        tid = int(data.split("_")[-1])
        text = _build_profile_text(tid)
        return await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb.banned_user_detail_kb(tid))

    if data.startswith("adm_unban_"):
        tid = int(data.split("_")[-1])
        db.unban_user(tid)
        await q.answer("User unbanned ✅", show_alert=True)
        banned = db.list_banned_users()
        if not banned:
            return await q.edit_message_text("✅ No banned users.", reply_markup=kb.back_btn("adm_back_main"))
        return await q.edit_message_text("🚫 <b>Banned Users</b>\n\nSelect a user to unban:", parse_mode="HTML",
                                          reply_markup=kb.banned_user_list_kb(banned))

    # ---------- RESELLERS ----------
    if data == "adm_resellers":
        resellers = db.list_users(role="reseller")
        if not resellers:
            return await q.edit_message_text("No resellers found.", reply_markup=kb.back_btn("adm_back_main"))
        return await q.edit_message_text("🔴 <b>Resellers</b>", parse_mode="HTML",
                                          reply_markup=kb.reseller_list_kb(resellers))

    if data.startswith("adm_r_"):
        tid = int(data.split("_")[-1])
        text = _build_profile_text(tid)
        return await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb.reseller_detail_kb(tid))

    if data.startswith("adm_demote_"):
        tid = int(data.split("_")[-1])
        db.set_role(tid, "user")
        await q.answer("Demoted to User ✅", show_alert=True)
        resellers = db.list_users(role="reseller")
        return await q.edit_message_text("🔴 <b>Resellers</b>", parse_mode="HTML",
                                          reply_markup=kb.reseller_list_kb(resellers))

    # ---------- PRODUCTS ----------
    if data == "adm_products":
        cats = db.list_categories()
        return await q.edit_message_text("🟢 <b>Manage Products</b>\n\nChoose a category:", parse_mode="HTML",
                                          reply_markup=kb.categories_kb(cats))

    if data.startswith("adm_cat_"):
        cat_id = int(data.split("_")[-1])
        products = db.list_products(cat_id)
        cat = db.get_category(cat_id)
        return await q.edit_message_text(f"📦 <b>{cat['name']}</b>\n\nProducts:", parse_mode="HTML",
                                          reply_markup=kb.products_kb(products, cat_id))

    if data == "adm_addcat":
        context.user_data["state"] = {"action": "await_add_category"}
        return await q.edit_message_text("✏️ Send the new category name:", reply_markup=kb.back_btn("adm_products"))

    if data.startswith("adm_renamecat_"):
        cat_id = int(data.split("_")[-1])
        cat = db.get_category(cat_id)
        context.user_data["state"] = {"action": "await_rename_category", "cat_id": cat_id}
        return await q.edit_message_text(
            f"✏️ Current category name: <b>{cat['name']}</b>\n\nSend the new name:",
            parse_mode="HTML", reply_markup=kb.back_btn(f"adm_cat_{cat_id}"))

    if data.startswith("adm_delcat_"):
        cat_id = int(data.split("_")[-1])
        cat = db.get_category(cat_id)
        products = db.list_products(cat_id)
        return await q.edit_message_text(
            f"⚠️ <b>Are you sure?</b>\n\nThis will permanently delete <b>{cat['name']}</b> — "
            f"including ALL {len(products)} product(s) inside it, their durations, and any unsold stock keys.\n\n"
            "🚫 This cannot be undone.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [kb.btn("✅ Yes, Delete It", callback_data=f"adm_delcatgo_{cat_id}", style="danger"),
                 kb.btn("❌ Cancel", callback_data=f"adm_cat_{cat_id}", style="primary")],
            ]))

    if data.startswith("adm_delcatgo_"):
        cat_id = int(data.split("_")[-1])
        db.delete_category(cat_id)
        await q.answer("Category deleted 🗑", show_alert=True)
        cats = db.list_categories()
        return await q.edit_message_text("🟢 <b>Manage Products</b>\n\nChoose a category:", parse_mode="HTML",
                                          reply_markup=kb.categories_kb(cats))

    if data.startswith("adm_addprod_"):
        cat_id = int(data.split("_")[-1])
        context.user_data["state"] = {"action": "await_add_product", "cat_id": cat_id}
        return await q.edit_message_text("✏️ Send the product name:", reply_markup=kb.back_btn(f"adm_cat_{cat_id}"))

    if data in ("adm_prodvis_all", "adm_prodvis_reseller"):
        pending = context.user_data.get("state", {})
        if pending.get("action") != "await_add_product_visibility":
            return
        visibility = "all" if data == "adm_prodvis_all" else "reseller_only"
        cat_id = pending["cat_id"]
        name = pending["name"]
        db.add_product(cat_id, name, visibility)
        context.user_data.pop("state", None)
        vis_label = "All Users" if visibility == "all" else "Reseller Only 🔴"
        products = db.list_products(cat_id)
        cat = db.get_category(cat_id)
        return await q.edit_message_text(
            f"✅ Product '{name}' added ({vis_label}).\n\n📦 <b>{cat['name']}</b>",
            parse_mode="HTML", reply_markup=kb.products_kb(products, cat_id))

    if data.startswith("adm_prod_"):
        product_id = int(data.split("_")[-1])
        p = db.get_product(product_id)
        durations = db.list_durations(product_id)
        return await q.edit_message_text(f"📦 <b>{p['name']}</b>\n\nDurations:", parse_mode="HTML",
                                          reply_markup=kb.durations_kb(durations, product_id, p["category_id"]))

    if data.startswith("adm_renameprod_"):
        product_id = int(data.split("_")[-1])
        p = db.get_product(product_id)
        context.user_data["state"] = {"action": "await_rename_product", "product_id": product_id}
        return await q.edit_message_text(
            f"✏️ Current product name: <b>{p['name']}</b>\n\nSend the new name:",
            parse_mode="HTML", reply_markup=kb.back_btn(f"adm_prod_{product_id}"))

    if data.startswith("adm_adddur_"):
        product_id = int(data.split("_")[-1])
        context.user_data["state"] = {"action": "await_add_duration", "product_id": product_id}
        return await q.edit_message_text(
            "✏️ Send the duration label (e.g. 7 Days / 30 Days):",
            reply_markup=kb.back_btn(f"adm_prod_{product_id}"))

    if data.startswith("adm_sharelink_"):
        product_id = int(data.split("_")[-1])
        p = db.get_product(product_id)
        bot_user = await context.bot.get_me()
        link = f"https://t.me/{bot_user.username}?start=prod_{product_id}"
        await q.answer()
        await context.bot.send_message(
            update.effective_chat.id,
            f"🔗 Shareable link for <b>{p['name']}</b>:\n\n{link}\n\n"
            "Anyone who opens this link will land directly on this product's plans "
            "(after phone verification if they're new).",
            parse_mode="HTML")
        return

    if data.startswith("adm_delprod_"):
        _, _, product_id, cat_id = data.split("_")
        p = db.get_product(int(product_id))
        return await q.edit_message_text(
            f"⚠️ <b>Are you sure?</b>\n\nThis will permanently delete <b>{p['name']}</b> — "
            f"including ALL its durations and any unsold stock keys.\n\n🚫 This cannot be undone.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [kb.btn("✅ Yes, Delete It", callback_data=f"adm_delprodgo_{product_id}_{cat_id}", style="danger"),
                 kb.btn("❌ Cancel", callback_data=f"adm_cat_{cat_id}", style="primary")],
            ]))

    if data.startswith("adm_delprodgo_"):
        _, _, product_id, cat_id = data.split("_")
        db.delete_product(int(product_id))
        await q.answer("Product deleted 🗑", show_alert=True)
        products = db.list_products(int(cat_id))
        cat = db.get_category(int(cat_id))
        return await q.edit_message_text(f"📦 <b>{cat['name']}</b>", parse_mode="HTML",
                                          reply_markup=kb.products_kb(products, int(cat_id)))

    if data.startswith("adm_dur_"):
        duration_id = int(data.split("_")[-1])
        d = db.get_duration(duration_id)
        avail = db.count_available_keys(duration_id)
        text = f"⏳ <b>{d['label']}</b>\n🔑 Available stock: {avail}"
        return await q.edit_message_text(text, parse_mode="HTML",
                                          reply_markup=kb.duration_detail_kb(duration_id, d["product_id"]))

    if data.startswith("adm_renamedur_"):
        duration_id = int(data.split("_")[-1])
        d = db.get_duration(duration_id)
        context.user_data["state"] = {"action": "await_rename_duration", "duration_id": duration_id}
        return await q.edit_message_text(
            f"✏️ Current duration label: <b>{d['label']}</b>\n\nSend the new label:",
            parse_mode="HTML", reply_markup=kb.back_btn(f"adm_dur_{duration_id}"))

    if data.startswith("adm_deldur_"):
        _, _, duration_id, product_id = data.split("_")
        d = db.get_duration(int(duration_id))
        avail = db.count_available_keys(int(duration_id))
        return await q.edit_message_text(
            f"⚠️ <b>Are you sure?</b>\n\nThis will permanently delete the <b>{d['label']}</b> duration"
            f"{f' (and its {avail} unsold stock keys)' if avail else ''}.\n\n🚫 This cannot be undone.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [kb.btn("✅ Yes, Delete It", callback_data=f"adm_deldurgo_{duration_id}_{product_id}",
                        style="danger"),
                 kb.btn("❌ Cancel", callback_data=f"adm_dur_{duration_id}", style="primary")],
            ]))

    if data.startswith("adm_deldurgo_"):
        _, _, duration_id, product_id = data.split("_")
        db.delete_duration(int(duration_id))
        await q.answer("Duration deleted 🗑", show_alert=True)
        durations = db.list_durations(int(product_id))
        p = db.get_product(int(product_id))
        return await q.edit_message_text(f"📦 <b>{p['name']}</b>", parse_mode="HTML",
                                          reply_markup=kb.durations_kb(durations, int(product_id), p["category_id"]))

    if data.startswith("adm_stock_"):
        duration_id = int(data.split("_")[-1])
        context.user_data["state"] = {"action": "await_stock_key", "duration_id": duration_id}
        return await q.edit_message_text(
            "🔑 Send the key(s). For multiple keys, put each one on a new line:",
            reply_markup=kb.back_btn(f"adm_dur_{duration_id}"))

    if data.startswith("adm_setprice_"):
        duration_id = int(data.split("_")[-1])
        return await q.edit_message_text("💰 Who should this price apply to?",
                                          reply_markup=kb.price_scope_kb(duration_id))

    if data.startswith("adm_price_all_"):
        duration_id = int(data.split("_")[-1])
        context.user_data["state"] = {"action": "await_price_all", "duration_id": duration_id}
        return await q.edit_message_text("✏️ Send the price for All Users (numeric):",
                                          reply_markup=kb.back_btn(f"adm_dur_{duration_id}"))

    if data.startswith("adm_price_reseller_"):
        duration_id = int(data.split("_")[-1])
        context.user_data["state"] = {"action": "await_price_reseller", "duration_id": duration_id}
        return await q.edit_message_text("✏️ Send the price for Resellers (numeric):",
                                          reply_markup=kb.back_btn(f"adm_dur_{duration_id}"))

    if data.startswith("adm_price_user_"):
        duration_id = int(data.split("_")[-1])
        context.user_data["state"] = {"action": "await_price_user_id", "duration_id": duration_id}
        return await q.edit_message_text("🎯 Send that user's numeric Telegram ID:",
                                          reply_markup=kb.back_btn(f"adm_dur_{duration_id}"))

    # ---------- TRIAL ----------
    if data == "adm_trial":
        trial_products = db.list_trial_products()
        text = "🎁 <b>Manage Trial</b>\n\nThese are the products users can claim for free from the Free Trial button."
        if not trial_products:
            text += "\n\n⚠️ No trial products yet — add one below."
        return await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb.admin_trial_menu_kb(trial_products))

    if data == "adm_addtrial":
        context.user_data["state"] = {"action": "await_add_trial_product"}
        return await q.edit_message_text("✏️ Send the trial product name:", reply_markup=kb.back_btn("adm_trial"))

    if data.startswith("adm_trialprod_"):
        trial_product_id = int(data.split("_")[-1])
        tp = db.get_trial_product(trial_product_id)
        avail = db.count_available_trial_keys(trial_product_id)
        link_line = f"\n🔗 Link: {tp['link']}" if tp.get("link") else "\n🔗 Link: (not set — using auto-generated key link)"
        text = f"🎁 <b>{tp['name']}</b>\n🔑 Available trial stock: {avail}{link_line}"
        return await q.edit_message_text(text, parse_mode="HTML",
                                          reply_markup=kb.admin_trial_product_kb(trial_product_id))

    if data.startswith("adm_renametrial_"):
        trial_product_id = int(data.split("_")[-1])
        tp = db.get_trial_product(trial_product_id)
        context.user_data["state"] = {"action": "await_rename_trial_product", "trial_product_id": trial_product_id}
        return await q.edit_message_text(
            f"✏️ Current name: <b>{tp['name']}</b>\n\nSend the new name:",
            parse_mode="HTML", reply_markup=kb.back_btn(f"adm_trialprod_{trial_product_id}"))

    if data.startswith("adm_settriallink_"):
        trial_product_id = int(data.split("_")[-1])
        tp = db.get_trial_product(trial_product_id)
        context.user_data["state"] = {"action": "await_set_trial_link", "trial_product_id": trial_product_id}
        current = f"\n\nCurrent link: {tp['link']}" if tp.get("link") else ""
        return await q.edit_message_text(
            "🔗 Send the link users should get when they claim this trial "
            "(e.g. your own page/channel where the key is shown).\n\n"
            "Send <code>clear</code> to remove it and go back to the bot's auto-generated key link."
            f"{current}",
            parse_mode="HTML", reply_markup=kb.back_btn(f"adm_trialprod_{trial_product_id}"))

    if data.startswith("adm_addtrialkeys_"):
        trial_product_id = int(data.split("_")[-1])
        context.user_data["state"] = {"action": "await_add_trial_keys", "trial_product_id": trial_product_id}
        return await q.edit_message_text(
            "🔑 Send the trial key(s). For multiple keys, put each one on a new line:",
            reply_markup=kb.back_btn(f"adm_trialprod_{trial_product_id}"))

    if data.startswith("adm_deltrialgo_"):
        trial_product_id = int(data.split("_")[-1])
        db.delete_trial_product(trial_product_id)
        await q.answer("Trial product deleted 🗑", show_alert=True)
        trial_products = db.list_trial_products()
        return await q.edit_message_text("🎁 <b>Manage Trial</b>", parse_mode="HTML",
                                          reply_markup=kb.admin_trial_menu_kb(trial_products))

    if data.startswith("adm_deltrial_"):
        trial_product_id = int(data.split("_")[-1])
        tp = db.get_trial_product(trial_product_id)
        return await q.edit_message_text(
            f"⚠️ <b>Are you sure?</b>\n\nThis will permanently delete <b>{tp['name']}</b> from the trial "
            f"section — including any unclaimed trial keys.\n\n🚫 This cannot be undone.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [kb.btn("✅ Yes, Delete It", callback_data=f"adm_deltrialgo_{trial_product_id}", style="danger"),
                 kb.btn("❌ Cancel", callback_data=f"adm_trialprod_{trial_product_id}", style="primary")],
            ]))

    # ---------- MANAGE BALANCE ----------
    if data == "adm_balance":
        return await q.edit_message_text(
            "💵 <b>Manage Balance</b>\n\nWhat would you like to do?", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [kb.btn("🔍 Manage a Specific User", callback_data="adm_balance_specific", style="primary")],
                [kb.btn("♻️ Reset ALL Balances", callback_data="adm_balance_reset_confirm", style="danger")],
                [kb.back_button("adm_back_main")],
            ]))

    if data == "adm_balance_specific":
        context.user_data["state"] = {"action": "await_balance_user_id"}
        return await q.edit_message_text(
            "🎯 Send the numeric Telegram ID of the user whose balance you want to manage:",
            reply_markup=kb.back_btn("adm_balance"))

    if data == "adm_balance_reset_confirm":
        with db.get_conn() as conn:
            row = conn.execute("SELECT COUNT(*) c, COALESCE(SUM(balance),0) s FROM users "
                                "WHERE balance != 0").fetchone()
        return await q.edit_message_text(
            f"⚠️ <b>Are you sure?</b>\n\n"
            f"This will reset <b>{row['c']} users'</b> wallet balance to ₹0 "
            f"(total ₹{row['s']:.2f} being wiped).\n\n"
            f"🚫 <b>This cannot be undone.</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [kb.btn("✅ Yes, Reset All", callback_data="adm_balance_reset_do", style="danger"),
                 kb.btn("❌ Cancel", callback_data="adm_balance", style="primary")],
            ]))

    if data == "adm_balance_reset_do":
        count, total = db.reset_all_balances()
        await q.answer("All balances reset ✅", show_alert=True)
        return await q.edit_message_text(
            f"✅ Done — <b>{count} users'</b> balances (totaling ₹{total:.2f}) have been reset to ₹0.",
            parse_mode="HTML", reply_markup=kb.back_btn("adm_back_main"))

    if data == "adm_pending":
        orders = db.list_pending_orders()
        deposits = db.list_pending_deposits()
        if not orders and not deposits:
            return await q.edit_message_text("✅ No pending payments.",
                                              reply_markup=kb.back_btn("adm_back_main"))
        await q.edit_message_text(f"💳 <b>Pending Payments</b>\nOrders: {len(orders)} | Deposits: {len(deposits)}",
                                   parse_mode="HTML", reply_markup=kb.back_btn("adm_back_main"))
        for o in orders:
            u = db.get_user(o["telegram_id"])
            d = db.get_duration(o["duration_id"])
            p = db.get_product(d["product_id"])
            cat = db.get_category(p["category_id"])
            username_display = f"@{u['username']}" if u["username"] else "(no username)"
            cap = (
                "🚨 <b>NEW SHOP ORDER RECEIVED</b> 🚨\n\n"
                f"🧾 <b>Order ID:</b> #{o['id']}\n"
                f"👤 <b>Customer:</b> {username_display} (ID: {o['telegram_id']})\n"
                f"🔷 <b>Category:</b> {cat['name']}\n"
                f"🔷 <b>Product:</b> {p['name']}\n"
                f"🔷 <b>License:</b> {d['label']}\n"
                f"💰 <b>Amount Paid:</b> ₹{o['price']}\n\n"
                "👇 Select an action below to review this transaction:"
            )
            if o["screenshot_file_id"]:
                await context.bot.send_photo(update.effective_chat.id, o["screenshot_file_id"], caption=cap,
                                              parse_mode="HTML", reply_markup=kb.order_review_kb(o["id"]))
            else:
                await context.bot.send_message(update.effective_chat.id, cap, parse_mode="HTML",
                                                reply_markup=kb.order_review_kb(o["id"]))
        for dep in deposits:
            u = db.get_user(dep["telegram_id"])
            username_display = f"@{u['username']}" if u["username"] else "(no username)"
            header = ("🚨 <b>NEW RESELLER UPGRADE FEE RECEIVED</b> 🚨" if dep.get("purpose") == "reseller_upgrade"
                      else "🚨 <b>NEW DEPOSIT RECEIVED</b> 🚨")
            cap = (
                f"{header}\n\n"
                f"🧾 <b>Deposit ID:</b> #{dep['id']}\n"
                f"👤 <b>Customer:</b> {username_display} (ID: {dep['telegram_id']})\n"
                f"💰 <b>Amount:</b> ₹{dep['amount']}\n\n"
                "👇 Select an action below to review this transaction:"
            )
            if dep["screenshot_file_id"]:
                await context.bot.send_photo(update.effective_chat.id, dep["screenshot_file_id"], caption=cap,
                                              parse_mode="HTML", reply_markup=kb.deposit_review_kb(dep["id"]))
            else:
                await context.bot.send_message(update.effective_chat.id, cap, parse_mode="HTML",
                                                reply_markup=kb.deposit_review_kb(dep["id"]))
        return

    if data.startswith("adm_vorder_") or data.startswith("adm_rorder_"):
        verify = data.startswith("adm_vorder_")
        order_id = int(data.split("_")[-1])
        o = db.get_order(order_id)
        if not o or o["status"] != "review":
            return await _safe_edit_status(q, "⚠️ This order has already been processed.")
        if verify:
            duration = db.get_duration(o["duration_id"])
            product = db.get_product(o["product_id"])
            key = db.pop_key(o["duration_id"], o["telegram_id"])
            db.set_order_status(order_id, "completed")
            db.credit_referral_commission(o["telegram_id"], o["price"], f"product order #{order_id}")
            if key:
                db.set_order_delivered_key(order_id, key)
                if o.get("coupon_code"):
                    db.record_coupon_usage(o["coupon_code"], o["telegram_id"])
                verified_note = f"✅ VERIFIED\n🔑 Key Delivered: {key}"
                try:
                    _method_labels = {
                        "binance": kb.get_header('method_label_binance'),
                        "bkash": kb.get_header('method_label_bkash'),
                        "nagad": kb.get_header('method_label_nagad'),
                    }
                    method_label = _method_labels.get(o["method"], kb.get_header('method_label_upi'))
                    await context.bot.send_message(
                        o["telegram_id"],
                        kb.get_header("key_delivered_message", order_id=order_id, product_name=product['name'],
                                      duration_label=duration['label'], price=f"{o['price']:.2f}", key=key,
                                      payment_mode=f"{method_label} · Admin Verified"),
                        parse_mode="HTML")
                except Exception:
                    try:
                        await context.bot.send_message(
                            o["telegram_id"],
                            f"🎉 YOUR PAYMENT HAS BEEN APPROVED! 🎉\n\n"
                            f"🧾 Order ID: #{order_id}\n📦 Product: {product['name']} - {duration['label']}\n"
                            f"💰 Price: ₹{o['price']:.2f}\n\n🔑 Your Digital Item/License Code:\nKey: {key}\n\n"
                            f"Thank you for shopping with us! Have a great day.")
                    except Exception as e2:
                        await _safe_edit_status(
                            q, f"⚠️ Verified & key delivered in DB, but couldn't message the customer ({e2}). "
                               f"They may have blocked the bot — key: {key}")
                        return
                mode = "Binance (Admin Verified)" if o["method"] == "binance" else "UPI (Admin Verified)"
                await ch.notify_admins_order_completed(context, order_id, mode, key)
            else:
                verified_note = "✅ VERIFIED"
                try:
                    await context.bot.send_message(
                        o["telegram_id"], kb.get_header("stock_out_message"), parse_mode="HTML",
                        reply_markup=kb.stock_out_kb())
                except Exception:
                    try:
                        await context.bot.send_message(
                            o["telegram_id"],
                            "✅ Payment verified, but stock has run out. Please contact the admin.",
                            reply_markup=kb.stock_out_kb())
                    except Exception as e2:
                        await _safe_edit_status(q, f"⚠️ Verified in DB, but couldn't message the customer ({e2}).")
                        return
                mode = "Binance (Admin Verified)" if o["method"] == "binance" else "UPI (Admin Verified)"
                await ch.notify_admins_order_completed(context, order_id, mode, None)
            await _safe_edit_status(q, verified_note)
        else:
            context.user_data["state"] = {"action": "await_reject_reason_order", "order_id": order_id}
            return await q.message.reply_text(
                "✏️ Please type the reason for declining this order (this will be shown to the customer):")
        return

    if data.startswith("adm_vdep_") or data.startswith("adm_rdep_"):
        verify = data.startswith("adm_vdep_")
        dep_id = int(data.split("_")[-1])
        dep = db.get_deposit(dep_id)
        if not dep or dep["status"] != "review":
            return await _safe_edit_status(q, "⚠️ This deposit has already been processed.")
        if verify:
            if dep.get("purpose") == "reseller_upgrade":
                db.set_deposit_status(dep_id, "completed")
                mode = "Binance (Admin Verified)" if dep["method"] == "binance" else "UPI (Admin Verified)"
                await ch.complete_reseller_upgrade(context, dep_id, mode)
                await _safe_edit_status(q, "✅ VERIFIED — Reseller Upgraded")
            else:
                previous_balance = db.get_user(dep["telegram_id"])["balance"]
                db.set_deposit_status(dep_id, "completed")
                db.adjust_balance(dep["telegram_id"], dep["amount"], "deposit", f"Deposit #{dep_id} approved")
                db.set_deposit_balances(dep_id, previous_balance, previous_balance + dep["amount"])
                db.credit_referral_commission(dep["telegram_id"], dep["amount"], f"deposit #{dep_id}")
                try:
                    await context.bot.send_message(
                        dep["telegram_id"],
                        kb.get_header("deposit_confirmed_message", amount=dep["amount"],
                                      previous_balance=previous_balance,
                                      new_balance=previous_balance + dep["amount"]),
                        parse_mode="HTML")
                except Exception as e:
                    await _safe_edit_status(q, f"⚠️ Verified & balance updated in DB, but couldn't message the "
                                                f"customer ({e}).")
                    return
                mode = "Binance (Admin Verified)" if dep["method"] == "binance" else "UPI (Admin Verified)"
                await ch.notify_admins_deposit_completed(context, dep_id, mode)
                await _safe_edit_status(q, "✅ VERIFIED")
        else:
            context.user_data["state"] = {"action": "await_reject_reason_deposit", "deposit_id": dep_id}
            return await q.message.reply_text(
                "✏️ Please type the reason for declining this deposit (this will be shown to the customer):")
        return

    # ---------- SETTINGS ----------
    if data == "adm_settings":
        text = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "⚙️ <b>SHOP SETTINGS</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Use the options below to configure your shop:"
        )
        return await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb.settings_kb())

    if data == "adm_setwelcome":
        context.user_data["state"] = {"action": "await_welcome"}
        current = db.get_setting("welcome_message", "")
        return await q.edit_message_text(
            f"📄 Current welcome message:\n\n{current}\n\n"
            "━━━━━━━━━━━━━━\n"
            "✏️ Send the new welcome message.\nUse {shop_name} and {name} as placeholders.",
            reply_markup=kb.back_btn("adm_settings"))

    if data == "adm_setshopname":
        context.user_data["state"] = {"action": "await_shopname"}
        current = db.get_setting("shop_name", "")
        return await q.edit_message_text(f"🏪 Current shop name: {current}\n\n✏️ Send the new shop name:",
                                          reply_markup=kb.back_btn("adm_settings"))

    if data == "adm_setupi":
        context.user_data["state"] = {"action": "await_upi_id"}
        current = db.get_setting("upi_id", "(not set)")
        return await q.edit_message_text(
            f"💳 Current UPI ID: {current or '(not set)'}\n\n"
            "✏️ Send your UPI ID (e.g. yourname@okhdfcbank):",
            reply_markup=kb.back_btn("adm_settings"))

    if data == "adm_setpayee":
        context.user_data["state"] = {"action": "await_payee_name"}
        current = db.get_setting("payee_name", "")
        return await q.edit_message_text(
            f"🏷 Current payee name: {current}\n\n✏️ Send the new payee/shop name to display when the QR is scanned:",
            reply_markup=kb.back_btn("adm_settings"))

    if data == "adm_sethowto":
        context.user_data["state"] = {"action": "await_howto_link"}
        current = db.get_setting("how_to_use_link", "")
        return await q.edit_message_text(
            f"🎥 Current How To Use link: {current}\n\n"
            "✏️ Send the new link (YouTube/Telegram, any URL):",
            reply_markup=kb.back_btn("adm_settings"))

    if data == "adm_setfiles":
        context.user_data["state"] = {"action": "await_files_link"}
        current = db.get_setting("updated_file_group_link", "")
        return await q.edit_message_text(
            f"📂 Current Updated File link: {current}\n\n"
            "✏️ Send the new group/channel link (e.g. https://t.me/yourgroup):",
            reply_markup=kb.back_btn("adm_settings"))

    if data == "adm_setpayproof":
        context.user_data["state"] = {"action": "await_payproof_link"}
        current = db.get_setting("pay_proof_group_link", "")
        return await q.edit_message_text(
            f"📩 Current Pay Proof group link: {current}\n\n"
            "✏️ Send the new Telegram group link (e.g. https://t.me/yourgroup):",
            reply_markup=kb.back_btn("adm_settings"))

    if data == "adm_setusdrate":
        context.user_data["state"] = {"action": "await_usd_rate"}
        current = db.get_setting("usd_rate", "90")
        return await q.edit_message_text(
            f"💱 Current rate: ₹{current} = $1\n\n"
            "✏️ Send how many INR equal $1 (numeric, e.g. 90):",
            reply_markup=kb.back_btn("adm_settings"))

    if data == "adm_setbdtrate":
        context.user_data["state"] = {"action": "await_bdt_rate"}
        current = db.get_setting("bdt_rate", "115")
        return await q.edit_message_text(
            f"💱 Current rate: ৳{current} = $1\n\n"
            "✏️ Send how many BDT equal $1 (numeric, e.g. 115):",
            reply_markup=kb.back_btn("adm_settings"))

    if data == "adm_setbkash":
        context.user_data["state"] = {"action": "await_bkash_number"}
        current = db.get_setting("bkash_number", "")
        return await q.edit_message_text(
            f"📱 Current bKash Number: {current or '(not set)'}\n\n"
            "✏️ Send your bKash number (e.g. 01712345678):",
            reply_markup=kb.back_btn("adm_settings"))

    if data == "adm_setnagad":
        context.user_data["state"] = {"action": "await_nagad_number"}
        current = db.get_setting("nagad_number", "")
        return await q.edit_message_text(
            f"📱 Current Nagad Number: {current or '(not set)'}\n\n"
            "✏️ Send your Nagad number (e.g. 01712345678):",
            reply_markup=kb.back_btn("adm_settings"))

    if data == "adm_setbinpayid":
        context.user_data["state"] = {"action": "await_binance_pay_id"}
        current = db.get_setting("binance_pay_id", "")
        return await q.edit_message_text(
            f"🟡 Current Binance Pay ID: {current or '(not set)'}\n\n"
            "✏️ Send your Binance Pay ID (from Binance app → Pay → Receive):",
            reply_markup=kb.back_btn("adm_settings"))

    if data == "adm_setbinkey":
        context.user_data["state"] = {"action": "await_binance_api_key"}
        current = db.get_setting("binance_api_key", "")
        masked = (current[:4] + "..." + current[-4:]) if len(current) > 8 else current
        return await q.edit_message_text(
            f"🔑 Current API Key: {masked or '(not set)'}\n\n"
            "✏️ Send your Binance API Key:\n\n"
            "<i>⚠️ This must be a REGULAR account API key from binance.com → Profile → API "
            "Management (\"Enable Reading\" permission is enough) — NOT the Merchant Pay key "
            "from merchant.binance.com. Auto-verify checks your account's incoming Pay "
            "transaction history, which regular account keys have access to.</i>",
            parse_mode="HTML", reply_markup=kb.back_btn("adm_settings"))

    if data == "adm_setbinsecret":
        context.user_data["state"] = {"action": "await_binance_api_secret"}
        current = db.get_setting("binance_api_secret", "")
        masked = (current[:4] + "..." + current[-4:]) if len(current) > 8 else current
        return await q.edit_message_text(
            f"🔒 Current API Secret: {masked or '(not set)'}\n\n"
            "✏️ Send the matching Secret Key for the same regular account API key:",
            reply_markup=kb.back_btn("adm_settings"))

    if data == "adm_setfampaykey":
        context.user_data["state"] = {"action": "await_fampay_api_key"}
        current = db.get_setting("fampay_api_key", "")
        masked = (current[:4] + "..." + current[-4:]) if len(current) > 8 else (current or "(not set)")
        return await q.edit_message_text(
            f"🧾 Current FamPay API Key: {masked}\n\n"
            "✏️ Send your FamPay (rubelislam.store) API key. This powers auto-verified "
            "UPI deposits — no more manual screenshot checking.",
            reply_markup=kb.back_btn("adm_settings"))

    if data == "adm_setearnlinkskey":
        context.user_data["state"] = {"action": "await_earnlinks_api_key"}
        current = db.get_setting("earnlinks_api_token", "")
        masked = (current[:4] + "..." + current[-4:]) if len(current) > 8 else (current or "(not set)")
        return await q.edit_message_text(
            f"🔗 Current Earnlinks API Token: {masked}\n\n"
            "✏️ Send your Earnlinks.in API token. This is used to shorten Free Trial "
            "delivery links — users must complete the shortener before getting their key.",
            reply_markup=kb.back_btn("adm_settings"))

    if data == "adm_setsupport":
        context.user_data["state"] = {"action": "await_support_username"}
        current = db.get_setting("support_username", "")
        return await q.edit_message_text(
            f"🆘 Current support username: @{current}\n\n"
            "✏️ Send the new Telegram username (without @):",
            reply_markup=kb.back_btn("adm_settings"))

    if data == "adm_broadcast":
        return await q.edit_message_text("📢 Who should receive the broadcast?", reply_markup=kb.broadcast_target_kb())

    if data == "adm_coupons":
        coupons = db.list_coupons()
        text = "🎟️ <b>Manage Coupons</b>\n\nTap a coupon to view/delete it, or add a new one:"
        return await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb.coupons_list_kb(coupons))

    if data == "adm_addcoupon":
        return await q.edit_message_text("🎯 Who is this coupon for?", reply_markup=kb.coupon_target_kb())

    if data in ("adm_coupontarget_all_except_reseller", "adm_coupontarget_reseller"):
        target_role = "all_except_reseller" if data == "adm_coupontarget_all_except_reseller" else "reseller"
        context.user_data["state"] = {"action": "await_coupon_new_code", "target_role": target_role}
        return await q.edit_message_text("✏️ Send the coupon code (e.g. SAVE10):",
                                          reply_markup=kb.back_btn("adm_coupons"))

    if data in ("adm_coupontype_percent", "adm_coupontype_flat"):
        pending = context.user_data.get("state", {})
        if pending.get("action") != "await_coupon_new_type":
            return
        discount_type = "percent" if data == "adm_coupontype_percent" else "flat"
        context.user_data["state"] = {"action": "await_coupon_new_value", "code": pending["code"],
                                       "target_role": pending["target_role"], "discount_type": discount_type}
        unit = "%" if discount_type == "percent" else "₹ (INR)"
        return await q.edit_message_text(f"✏️ Send the discount value ({unit}):",
                                          reply_markup=kb.back_btn("adm_coupons"))

    if data.startswith("adm_coupondur_"):
        pending = context.user_data.get("state", {})
        if pending.get("action") != "await_coupon_new_duration":
            return
        hours = int(data.split("_")[-1])
        context.user_data["state"] = {**pending, "action": "await_coupon_new_limit", "duration_hours": hours}
        return await q.edit_message_text("👥 How many times can ONE user use this coupon?",
                                          reply_markup=kb.coupon_limit_kb())

    if data.startswith("adm_couponlimit_"):
        pending = context.user_data.get("state", {})
        if pending.get("action") != "await_coupon_new_limit":
            return
        raw = data.split("_")[-1]
        per_user_limit = -1 if raw == "unlimited" else int(raw)
        db.add_coupon(pending["code"], pending["discount_type"], pending["value"],
                       target_role=pending["target_role"], duration_hours=pending["duration_hours"],
                       per_user_limit=per_user_limit)
        context.user_data.pop("state", None)
        limit_label = "Unlimited" if per_user_limit == -1 else str(per_user_limit)
        unit = "%" if pending["discount_type"] == "percent" else "₹"
        await q.answer("Coupon created ✅", show_alert=True)
        text = (
            f"✅ Coupon <b>{pending['code']}</b> created!\n\n"
            f"🎯 For: {pending['target_role'].replace('_', ' ').title()}\n"
            f"💸 Discount: {pending['value']}{unit} off\n"
            f"⏰ Valid for: {pending['duration_hours']} hours\n"
            f"👥 Per-user limit: {limit_label}"
        )
        return await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb.coupons_list_kb(db.list_coupons()))

    if data.startswith("adm_coupon_"):
        code = data.split("_", 2)[2]
        c = db.get_coupon(code)
        if not c:
            return await q.edit_message_text("⚠️ Coupon not found.", reply_markup=kb.back_btn("adm_coupons"))
        unit = "%" if c["discount_type"] == "percent" else "₹"
        text = (f"🎟️ <b>{c['code']}</b>\n\nType: {c['discount_type']}\nValue: {c['discount_value']}{unit} off\n"
                f"Status: {'Active ✅' if c['active'] else 'Inactive ❌'}")
        return await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb.coupon_detail_kb(code))

    if data.startswith("adm_delcoupon_"):
        code = data.split("_", 2)[2]
        db.delete_coupon(code)
        await q.answer("Coupon deleted ✅", show_alert=True)
        coupons = db.list_coupons()
        return await q.edit_message_text("🎟️ <b>Manage Coupons</b>", parse_mode="HTML",
                                          reply_markup=kb.coupons_list_kb(coupons))

    if data == "adm_customtexts":
        text = (
            "📝 <b>Customize Text</b>\n\n"
            "Tap any item to edit its message text.\n"
            "You can use <code>&lt;tg-emoji emoji-id=\"...\"&gt;😀&lt;/tg-emoji&gt;</code> for 3D/custom emoji "
            "(requires Telegram Premium on the bot owner's account).\n\n"
            "Changes apply instantly for all users:"
        )
        return await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb.customize_texts_kb())

    if data.startswith("adm_edittext_"):
        key = data.split("_", 2)[2]
        label = dict(kb.CUSTOMIZABLE_TEXTS).get(key, key)
        current = db.get_setting(f"text_{key}", "")
        context.user_data["state"] = {"action": "await_edit_text", "key": key}
        return await q.edit_message_text(
            f"✏️ <b>{label}</b>\n\nCurrent text:\n{current}\n\nSend the new text (HTML allowed):",
            parse_mode="HTML", reply_markup=kb.back_btn("adm_customtexts"))

    if data == "adm_customheaders":
        text = (
            "🏷 <b>Customize Headers</b>\n\n"
            "These are the headers shown in the Shop Now flow: Shop → Category → "
            "Product → Duration/Order Summary.\n\n"
            "Tap any header to edit it — every word is editable, including the "
            "shop/category/product name (shown as <code>{placeholders}</code>).\n"
            "It's always shown in bold automatically, no formatting needed.\n\n"
            "Changes apply instantly for all users:"
        )
        return await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb.customize_headers_kb())

    if data.startswith("adm_editheader_"):
        key = data.split("_", 2)[2]
        label = next((lbl for k, lbl, _ in kb.CUSTOMIZABLE_HEADERS if k == key), key)
        current = kb.get_header(key)
        is_customized = db.get_setting(f"header_{key}", None) is not None
        context.user_data["state"] = {"action": "await_edit_header", "key": key}
        placeholder_note = (
            "\n\n💡 You can use those <code>{placeholders}</code> anywhere in your text — "
            "they'll be swapped for the real value automatically."
            if "{" in current else ""
        )
        reset_note = (
            "\n\n♻️ This has been customized before — if it looks outdated, tap Reset below to "
            "go back to the latest built-in version." if is_customized else ""
        )
        buttons = []
        if is_customized:
            buttons.append([kb.btn("♻️ Reset to Default", callback_data=f"adm_resetheader_{key}", style="danger")])
        buttons.append([kb.btn("🔙 Back", callback_data="adm_customheaders", style="danger")])
        return await q.edit_message_text(
            f"✏️ <b>{label}</b>\n\nCurrent header:\n{current}\n\nSend the new header text:"
            f"{placeholder_note}{reset_note}",
            parse_mode="HTML", reply_markup=kb.InlineKeyboardMarkup(buttons))

    if data.startswith("adm_resetheader_"):
        key = data.split("_", 2)[2]
        db.delete_setting(f"header_{key}")
        context.user_data.pop("state", None)
        label = next((lbl for k, lbl, _ in kb.CUSTOMIZABLE_HEADERS if k == key), key)
        return await q.edit_message_text(
            f"✅ <b>{label}</b> reset to the latest built-in default.\n\nApplied instantly for all users.",
            parse_mode="HTML", reply_markup=kb.customize_headers_kb())

    if data == "adm_custombtns":
        text = (
            "🎨 <b>Customize Buttons</b>\n\n"
            "Tap any button to change its text/emoji.\n"
            "The change applies instantly for all users, no restart needed:"
        )
        return await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb.customize_buttons_kb())

    if data.startswith("adm_editbtn_"):
        key = data.split("_", 2)[2]
        label = dict(kb.CUSTOMIZABLE_BUTTONS).get(key, key)
        current = db.get_setting(f"btn_label_{key}", label)
        current_icon = kb.get_icon(key)
        icon_note = "✅ Custom 3D icon is set" if current_icon else "➖ No custom 3D icon set"
        context.user_data["state"] = {"action": "await_edit_button", "key": key}
        return await q.edit_message_text(
            f"✏️ <b>{label}</b> button\n\nCurrent text: {current}\n{icon_note}\n\n"
            "Send the new text/emoji.\n"
            "💎 To add a 3D icon: include a Telegram Premium custom emoji anywhere "
            "in your message (requires the bot owner account to have Premium) — "
            "it'll be detected and saved automatically.",
            parse_mode="HTML", reply_markup=kb.back_btn("adm_custombtns"))

    if data == "adm_custombtncolors":
        text = "🌈 <b>Button Colors</b>\n\nTap any group below to change its color:"
        return await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb.button_colors_kb())

    if data.startswith("adm_colorgrp_"):
        key = data.split("_", 2)[2]
        label = next((lbl for k, lbl, _ in kb.STYLE_GROUPS if k == key), key)
        return await q.edit_message_text(f"🌈 Choose a color for <b>{label}</b>:", parse_mode="HTML",
                                          reply_markup=kb.color_choice_kb(key))

    if data.startswith("adm_setcolor_"):
        parts = data.split("_")
        key, color = parts[2], parts[3]
        db.set_setting(f"style_{key}", color)
        await q.answer("Color updated ✅", show_alert=True)
        text = "🌈 <b>Button Colors</b>\n\nTap any group below to change its color:"
        return await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb.button_colors_kb())

    if data in ("adm_bc_all", "adm_bc_reseller"):
        target = "all" if data == "adm_bc_all" else "reseller"
        context.user_data["state"] = {"action": "await_broadcast_content", "target": target}
        return await q.edit_message_text("✏️ Now send the text/photo/video/voice you want to broadcast:",
                                          reply_markup=kb.back_btn("adm_settings"))

    if data == "adm_bc_specific":
        context.user_data["state"] = {"action": "await_broadcast_specific_id"}
        return await q.edit_message_text("🎯 Send the user's numeric Telegram ID:",
                                          reply_markup=kb.back_btn("adm_settings"))
