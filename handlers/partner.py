"""
Хэндлер для партнёров: команда /me_partner.

Партнёр видит ТОЛЬКО свою статистику — никаких других партнёров,
никаких чужих клиентов. Если юзер не партнёр — команда отвечает
нейтральным сообщением (не палим, что такая программа существует).
"""

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database import get_partner_stats

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("me_partner"))
async def cmd_me_partner(message: Message) -> None:
    user = message.from_user
    stats = await get_partner_stats(user.id)

    if not stats:
        # Юзер не партнёр — отвечаем нейтрально, чтобы не раскрывать структуру
        await message.answer(
            "🤔 Эта команда доступна только участникам партнёрской программы.\n\n"
            "Если хочешь стать партнёром и зарабатывать на каждом клиенте, "
            "которого приведёшь в бота — напиши администратору."
        )
        return

    # Реферальная ссылка партнёра
    try:
        me = await message.bot.me()
        ref_link = f"https://t.me/{me.username}?start=ref_{user.id}"
    except Exception as e:
        logger.warning("Не удалось получить username бота: %s", e)
        ref_link = None

    # Конверсия в %, с защитой от деления на 0
    conv = (
        round(100 * stats["clients_paid"] / stats["clients_total"], 1)
        if stats["clients_total"] > 0 else 0.0
    )

    pct = stats["commission_pct"]
    pct_str = f"{pct:.0f}" if pct == int(pct) else f"{pct:.2f}"

    name = stats["display_name"] or user.first_name or "партнёр"

    lines = [
        f"👋 Привет, <b>{name}</b>!\n",
        "📊 <b>Твоя статистика</b>",
        f"  Привёл клиентов: <b>{stats['clients_total']}</b>",
        f"  Из них купили: <b>{stats['clients_paid']}</b>",
        f"  Конверсия: <b>{conv}%</b>\n",
        "💰 <b>Заработок</b>",
        f"  Всего: <b>{stats['earned_total']} ₸</b>",
        f"  За 30 дней: <b>{stats['earned_month']} ₸</b>",
        f"  Выплачено: <b>{stats['paid_out']} ₸</b>",
        f"  <b>К выплате: {stats['pending']} ₸</b>\n",
        f"📝 Твоя ставка: <b>{pct_str}%</b>",
    ]

    if ref_link:
        lines.append("")
        lines.append("🔗 <b>Твоя реферальная ссылка:</b>")
        lines.append(f"<code>{ref_link}</code>")
        lines.append("")
        lines.append("<i>Копируй и отправляй клиентам. "
                     "Все продажи по ней будут засчитаны тебе автоматически 🎵</i>")

    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    logger.info("Партнёр %d запросил свою статистику.", user.id)
