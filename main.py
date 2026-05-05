"""
Точка входа для Telegram бота.
Инициализирует бота, диспетчер и регистрирует все хэндлеры.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage

from config import settings
from database import get_pool, close_pool
from handlers import start, genre, mood, voice, details, editing, music

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def register_all_handlers(dp: Dispatcher) -> None:
    dp.include_router(start.router)
    dp.include_router(genre.router)
    dp.include_router(mood.router)
    dp.include_router(voice.router)
    dp.include_router(details.router)
    dp.include_router(editing.router)
    dp.include_router(music.router)


async def main() -> None:
    logger.info("Запуск бота...")

    # ── Redis FSM storage ──────────────────────────────────────────────────────
    storage = RedisStorage.from_url(settings.REDIS_URL)

    bot = Bot(token=settings.BOT_TOKEN)
    dp  = Dispatcher(storage=storage)

    register_all_handlers(dp)

    # ── Прогрев пула БД при старте ─────────────────────────────────────────────
    await get_pool()

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен. Начинаем polling...")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await close_pool()
        await storage.close()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    asyncio.run(main())
