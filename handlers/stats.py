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
    get_funnel_stats,
    admin_add_bonus_credits,
    find_user_by_username,
)


# Человекочитаемые подписи шагов воронки для отчёта /funnel
FUNNEL_LABELS = {
    "bot_started":        "Запустил бота",
    "flow_started":       "Нажал «Новая песня»",
    "genre_selected":     "Выбрал жанр",
    "mood_selected":      "Выбрал настроение",
    "voice_selected":     "Выбрал голос",
    "details_submitted":  "Отправил детали",
    "text_generated":     "Получил текст",
    "music_started":      "Нажал «Создать песню»",
    "music_delivered":    "Получил музыку",
}

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


# ── /funnel — воронка конверсии ───────────────────────────────────────────────

@router.message(Command("funnel"))
async def cmd_funnel(message: Message, command: CommandObject) -> None:
    """
    Показывает воронку конверсии за N дней.
    Использование:
        /funnel        — за 7 дней
        /funnel 30     — за 30 дней
        /funnel 1      — за сутки
    """
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    period = 7
    arg = (command.args or "").strip()
    if arg:
        if not arg.isdigit() or not (1 <= int(arg) <= 365):
            await message.answer("Период должен быть числом дней от 1 до 365.")
            return
        period = int(arg)

    funnel = await get_funnel_stats(period_days=period)

    lines = [f"📉 <b>Воронка за {period} дн.</b>\n"]
    if funnel and funnel[0]["users_count"] == 0:
        lines.append("<i>Нет данных за выбранный период.</i>")
    else:
        for i, step in enumerate(funnel):
            label = FUNNEL_LABELS.get(step["step"], step["step"])
            n = step["users_count"]
            from_start = step["pct_from_start"]
            from_prev = step["pct_from_prev"]

            # Первый шаг — базовая когорта, проценты не показываем
            if i == 0:
                lines.append(f"<b>{n}</b>  · {label}")
            else:
                drop = 100 - from_prev if from_prev else 0
                drop_marker = "" if drop < 5 else f"  ⚠️ -{drop:.0f}%"
                lines.append(
                    f"<b>{n}</b>  ({from_start}% от старта, "
                    f"{from_prev}% от пред.)  · {label}{drop_marker}"
                )

    await message.answer("\n".join(lines), parse_mode="HTML")
    logger.info("Воронка запрошена админом %d за %d дней.", message.from_user.id, period)
