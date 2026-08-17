import os
import sqlite3
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
)

# লগিং সেটআপ
logging.basicConfig(level=logging.INFO)

# এনভায়রনমেন্ট ভ্যারিয়েবল থেকে টোকেন ও অ্যাডমিন আইডি সংগ্রহ
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))

# ডাটাবেস প্রস্তুত করা
conn = sqlite3.connect('shop.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE,
    status INTEGER DEFAULT 1
)''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT,
    key_code TEXT UNIQUE,
    status TEXT DEFAULT 'available'
)''')
conn.commit()

# /admin কমান্ড
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        if update.message:
            await update.message.reply_text("⛔ আপনি এই প্যানেল ব্যবহারের অনুমতিপ্রাপ্ত নন।")
        return

    keyboard = [
        [InlineKeyboardButton("🛍️ Products", callback_data="admin_products"), InlineKeyboardButton("🔑 Keys", callback_data="admin_keys")],
        [InlineKeyboardButton("➕ Add Product", callback_data="add_product")],
        [InlineKeyboardButton("❌ Close", callback_data="close_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "🤖 **Rp Shiva Shop Admin Control Panel**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "ধাপ ১ টেস্ট ভার্সনে স্বাগতম! নিচে থেকে যেকোনো অপশন বেছে নিন।"
    )
    
    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

# ইনলাইন বাটন হ্যান্ডলার
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "admin_main":
        await admin_panel(update, context)
        
    elif query.data == "admin_products":
        cursor.execute("SELECT id, name, status FROM products")
        prods = cursor.fetchall()
        
        keyboard = []
        for p_id, p_name, p_status in prods:
            status_icon = "✅" if p_status == 1 else "🚫"
            keyboard.append([InlineKeyboardButton(f"{status_icon} {p_name}", callback_data=f"toggle_prod_{p_id}")])
            
        keyboard.append([InlineKeyboardButton("➕ Add Product", callback_data="add_product")])
        keyboard.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_main")])
        
        await query.edit_message_text("🛍️ **PRODUCTS MANAGEMENT**\n\nপণ্য অন/অফ করতে নামের ওপর ট্যাপ করুন:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("toggle_prod_"):
        p_id = int(query.data.split("_")[2])
        cursor.execute("UPDATE products SET status = CASE WHEN status = 1 THEN 0 ELSE 1 END WHERE id = ?", (p_id,))
        conn.commit()
        # রিফ্রেশ প্রোডাক্ট লিস্ট
        await button_handler(update, context)

    elif query.data == "add_product":
        context.user_data['state'] = 'WAITING_FOR_PRODUCT_NAME'
        await query.edit_message_text("📝 নতুন প্রোডাক্টের নাম লিখে মেসেজ পাঠান:")

    elif query.data == "admin_keys":
        cursor.execute("SELECT COUNT(*) FROM keys")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM keys WHERE status='available'")
        available = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM keys WHERE status='sold'")
        sold = cursor.fetchone()[0]
        
        keyboard = [
            [InlineKeyboardButton("📩 Upload Keys", callback_data="upload_keys")],
            [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_main")]
        ]
        text = f"🔑 **KEYS STATS**\n━━━━━━━\n├ 🔢 Total: {total}\n├ ✅ Available: {available}\n└ 💰 Sold: {sold}"
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "upload_keys":
        cursor.execute("SELECT name FROM products WHERE status=1")
        prods = cursor.fetchall()
        if not prods:
            await query.edit_message_text("❌ কোনো একটিভ প্রোডাক্ট নেই! আগে প্রোডাক্ট যোগ করুন।", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_keys")]]))
            return
        
        keyboard = []
        for (p_name,) in prods:
            keyboard.append([InlineKeyboardButton(f"🛒 {p_name}", callback_data=f"sel_prod_key_{p_name}")])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_keys")])
        
        await query.edit_message_text("🔑 কোন প্রোডাক্টের জন্য লাইসেন্স কী (Key) আপলোড করতে চান সিলেক্ট করুন:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("sel_prod_key_"):
        p_name = query.data.replace("sel_prod_key_", "")
        context.user_data['state'] = 'WAITING_FOR_KEYS'
        context.user_data['target_product'] = p_name
        await query.edit_message_text(f"📥 **{p_name}**-এর জন্য কী (Key) গুলো মেসেজে পাঠান।\n(একাধিক কী একসাথে পাঠাতে প্রতি লাইনে ১টি করে দিন):")

    elif query.data == "close_panel":
        await query.delete_message()

# টেক্সট মেসেজ প্রসেসর (প্রোডাক্ট বা কী ইনপুটের জন্য)
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return

    state = context.user_data.get('state')
    
    if state == 'WAITING_FOR_PRODUCT_NAME':
        prod_name = update.message.text.strip()
        try:
            cursor.execute("INSERT INTO products (name) VALUES (?)", (prod_name,))
            conn.commit()
            await update.message.reply_text(f"✅ প্রোডাক্ট **{prod_name}** সফলভাবে যুক্ত হয়েছে!", parse_mode="Markdown")
        except sqlite3.IntegrityError:
            await update.message.reply_text("❌ এই নামের প্রোডাক্ট আগে থেকেই আছে!")
        context.user_data['state'] = None

    elif state == 'WAITING_FOR_KEYS':
        raw_keys = update.message.text.strip().split('\n')
        p_name = context.user_data.get('target_product')
        
        count = 0
        for k in raw_keys:
            key_code = k.strip()
            if key_code:
                try:
                    cursor.execute("INSERT INTO keys (product_name, key_code) VALUES (?, ?)", (p_name, key_code))
                    count += 1
                except sqlite3.IntegrityError:
                    pass
        conn.commit()
        await update.message.reply_text(f"✅ **{p_name}**-এর জন্য মোট **{count}** টি নতুন কী (Key) সফলভাবে আপলোড হয়েছে!", parse_mode="Markdown")
        context.user_data['state'] = None

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    print("Bot is starting...")
    app.run_polling()