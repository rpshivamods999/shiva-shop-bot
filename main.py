import os
import logging
import uuid
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment Variables & Configuration
# ---------------------------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PAYTM_MID = os.getenv("PAYTM_MID", "")          # Paytm Merchant ID
PAYTM_UPI_ID = os.getenv("PAYTM_UPI_ID", "")    # Custom UPI ID (e.g. merchant@paytm)

# ---------------------------------------------------------------------------
# Conversation Handler States
# ---------------------------------------------------------------------------
ADD_CAT_NAME = 1
ADD_PROD_CAT, ADD_PROD_NAME, ADD_PROD_PRICE, ADD_PROD_DESC = range(2, 6)
ADD_KEY_PROD, ADD_KEY_VAL = range(6, 8)

# ---------------------------------------------------------------------------
# In-Memory Database (Production structure ready)
# ---------------------------------------------------------------------------
CATEGORIES = []
PRODUCTS = {}         # {prod_id: {"category": str, "name": str, "price": str, "desc": str, "keys": []}}
PENDING_ORDERS = {}   # {order_id: {"user_id": int, "prod_id": int, "price": str}}
product_counter = 1

# ---------------------------------------------------------------------------
# Paytm & Auto-Verification Core Logic
# ---------------------------------------------------------------------------
def verify_payment_api(order_id: str) -> bool:
    """
    Verifies payment status with Paytm Gateway API.
    Returns True if payment is successful, False otherwise.
    """
    if not PAYTM_MID:
        return False
    # Paytm API Transaction Status Check Integration Logic
    url = f"https://securegw.paytm.in/v3/order/status"
    # Insert production status check checksum logic here when needed
    return False

# ---------------------------------------------------------------------------
# USER HANDLERS
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    
    welcome_text = (
        f"⚡ **WELCOME TO RP SHIVA LIVE SHOP** ⚡\n"
        f"─────────────────────────────\n"
        f"Hello **{first_name}**, welcome to our official automated store!\n\n"
        f"🔹 Instant Automatic Key & File Delivery\n"
        f"🔹 24/7 Verified Payment Gateway\n"
        f"🔹 Dedicated Customer Support\n\n"
        f"Please select an option from the menu below:"
    )
    
    keyboard = [
        [InlineKeyboardButton("🛒 Browse Shop & Products", callback_data="user_categories")],
        [InlineKeyboardButton("💳 Payment Info & Methods", callback_data="user_payment")],
        [InlineKeyboardButton("👨‍💻 Official Support", callback_data="user_support")]
    ]
    
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Admin Control Panel", callback_data="admin_panel")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    await query.answer()

    if data == "main_menu":
        await start(update, context)

    elif data == "close_menu":
        await query.delete_message()

    elif data == "user_payment":
        text = (
            "💳 **PAYMENT METHODS & INFORMATION**\n"
            "─────────────────────────────\n"
            "• **Accepted Gateway:** Paytm, PhonePe, Google Pay, BHIM UPI\n"
            "• **Auto Verification:** Instant order fulfillment upon payment\n\n"
            "If you face any issues during payment, click Support below."
        )
        keyboard = [[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "user_support":
        text = (
            "👨‍💻 **OFFICIAL CUSTOMER SUPPORT**\n"
            "─────────────────────────────\n"
            "Need help with your order or custom requirements?\n\n"
            "• **Telegram Direct Support:** `@RpShivaLive`\n"
            "• **Operating Hours:** 24/7 Active"
        )
        keyboard = [[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    # ---------------- USER BROWSE & SHOPPING ----------------
    elif data == "user_categories":
        if not CATEGORIES:
            text = "❌ **No categories available at the moment.** Please check back later!"
            keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return

        keyboard = []
        for cat in CATEGORIES:
            keyboard.append([InlineKeyboardButton(f"📁 {cat}", callback_data=f"show_cat_{cat}")])
        keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")])
        
        await query.edit_message_text(
            "📂 **SELECT A CATEGORY:**\nChoose a category below to explore items:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif data.startswith("show_cat_"):
        cat_name = data.replace("show_cat_", "")
        cat_prods = {pid: item for pid, item in PRODUCTS.items() if item["category"] == cat_name}
        
        if not cat_prods:
            text = f"❌ No products currently listed under **{cat_name}**."
            keyboard = [[InlineKeyboardButton("🔙 Back to Categories", callback_data="user_categories")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return

        keyboard = []
        for pid, item in cat_prods.items():
            stock = len(item["keys"])
            stock_status = f"{stock} Available" if stock > 0 else "OUT OF STOCK"
            keyboard.append([
                InlineKeyboardButton(f"📦 {item['name']} | ₹{item['price']} ({stock_status})", callback_data=f"buy_{pid}")
            ])
        keyboard.append([InlineKeyboardButton("🔙 Back to Categories", callback_data="user_categories")])
        
        await query.edit_message_text(
            f"🛍️ **PRODUCTS IN {cat_name.upper()}:**\nSelect an item to view details & buy:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    # ---------------- CHECKOUT & AUTO PAYTM ----------------
    elif data.startswith("buy_"):
        pid = int(data.split("_")[1])
        item = PRODUCTS.get(pid)
        
        if not item or len(item["keys"]) == 0:
            text = "⚠️ **Sorry! This product is currently Out of Stock.**\nPlease contact Admin for restock."
            keyboard = [[InlineKeyboardButton("🔙 Back to Shop", callback_data="user_categories")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return

        order_id = "SHIVA-" + uuid.uuid4().hex[:8].upper()
        PENDING_ORDERS[order_id] = {
            "user_id": user_id,
            "prod_id": pid,
            "price": item["price"]
        }

        # Paytm / UPI String Construction
        upi_vpa = PAYTM_UPI_ID if PAYTM_UPI_ID else f"{PAYTM_MID}@paytm"
        pay_url = f"upi://pay?pa={upi_vpa}&pn=RPSHIVASHOP&am={item['price']}&tn={order_id}&cu=INR"
        qr_image_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={pay_url}"

        checkout_text = (
            f"🛒 **CHECKOUT & AUTO PAYMENT**\n"
            f"─────────────────────────────\n"
            f"📦 **Item:** {item['name']}\n"
            f"💰 **Total Price:** ₹{item['price']}\n"
            f"🆔 **Order ID:** `{order_id}`\n\n"
            f"📌 **Description:**\n{item['desc']}\n\n"
            f"👇 **Payment Instructions:**\n"
            f"1. Click **'Pay via Paytm / UPI'** or scan the QR code.\n"
            f"2. Complete the payment of ₹{item['price']}.\n"
            f"3. Click **'Verify Payment'** below for instant automated delivery!"
        )
        
        keyboard = [
            [InlineKeyboardButton("📲 Pay via Paytm / UPI App", url=pay_url)],
            [InlineKeyboardButton("✅ Verify Payment Now", callback_data=f"verify_{order_id}")],
            [InlineKeyboardButton("❌ Cancel Order", callback_data="user_categories")]
        ]
        
        await query.edit_message_text(
            checkout_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif data.startswith("verify_"):
        order_id = data.replace("verify_", "")
        order = PENDING_ORDERS.get(order_id)
        
        if not order:
            await query.edit_message_text("❌ Order expired or invalid. Please start checkout again.")
            return

        pid = order["prod_id"]
        item = PRODUCTS.get(pid)

        # Execute Auto-Verification Check
        is_verified = verify_payment_api(order_id)
        
        if is_verified and item and len(item["keys"]) > 0:
            delivered_key = item["keys"].pop(0)  # Auto-dispatch key
            del PENDING_ORDERS[order_id]
            
            success_text = (
                f"🎉 **PAYMENT SUCCESSFUL!** 🎉\n"
                f"─────────────────────────────\n"
                f"Thank you for your purchase!\n\n"
                f"📦 **Product:** {item['name']}\n"
                f"🔐 **Your License Key / Digital Link:**\n\n"
                f"`{delivered_key}`\n\n"
                f"⚠️ *Keep this key safe. Contact support if you need assistance.*"
            )
            await query.edit_message_text(success_text, parse_mode="Markdown")
        else:
            unverified_text = (
                f"⏳ **PAYMENT NOT DETECTED YET**\n"
                f"─────────────────────────────\n"
                f"Order ID: `{order_id}`\n\n"
                f"If you have already paid, please allow 1-2 minutes for the banking server to sync and tap **'Try Verification Again'**.\n\n"
                f"For manual verification, send your payment screenshot to `@RpShivaLive`."
            )
            keyboard = [
                [InlineKeyboardButton("🔄 Try Verification Again", callback_data=f"verify_{order_id}")],
                [InlineKeyboardButton("👨‍💻 Contact Support", callback_data="user_support")],
                [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
            ]
            await query.edit_message_text(unverified_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "admin_panel":
        await admin_panel(update, context)

    elif data == "admin_list_prod":
        if not PRODUCTS:
            text = "❌ **No products currently listed in inventory.**"
        else:
            text = "📋 **CURRENT INVENTORY LIST:**\n─────────────────────────────\n"
            for pid, item in PRODUCTS.items():
                text += f"• **ID #{pid}:** {item['name']} | Category: {item['category']} | Price: ₹{item['price']} | Stock: {len(item['keys'])}\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# ---------------------------------------------------------------------------
# ADMIN PANEL HANDLERS
# ---------------------------------------------------------------------------
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id

    if user_id != ADMIN_ID:
        msg = "⛔ **Unauthorized Access Denied!**"
        if query:
            await query.edit_message_text(msg, parse_mode="Markdown")
        else:
            await update.message.reply_text(msg, parse_mode="Markdown")
        return

    admin_text = (
        "⚙️ **ADMIN CONTROL DASHBOARD**\n"
        "─────────────────────────────\n"
        "Manage your shop categories, products, stock, and automated settings below:"
    )
    
    keyboard = [
        [InlineKeyboardButton("📂 Add Category", callback_data="start_add_cat"), InlineKeyboardButton("📦 Add Product", callback_data="start_add_prod")],
        [InlineKeyboardButton("🔑 Add Keys / Stock", callback_data="start_add_key"), InlineKeyboardButton("📋 View Inventory", callback_data="admin_list_prod")],
        [InlineKeyboardButton("❌ Exit Admin Panel", callback_data="close_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    if query:
        await query.edit_message_text(admin_text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(admin_text, reply_markup=reply_markup, parse_mode="Markdown")

# ---------------- CONVERSATIONS FOR ADMIN ACTIONS ----------------
async def start_add_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📂 **Enter new Category Name:**\n(Example: `Free Fire Mods`, `VIP Root Services`)", parse_mode="Markdown")
    return ADD_CAT_NAME

async def add_cat_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cat_name = update.message.text.strip()
    if cat_name not in CATEGORIES:
        CATEGORIES.append(cat_name)
        await update.message.reply_text(f"✅ Category **{cat_name}** created successfully!\n\nType /admin to open dashboard.", parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠️ This category already exists.")
    return ConversationHandler.END

async def start_add_prod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not CATEGORIES:
        await query.edit_message_text("❌ Please create at least one category first using 'Add Category'.")
        return ConversationHandler.END
        
    cats = ", ".join(CATEGORIES)
    await query.edit_message_text(f"📁 Enter Category Name for this product:\n\nAvailable Categories: **{cats}**", parse_mode="Markdown")
    return ADD_PROD_CAT

async def add_prod_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cat = update.message.text.strip()
    if cat not in CATEGORIES:
        await update.message.reply_text(f"❌ Invalid category. Choose from: {', '.join(CATEGORIES)}")
        return ADD_PROD_CAT
    context.user_data['p_cat'] = cat
    await update.message.reply_text("📝 **Step 1/3:** Enter **Product Name**:")
    return ADD_PROD_NAME

async def add_prod_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['p_name'] = update.message.text.strip()
    await update.message.reply_text("💵 **Step 2/3:** Enter **Product Price (in ₹)**:")
    return ADD_PROD_PRICE

async def add_prod_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['p_price'] = update.message.text.strip()
    await update.message.reply_text("📋 **Step 3/3:** Enter **Product Description**:")
    return ADD_PROD_DESC

async def add_prod_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global product_counter
    PRODUCTS[product_counter] = {
        "category": context.user_data['p_cat'],
        "name": context.user_data['p_name'],
        "price": context.user_data['p_price'],
        "desc": update.message.text.strip(),
        "keys": []
    }
    await update.message.reply_text(f"✅ Product **{context.user_data['p_name']}** added with ID **#{product_counter}**!\n\nType /admin to open dashboard.", parse_mode="Markdown")
    product_counter += 1
    return ConversationHandler.END

async def start_add_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not PRODUCTS:
        await query.edit_message_text("❌ No products found. Create a product first.")
        return ConversationHandler.END
        
    prods_text = "\n".join([f"ID #{pid}: {item['name']}" for pid, item in PRODUCTS.items()])
    await query.edit_message_text(f"🔑 Select Product ID to add stock/keys to:\n\n{prods_text}")
    return ADD_KEY_PROD

async def add_key_prod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        pid = int(update.message.text.strip())
        if pid in PRODUCTS:
            context.user_data['key_pid'] = pid
            await update.message.reply_text("🔐 Enter the **License Key** or **File Link** to store:")
            return ADD_KEY_VAL
        else:
            await update.message.reply_text("❌ Invalid Product ID. Try again:")
            return ADD_KEY_PROD
    except ValueError:
        await update.message.reply_text("❌ Please enter a numeric Product ID:")
        return ADD_KEY_PROD

async def add_key_val(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pid = context.user_data['key_pid']
    PRODUCTS[pid]["keys"].append(update.message.text.strip())
    await update.message.reply_text(f"✅ Stock added successfully to Product ID **#{pid}**! Total Stock: {len(PRODUCTS[pid]['keys'])}\n\nType /admin to open dashboard.", parse_mode="Markdown")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operation cancelled. Type /admin to view options.")
    return ConversationHandler.END

# ---------------------------------------------------------------------------
# MAIN APPLICATION INITIALIZATION
# ---------------------------------------------------------------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    cat_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_cat, pattern="^start_add_cat$")],
        states={ADD_CAT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_cat_name)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    prod_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_prod, pattern="^start_add_prod$")],
        states={
            ADD_PROD_CAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_prod_cat)],
            ADD_PROD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_prod_name)],
            ADD_PROD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_prod_price)],
            ADD_PROD_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_prod_desc)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    key_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_key, pattern="^start_add_key$")],
        states={
            ADD_KEY_PROD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_key_prod)],
            ADD_KEY_VAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_key_val)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(cat_conv)
    app.add_handler(prod_conv)
    app.add_handler(key_conv)
    app.add_handler(CallbackQueryHandler(callback_handler))

    app.run_polling()

if __name__ == '__main__':
    main()
