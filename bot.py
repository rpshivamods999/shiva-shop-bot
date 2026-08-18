from aiogram import Bot, Dispatcher
from app.config import settings
from app.db import init_db
from app.handlers.user import router as user_router
from app.handlers.admin import router as admin_router

async def main():
    await init_db()
    bot = Bot(settings.bot_token)
    dp = Dispatcher()
    dp.include_router(admin_router)
    dp.include_router(user_router)
    await dp.start_polling(bot)
