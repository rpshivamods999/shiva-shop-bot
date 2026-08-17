import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# Logging Setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# States for Adding Product & Key
ADD_NAME, ADD_PRICE, ADD_DESC, ADD_KEY_PROD, ADD_KEY_VAL = range(5)

# In-Memory Database
PRODUCTS = {}  # {prod_id: {"name": str, "price": str, "desc": str, "keys": []}}
product_counter = 1

# Commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = "🔥 **WELCOME TO RP SHIVA LIVE SHOP** 🔥\n\nChoose an option from below:"
    keyboard = [
        [InlineKeyboardButton("🛒 Browse Products", callback_data="user_products")],
        [InlineKeyboardButton("💳 Payment Methods", callback_data="user_payment")],
        [InlineKeyboardButton("👨‍💻 Official Support", callback_data="user_support")]
    ]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("❌ Unauthorized Access!")
        return

    text = "🤖 **RP SHIVA LIVE SHOP - ADMIN PANEL**\n\nSelect an operation:"
    keyboard = [
        [InlineKeyboardButton("🛍️ Products", callback_data="list_products_admin"), InlineKeyboardButton("🔑 Stock Keys", callback_data="manage_keys")],
        [InlineKeyboardButton("➕ Add Product", callback_data="start_add_prod"), InlineKeyboardButton("➕ Add License/Key", callback_data="start_add_key")],
        [InlineKeyboardButton("❌ Close Panel", callback_data="close_menu")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data == "admin_panel":
        await admin_panel(update, context)
    elif data == "close_menu":
        await query.delete_message()
    elif data == "user_payment":
        text = "💳 **Payment Methods & Info**\n\n• **Bkash / Nagad / Upay:** Contact Admin\n• **UPI / QR Code:** Contact Admin\n\nAfter payment, send receipt screenshot to admin."
        keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    elif data == "user_support":
        text = "👨‍💻 **Official Customer Support**\n\nFor queries, payments, or manual support contact admin."
        keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    elif data == "main_menu":
        await start(update, context)
    elif data == "user_products":
        if not PRODUCTS:
            text = "❌ Currently no products are available in the shop."
            keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return
        keyboard = []
        for p_id, item in PRODUCTS.items():
            stock = len(item["keys"])
            keyboard.append([InlineKeyboardButton(f"📦 {item['name']} | ₹{item['price']} (Stock: {stock})", callback_data=f"buy_{p_id}")])
        keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")])
        await query.edit_message_text("🛍️ **Select a Product to Buy:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    elif data.startswith("buy_"):
        p_id = int(data.split("_")[1])
        item = PRODUCTS.get(p_id)
        if item:
            stock = len(item["keys"])
            text = f"📦 **Product:** {item['name']}\n💰 **Price:** ₹{item['price']}\n📊 **Stock:** {stock}\n\n📝 **Description:**\n{item['desc']}\n\nTo purchase, complete payment and contact Admin."
            keyboard = [[InlineKeyboardButton("🔙 Back to Shop", callback_data="user_products")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    elif data == "list_products_admin":
        if not PRODUCTS:
            text = "❌ No products found."
        else:
            text = "📋 **Product List:**\n\n"
            for p_id, item in PRODUCTS.items():
                text += f"• **ID {p_id}:** {item['name']} | ₹{item['price']} | Keys left: {len(item['keys'])}\n"
        keyboard = [[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# Conversation Handlers for Adding Product
async def start_add_prod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📝 **Step 1/3:** Enter the **Product Name**:")
    return ADD_NAME

async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['prod_name'] = update.message.text
    await update.message.reply_text("💵 **Step 2/3:** Enter the **Product Price**:")
    return ADD_PRICE

async def add_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['prod_price'] = update.message.text
    await update.message.reply_text("📋 **Step 3/3:** Enter the **Product Description**:")
    return ADD_DESC

async def add_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global product_counter
    context.user_data['prod_desc'] = update.message.text
    
    PRODUCTS[product_counter] = {
        "name": context.user_data['prod_name'],
        "price": context.user_data['prod_price'],
        "desc": context.user_data['prod_desc'],
        "keys": []
    }
    await update.message.reply_text(f"✅ Product **{context.user_data['prod_name']}** added successfully with ID #{product_counter}!\n\nUse /admin to return to panel.")
    product_counter += 1
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operation cancelled. Use /admin to open panel.")
    return ConversationHandler.END

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    prod_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_prod, pattern="^start_add_prod$")],
        states={
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            ADD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_price)],
            ADD_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_desc)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(prod_conv)
    app.add_handler(CallbackQueryHandler(callback_handler))

    app.run_polling()

if __name__ == '__main__':
    main()
