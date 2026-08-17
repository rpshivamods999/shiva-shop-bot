import logging
import os
import asyncio
import datetime

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ApplicationHandlerStop
)

from config import BOT_TOKEN, ADMIN_IDS, DB_PATH
import database as db
import keyboards as kb
import user_handlers as uh
import admin_handlers as ah
import common_handlers as ch
import fampay_utils as fp
import binance_utils as bu

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background Maintenance & Automated Backup Tasks
# ---------------------------------------------------------------------------
async def daily_backup(context: ContextTypes.DEFAULT_TYPE):
    """Sends database backup to all admins once every 24 hours."""
    if not os.path.exists(DB_PATH):
        return
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
    for admin_id in ADMIN_IDS:
        try:
            with open(DB_PATH, "rb") as f:
                await context.bot.send_document(
                    admin_id, 
                    document=f, 
                    filename=f"shop_bot_backup_{timestamp}.db",
                    caption=f"💾 <b>Daily Automatic Backup</b>\n🕐 {timestamp}",
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.error("daily_backup: failed to send to admin %s: %s", admin_id, e)


async def maintenance_gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Intercepts all updates when Maintenance Mode is enabled (group=-1)."""
    if not db.is_maintenance_mode():
        return

    user = update.effective_user
    if user and db.is_admin(user.id):
        return  # Admins bypass maintenance gate

    if update.callback_query:
        try:
            await update.callback_query.answer(
                "🚧 Bot is under maintenance. Please check back soon!", show_alert=True
            )
        except Exception:
            pass
    elif update.message:
        try:
            await update.message.reply_text(
                "🚧 <b>Bot is under maintenance</b>\n\n"
                "We are currently making improvements. Please check back in a little while "
                "— sorry for the inconvenience!",
                parse_mode="HTML"
            )
        except Exception:
            pass

    raise ApplicationHandlerStop()


# ---------------------------------------------------------------------------
# Router Handlers
# ---------------------------------------------------------------------------
async def route_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data or ""
    if data.startswith("adm_"):
        await ah.admin_callback(update, context)
    elif data.startswith("u_"):
        await uh.user_callback(update, context)


async def route_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state")
    if state and state.get("action") == "await_binance_order_id":
        await uh.handle_binance_order_id_text(update, context)
        return
    await ch.handle_text(update, context)


async def cleanup_stale_transactions(context: ContextTypes.DEFAULT_TYPE):
    stale_orders, stale_deposits = db.cancel_stale_transactions(minutes=5)
    for o in stale_orders:
        try:
            text = kb.get_header("payment_expired_message", reference=o['reference'])
            await context.bot.send_message(o["telegram_id"], text, parse_mode="HTML")
        except Exception:
            pass
    for d in stale_deposits:
        try:
            text = kb.get_header("payment_expired_message", reference=d['reference'])
            await context.bot.send_message(d["telegram_id"], text, parse_mode="HTML")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Automated Payment Polling Loops
# ---------------------------------------------------------------------------
async def poll_upi_deposits(context: ContextTypes.DEFAULT_TYPE):
    """Auto-verifies FamPay-backed UPI deposits and orders in the background."""
    for dep in db.list_pending_gateway_deposits():
        try:
            status, raw = fp.verify_order(dep["gateway_order_id"])
        except Exception as e:
            logger.error("poll_upi_deposits: verify_order crashed for deposit #%s: %s", dep["id"], e)
            continue

        if status == "success" and not fp.amount_is_sufficient(raw, dep["amount"]):
            paid = fp.get_paid_amount(raw)
            logger.warning("poll_upi_deposits: deposit #%s UNDERPAID", dep["id"])
            try:
                await ch.notify_admins_amount_mismatch(context, "deposit", dep["id"], dep["amount"], paid, raw)
            except Exception:
                pass
            continue

        if status == "success":
            db.set_deposit_status(dep["id"], "completed")
            if dep.get("purpose") == "reseller_upgrade":
                await ch.complete_reseller_upgrade(context, dep["id"], "UPI (Auto-Verified)")
            else:
                previous_balance = db.get_user(dep["telegram_id"])["balance"]
                db.adjust_balance(dep["telegram_id"], dep["amount"], "deposit", f"Deposit #{dep['id']} auto-verified")
                db.set_deposit_balances(dep["id"], previous_balance, previous_balance + dep["amount"])
                db.credit_referral_commission(dep["telegram_id"], dep["amount"], f"deposit #{dep['id']}")
                try:
                    await context.bot.send_message(
                        dep["telegram_id"],
                        kb.get_header("deposit_confirmed_message", amount=dep["amount"],
                                      previous_balance=previous_balance, new_balance=previous_balance + dep["amount"]),
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
                await ch.notify_admins_deposit_completed(context, dep["id"], "UPI (Auto-Verified)")
        elif status in ("failed", "expired"):
            db.set_deposit_status(dep["id"], "cancelled")
            try:
                text = kb.get_header("payment_expired_message", reference=dep.get("reference", ""))
                await context.bot.send_message(dep["telegram_id"], text, parse_mode="HTML")
            except Exception:
                pass

    for o in db.list_pending_gateway_orders():
        try:
            status, raw = fp.verify_order(o["gateway_order_id"])
        except Exception as e:
            logger.error("poll_upi_deposits: verify_order crashed for order #%s: %s", o["id"], e)
            continue

        if status == "success" and not fp.amount_is_sufficient(raw, o["price"]):
            paid = fp.get_paid_amount(raw)
            try:
                await ch.notify_admins_amount_mismatch(context, "order", o["id"], o["price"], paid, raw)
            except Exception:
                pass
            continue

        if status == "success":
            await uh.deliver_order_key(context, o["id"], o)
        elif status in ("failed", "expired"):
            db.set_order_status(o["id"], "cancelled")
            try:
                text = kb.get_header("payment_expired_message", reference=o.get("reference", ""))
                await context.bot.send_message(o["telegram_id"], text, parse_mode="HTML")
            except Exception:
                pass


async def poll_binance_payments(context: ContextTypes.DEFAULT_TYPE):
    """Background automatic verification for Binance payments."""
    try:
        with db.get_conn() as conn:
            review_orders = conn.execute(
                "SELECT * FROM orders WHERE status='review' AND binance_order_id IS NOT NULL AND method='binance'"
            ).fetchall()
            review_deposits = conn.execute(
                "SELECT * FROM deposits WHERE status='review' AND binance_order_id IS NOT NULL AND method='binance'"
            ).fetchall()

        for ro in review_orders:
            expected_usd = db.inr_to_usd(ro["price"])
            if bu.find_matching_payment(ro["binance_order_id"], expected_usd):
                await uh.deliver_order_key(context, ro["id"], dict(ro), method="binance")

        for rd in review_deposits:
            expected_usd = db.inr_to_usd(rd["amount"])
            if bu.find_matching_payment(rd["binance_order_id"], expected_usd):
                tid = rd["telegram_id"]
                if rd.get("purpose") == "reseller_upgrade":
                    db.set_deposit_status(rd["id"], "completed")
                    await ch.complete_reseller_upgrade(context, rd["id"], "Binance (Auto-Verified)")
                else:
                    previous_balance = db.get_user(tid)["balance"]
                    db.set_deposit_status(rd["id"], "completed")
                    db.adjust_balance(tid, rd["amount"], "deposit", f"Deposit #{rd['id']} auto-verified (Binance)")
                    db.set_deposit_balances(rd["id"], previous_balance, previous_balance + rd["amount"])
                    db.credit_referral_commission(tid, rd["amount"], f"deposit #{rd['id']}")
                    try:
                        await context.bot.send_message(
                            tid,
                            kb.get_header("deposit_confirmed_message", amount=rd["amount"],
                                          previous_balance=previous_balance, new_balance=previous_balance + rd["amount"]),
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        logger.error("Failed to notify user about binance deposit: %s", e)
                    await ch.notify_admins_deposit_completed(context, rd["id"], "Binance (Auto-Verified)")
    except Exception as e:
        logger.error("poll_binance_payments crashed: %s", e)


# ---------------------------------------------------------------------------
# Fallback Async Task Scheduler
# ---------------------------------------------------------------------------
class _BotOnlyContext:
    """Minimal stand-in for ContextTypes.DEFAULT_TYPE when JobQueue is unavailable."""
    def __init__(self, bot):
        self.bot = bot


async def _run_repeating_fallback(coro_func, ctx, interval, first_delay):
    """Fallback scheduler used when app.job_queue is not installed."""
    await asyncio.sleep(first_delay)
    while True:
        try:
            await coro_func(ctx)
        except Exception:
            logger.exception("background job %s failed", getattr(coro_func, "__name__", coro_func))
        await asyncio.sleep(interval)


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler for catching unhandled exceptions."""
    logger.error("Unhandled exception while processing update: %s", update, exc_info=context.error)
    err_text = f"⚠️ Bot error: {type(context.error).__name__}: {context.error}"[:500]
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, err_text)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main Application Setup
# ---------------------------------------------------------------------------
def main():
    db.init_db()
    
    token = BOT_TOKEN.strip() if BOT_TOKEN else ""
    if not token:
        logger.error("BOT_TOKEN is missing or empty! Please set BOT_TOKEN in environment variables or config.py")
        return

    app = (
        Application.builder()
        .token(token)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .build()
    )

    # Priority Gate (group=-1)
    app.add_handler(MessageHandler(filters.ALL, maintenance_gate), group=-1)
    app.add_handler(CallbackQueryHandler(maintenance_gate), group=-1)

    # Command Handlers
    app.add_handler(CommandHandler("start", uh.start))
    app.add_handler(CommandHandler("admin", ah.admin_entry))
    app.add_handler(CommandHandler("stock", ah.stock_report))
    app.add_handler(CommandHandler("promote", ah.promote_cmd))
    app.add_handler(CommandHandler("demote", ah.demote_cmd))
    app.add_handler(CommandHandler("backup", ah.backup_cmd))
    app.add_handler(CommandHandler("hideresellerbutton", ah.hide_reseller_button))
    app.add_handler(CommandHandler("addresellerbutton", ah.add_reseller_button))
    app.add_handler(CommandHandler("hidetrail", ah.hide_trial_button))
    app.add_handler(CommandHandler("addtrail", ah.add_trial_button))
    app.add_handler(CommandHandler("maintenance", ah.maintenance_cmd))
    app.add_handler(CommandHandler("premium", ah.premium_cmd))
    app.add_handler(CommandHandler("basic", ah.basic_cmd))

    # General Handlers
    app.add_handler(CallbackQueryHandler(route_callback))
    app.add_error_handler(global_error_handler)

    app.add_handler(MessageHandler(filters.CONTACT, uh.handle_contact))
    app.add_handler(MessageHandler(filters.PHOTO, ch.handle_photo))
    app.add_handler(MessageHandler(
        filters.VIDEO | filters.VOICE | filters.Document.ALL | filters.AUDIO, ch.handle_other_media))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, route_text))

    # Job Queue or Fallback Scheduler
    if app.job_queue is not None:
        app.job_queue.run_repeating(cleanup_stale_transactions, interval=60, first=30)
        app.job_queue.run_repeating(poll_upi_deposits, interval=15, first=10)
        app.job_queue.run_repeating(poll_binance_payments, interval=15, first=12)
        app.job_queue.run_repeating(daily_backup, interval=24 * 60 * 60, first=60)
    else:
        logger.warning("JobQueue not available. Falling back to asyncio manual task scheduler.")

        async def _start_fallback_jobs(application):
            ctx = _BotOnlyContext(application.bot)
            asyncio.create_task(_run_repeating_fallback(cleanup_stale_transactions, ctx, 60, 30))
            asyncio.create_task(_run_repeating_fallback(poll_upi_deposits, ctx, 15, 10))
            asyncio.create_task(_run_repeating_fallback(poll_binance_payments, ctx, 15, 12))
            asyncio.create_task(_run_repeating_fallback(daily_backup, ctx, 24 * 60 * 60, 60))

        app.post_init = _start_fallback_jobs

    logger.info("Bot starting successfully...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
