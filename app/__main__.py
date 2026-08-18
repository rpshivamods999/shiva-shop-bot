import asyncio
import logging
from aiogram import Bot, Dispatcher
from app.config import BOT_TOKEN
from app.handlers.user import user_router
from app.handlers.admin import admin_router

async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    dp.include_router(user_router)
    dp.include_router(admin_router)
    
    print("Bot is successfully running...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
