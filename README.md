# Telegram Shop Bot — Railway Starter

A production-oriented starter for a Telegram shop bot using Python, aiogram 3, PostgreSQL and SQLAlchemy.

## 1. Create the bot
Create a bot with @BotFather and copy its token.

## 2. GitHub
Upload this entire folder to a new GitHub repository.

## 3. Railway
Create a new Railway project from the GitHub repository.
Add a PostgreSQL service.
Add these environment variables to the bot service:

BOT_TOKEN=your_telegram_bot_token
DATABASE_URL=${{Postgres.DATABASE_URL}}

Railway may expose PostgreSQL as `DATABASE_URL`. If your variable has another name, set BOT_DATABASE_URL to that value and change the code accordingly.

## 4. Start command
Railway should run:
python -m app

## 5. Admin
Set:
ADMIN_IDS=123456789,987654321

Replace those IDs with your Telegram numeric user IDs.

## Current implemented foundation
- /start
- Main user menu
- Products/categories
- Product variants
- User wallet balance
- Orders
- Coupon validation
- User-specific custom price
- Ban/unban fields in database
- Admin commands for adding products, variants, balance and banning
- PostgreSQL persistence
- Environment-based configuration

Payment gateways are intentionally separated from the core order system. Real Paytm/Binance verification should be added only with the provider's official API/webhook and server-side transaction verification.

## Local run
Python 3.11+
pip install -r requirements.txt
python -m app
