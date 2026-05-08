"""
Хэндлеры админских команд (/stats, /grant).
Доступны только пользователям из ADMIN_IDS — для остальных молча игнорируются,
чтобы не раскрывать факт существования команд.
"""

import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from config import settings
from database import (
    get_stats,
    admin_add_bonus_credits,
    find_user_by_username,
)

logger = logging.getLogger(__name__)
router = Router()

# Защита от опечаток — лимит на одну команду /grant
MAX_GRANT_AMOUNT = 1000

GRANT_USAGE = (
    "<b>Использование:</b>\n"
    "<code>/grant &lt;user_id|@username&gt; &lt;amount&gt;</code>\n\n"
    "Примеры:\n"
    "<code>/grant 123456789 5</code>\n"
    "<code>/grant @username 3</code>"
)


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


# ── /grant — выдача бонусных кредитов ─────────────────────────────────────────

async def _resolve_target(target_arg: str) -> tuple[int | None, str | None]:
    """
    Преобразует аргумент команды (число или @username) в telegram_id.
    Возвращает (telegram_id, error_message). Один из них всегда None.
    """
    raw = target_arg.lstrip("@")

    # Числовой ID
    if raw.isdigit():
        return int(raw), None

    # @username — ищем в БД
    if not raw:
        return None, "Пустой аргумент. Укажи user_id или @username."

    target_id = await find_user_by_username(raw)
    if target_id is None:
        return None, (
            f"Пользователь @{raw} не найден в базе.\n"
            "Он должен сначала запустить бота хотя бы раз."
        )
    return target_id, None


@router.message(Command("grant"))
async def cmd_grant(message: Message, command: CommandObject) -> None:
    if message.from_user.id not in settings.ADMIN_IDS:
        return  # Молча игнорируем для не-админов

    args = (command.args or "").split()
    if len(args) != 2:
        await message.answer(GRANT_USAGE, parse_mode="HTML")
        return

    target_arg, amount_str = args

    try:
        amount = int(amount_str)
    except ValueError:
        await message.answer("❌ Количество должно быть целым числом.")
        return

    if amount <= 0:
        await message.answer("❌ Количество должно быть положительным.")
        return

    if amount > MAX_GRANT_AMOUNT:
        await message.answer(f"❌ За одну команду нельзя выдать больше {MAX_GRANT_AMOUNT}.")
        return

    target_id, err = await _resolve_target(target_arg)
    if err:
        await message.answer(f"❌ {err}")
        return

    new_balance = await admin_add_bonus_credits(target_id, amount)
    if new_balance is None:
        await message.answer(
            f"❌ Пользователь <code>{target_id}</code> не найден в базе.\n"
            "Он должен сначала запустить бота.",
            parse_mode="HTML",
        )
        return

    await message.answer(
        f"✅ Выдано <b>{amount}</b> бонусных кредитов пользователю "
        f"<code>{target_id}</code>.\n"
        f"Новый баланс бонусов: <b>{new_balance}</b>",
        parse_mode="HTML",
    )
    logger.info(
        "Админ %d выдал %d кредитов пользователю %d (новый баланс: %d).",
        message.from_user.id, amount, target_id, new_balance,
    )

    # Уведомляем получателя — best effort, не падаем если он заблокировал бота
    try:
        await message.bot.send_message(
            target_id,
            f"🎁 Тебе начислено <b>{amount}</b> "
            f"бонус{'ный кредит' if amount == 1 else 'ных кредитов'} "
            f"на создание песни!\n\n"
            f"Используй их через /menu или /start 🎵",
            parse_mode="HTML",
        )
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logger.info("Не удалось уведомить %d о выдаче кредитов: %s", target_id, e)
        await message.answer(
            "⚠️ <i>Кредиты начислены, но уведомить пользователя не удалось "
            "(возможно, заблокировал бота).</i>",
            parse_mode="HTML",
        )
