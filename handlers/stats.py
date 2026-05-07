"""
Хэндлер /stats — статистика бота для администратора.
Доступен только пользователям из ADMIN_IDS.
"""

import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import settings
from database import get_stats

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if message.from_user.id not in settings.ADMIN_IDS:
        return  # Молча игнорируем — не сообщаем что команда существует

    stats = await get_stats()

    text = (
        "📊 <b>Статистика бота</b>\n\n"

        "👥 <b>Пользователи</b>\n"
        f"  Всего: {stats['users_total']}\n"
        f"  Сегодня: {stats['users_today']}\n"
        f"  За 7 дней: {stats['users_week']}\n\n"

        "✍️ <b>Тексты песен (генерации)</b>\n"
        f"  Всего: {stats['texts_total']}\n"
        f"  Сегодня: {stats['texts_today']}\n"
        f"  За 7 дней: {stats['texts_week']}\n\n"

        "🎵 <b>Готовая музыка</b>\n"
        f"  Всего: {stats['music_total']}\n"
        f"  Сегодня: {stats['music_today']}\n"
        f"  За 7 дней: {stats['music_week']}\n\n"

        "📈 <b>Конверсия</b>\n"
        f"  Текст → Музыка: {stats['conversion_pct']}%\n"
        f"  Среднее генераций на юзера: {stats['avg_per_user']}\n"
    )

    await message.answer(text, parse_mode="HTML")
    logger.info("Статистика запрошена пользователем %d", message.from_user.id)
