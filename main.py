"""
Точка входа для Telegram бота.
Инициализирует бота, диспетчер и регистрирует все хэндлеры.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import ErrorEvent, BotCommand, BotCommandScopeDefault
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from config import settings
from database import get_pool, close_pool
from handlers import (
    start, genre, mood, voice, details, editing, music,
    cancel, stats, examples, payment, partner,
)


# Команды, которые видны пользователю в выпадающем меню Telegram (рядом с "/")
USER_COMMANDS = [
    BotCommand(command="start",   description="🎵 Перезапустить бота"),
    BotCommand(command="menu",    description="🏠 Главное меню"),
    BotCommand(command="buy",     description="💎 Купить кредиты"),
    BotCommand(command="invite",  description="🎁 Получить бонус"),
    BotCommand(command="balance", description="💰 Мой баланс"),
    BotCommand(command="cancel",  description="❌ Отменить текущее действие"),
    BotCommand(command="offer",   description="📄 Договор оферты"),
    BotCommand(command="help",    description="❓ Помощь"),
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def register_all_handlers(dp: Dispatcher) -> None:
    # cancel и stats регистрируем первыми — работают в любом состоянии
    dp.include_router(cancel.router)
    dp.include_router(stats.router)
    # examples ДО start — чтобы /getfileid (audio от админа) перехватывался первым,
    # пока админ не находится в фоне состояния SongCreation.
    dp.include_router(examples.router)
    # payment — отдельный поток покупки, имеет своё FSM-состояние Payment.awaiting_phone,
    # не пересекается с SongCreation. Регистрируем до основного флоу.
    dp.include_router(payment.router)
    # partner — отдельная команда /me_partner, нет своих FSM-состояний
    dp.include_router(partner.router)
    dp.include_router(start.router)
    dp.include_router(genre.router)
    dp.include_router(mood.router)
    dp.include_router(voice.router)
    dp.include_router(details.router)
    dp.include_router(editing.router)
    dp.include_router(music.router)


async def main() -> None:
    # Валидируем конфиг сразу — лучше упасть здесь, чем на первом запросе
    settings.validate()

    logger.info("Запуск бота...")

    storage = RedisStorage.from_url(settings.REDIS_URL)
    bot     = Bot(token=settings.BOT_TOKEN)
    dp      = Dispatcher(storage=storage)

    register_all_handlers(dp)

    # ── Глобальный обработчик ошибок ──────────────────────────────────────────
    @dp.errors()
    async def global_error_handler(event: ErrorEvent) -> bool:
        exc = event.exception

        if isinstance(exc, TelegramForbiddenError):
            # Пользователь заблокировал бота — логируем и молча пропускаем
            logger.warning("Бот заблокирован пользователем: %s", exc)
            return True

        if isinstance(exc, TelegramBadRequest):
            # Устаревшее сообщение, нельзя редактировать и т.п. — не критично
            logger.warning("TelegramBadRequest (проигнорировано): %s", exc)
            return True

        # Всё остальное — логируем как ошибку с полным traceback
        logger.error(
            "Необработанное исключение в хэндлере: %s",
            exc,
            exc_info=True,
        )
        return False   # False = aiogram не глушит исключение, оно пойдёт дальше

    await get_pool()

    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_my_commands(USER_COMMANDS, scope=BotCommandScopeDefault())
    logger.info("Команды бота зарегистрированы в Telegram.")
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
