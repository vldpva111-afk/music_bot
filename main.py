"""
Точка входа для Telegram бота.
Инициализирует бота, диспетчер и регистрирует все хэндлеры.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from handlers import start, genre, mood, voice, details, editing, music

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def register_all_handlers(dp: Dispatcher) -> None:
    """Регистрирует все роутеры в диспетчере."""
    dp.include_router(start.router)
    dp.include_router(genre.router)
    dp.include_router(mood.router)
    dp.include_router(voice.router)
    dp.include_router(details.router)
    dp.include_router(editing.router)
    dp.include_router(music.router)   # ← ВОТ ЭТОГО НЕ ХВАТАЛО


async def main() -> None:
    """Основная асинхронная функция запуска бота."""
    logger.info("Запуск бота...")

    bot = Bot(token=settings.BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    register_all_handlers(dp)

    # Удаляем вебхук и запускаем polling
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен. Начинаем polling...")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    asyncio.run(main())
