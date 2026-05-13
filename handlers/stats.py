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
    get_pending_orders,
    mark_latest_order_paid,
    log_event,
    Events,
    add_partner,
    remove_partner,
    get_partner,
    get_partner_stats,
    list_partner_stats,
    record_partner_payout,
)
from constants import PACKAGES

# Дефолтный % комиссии для новых партнёров (если не указан явно при /partner_add)
DEFAULT_PARTNER_PCT = 30.0


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

        "👥 <b>Пользователи (новые регистрации)</b>\n"
        f"  Всего: {stats['users_total']}\n"
        f"  Сегодня: {stats['users_today']}\n"
        f"  За 7 дней: {stats['users_week']}\n\n"

        "🔥 <b>Активность (уникальные юзеры)</b>\n"
        f"  Сегодня: <b>{stats['active_today']}</b> "
        f"(новых: {stats['active_new_today']}, "
        f"вернулось: {stats['active_returning_today']})\n"
        f"  Вчера: {stats['active_yesterday']}\n"
        f"  За 7 дней: {stats['active_week']}\n"
        f"  За 30 дней: {stats['active_month']}\n\n"

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

    # Автоматически закрываем последний pending-заказ юзера, если он был.
    # Это превращает /grant в полноценный «подтверди оплату»: одна команда —
    # и кредиты начислены, и заказ помечен paid в БД (для статистики).
    closed_order = await mark_latest_order_paid(target_id)

    order_note = ""
    if closed_order:
        order_note = (
            f"\n\n📦 <b>Закрыт заказ #{closed_order['id']}</b> "
            f"({closed_order['credits']} кр. за {closed_order['price']} ₸)"
        )
        await log_event(
            target_id,
            Events.ORDER_PAID,
            {
                "order_id":  closed_order["id"],
                "package":   closed_order["package_key"],
                "price":     closed_order["price"],
                "credits":   closed_order["credits"],
            },
        )

    await message.answer(
        f"✅ Выдано <b>{amount}</b> бонусных кредитов пользователю "
        f"<code>{target_id}</code>.\n"
        f"Новый баланс бонусов: <b>{new_balance}</b>"
        f"{order_note}",
        parse_mode="HTML",
    )
    logger.info(
        "Админ %d выдал %d кредитов пользователю %d (новый баланс: %d, "
        "закрыт заказ: %s).",
        message.from_user.id, amount, target_id, new_balance,
        closed_order["id"] if closed_order else None,
    )

    # Уведомляем получателя — best effort, не падаем если он заблокировал бота.
    # Текст разный в зависимости от того был ли это платный заказ или просто подарок.
    if closed_order:
        notify_text = (
            f"🎉 <b>Оплата получена!</b>\n\n"
            f"Тебе зачислено <b>{amount}</b> "
            f"кредит{'' if amount == 1 else 'ов'} на создание песни.\n\n"
            f"Спасибо за покупку! 🎵\n"
            f"Жми /menu чтобы создать новую песню."
        )
    else:
        notify_text = (
            f"🎁 Тебе начислено <b>{amount}</b> "
            f"бонус{'ный кредит' if amount == 1 else 'ных кредитов'} "
            f"на создание песни!\n\n"
            f"Используй их через /menu или /start 🎵"
        )
    try:
        await message.bot.send_message(
            target_id,
            notify_text,
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


# ── /orders — список pending-заказов ──────────────────────────────────────────

@router.message(Command("orders"))
async def cmd_orders(message: Message) -> None:
    """Показывает все необработанные заказы — для удобства, если алерт пропустил."""
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    orders = await get_pending_orders(limit=20)

    if not orders:
        await message.answer("✅ Нет необработанных заказов.")
        return

    lines = [f"📋 <b>Pending заказов: {len(orders)}</b>\n"]
    for o in orders:
        pkg_label = PACKAGES.get(o["package_key"], {}).get("label", o["package_key"])
        username_str = f"@{o['username']}" if o["username"] else "—"
        created_str = o["created_at"].strftime("%d.%m %H:%M")

        lines.append(
            f"\n<b>#{o['id']}</b> · {created_str}\n"
            f"  {username_str} ({o['first_name'] or '—'})\n"
            f"  📦 {pkg_label} — <b>{o['price']} ₸</b>\n"
            f"  📱 <code>{o['phone']}</code>\n"
            f"  👉 <code>/grant {o['telegram_id']} {o['credits']}</code>"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")


# ── Партнёрская программа (админские команды) ─────────────────────────────────

PARTNER_ADD_USAGE = (
    "<b>Использование:</b>\n"
    "<code>/partner_add &lt;user_id|@username&gt; [имя] [процент]</code>\n\n"
    "Примеры:\n"
    "<code>/partner_add 123456789</code> — добавит с дефолтом 30%\n"
    "<code>/partner_add @aidar Айдар</code> — с именем\n"
    "<code>/partner_add @aidar Айдар 35</code> — с именем и ставкой\n"
    "<code>/partner_add 123 35.5</code> — без имени, дробная ставка\n\n"
    "Повторный вызов <b>обновляет</b> имя и процент."
)


def _format_pct(pct: float) -> str:
    """Красиво форматирует процент: 30.00 → 30, 27.50 → 27.5."""
    if pct == int(pct):
        return f"{int(pct)}"
    s = f"{pct:.2f}".rstrip("0").rstrip(".")
    return s


@router.message(Command("partner_add"))
async def cmd_partner_add(message: Message, command: CommandObject) -> None:
    """Добавить / обновить партнёра."""
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    args = (command.args or "").split()
    if not args:
        await message.answer(PARTNER_ADD_USAGE, parse_mode="HTML")
        return

    target_arg = args[0]
    rest = args[1:]

    # Последний аргумент — это процент, если похож на число
    pct = DEFAULT_PARTNER_PCT
    name_parts: list[str] = rest
    if rest:
        try:
            candidate = float(rest[-1])
            if 0 < candidate <= 100:
                pct = candidate
                name_parts = rest[:-1]
        except ValueError:
            pass  # последнее слово не число — это часть имени

    display_name = " ".join(name_parts) if name_parts else None

    target_id, err = await _resolve_target(target_arg)
    if err:
        await message.answer(f"❌ {err}")
        return

    ok = await add_partner(target_id, display_name, pct)
    if not ok:
        await message.answer(
            f"❌ Пользователь <code>{target_id}</code> не найден в базе.\n"
            f"Он должен сначала запустить бота хотя бы раз.",
            parse_mode="HTML",
        )
        return

    name_str = f"<b>{display_name}</b> " if display_name else ""
    await message.answer(
        f"✅ Партнёр {name_str}<code>{target_id}</code> добавлен.\n"
        f"Комиссия: <b>{_format_pct(pct)}%</b>\n\n"
        f"Передай ему ссылку и попроси выполнить /me_partner в боте.",
        parse_mode="HTML",
    )
    logger.info(
        "Админ %d добавил партнёра %d (имя=%r, pct=%s).",
        message.from_user.id, target_id, display_name, pct,
    )

    # Уведомим самого партнёра, если возможно
    try:
        await message.bot.send_message(
            target_id,
            f"🎉 Тебя добавили в <b>партнёрскую программу ПоздравОК</b>!\n\n"
            f"Твоя комиссия: <b>{_format_pct(pct)}%</b> с каждой продажи.\n"
            f"Команда <b>/me_partner</b> — твоя статистика и реферальная ссылка.",
            parse_mode="HTML",
        )
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logger.info("Не удалось уведомить нового партнёра %d: %s", target_id, e)


@router.message(Command("partner_remove"))
async def cmd_partner_remove(message: Message, command: CommandObject) -> None:
    """Убрать юзера из партнёров (статистика сохраняется в payouts/orders)."""
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    arg = (command.args or "").strip()
    if not arg:
        await message.answer(
            "Использование: <code>/partner_remove &lt;user_id|@username&gt;</code>",
            parse_mode="HTML",
        )
        return

    target_id, err = await _resolve_target(arg)
    if err:
        await message.answer(f"❌ {err}")
        return

    removed = await remove_partner(target_id)
    if removed:
        await message.answer(
            f"✅ Партнёр <code>{target_id}</code> удалён.",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"⚠️ Пользователь <code>{target_id}</code> не был партнёром.",
            parse_mode="HTML",
        )


@router.message(Command("partner_stats"))
async def cmd_partner_stats(message: Message) -> None:
    """Сводка по всем партнёрам с pending-выплатами."""
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    stats_list = await list_partner_stats()
    if not stats_list:
        await message.answer(
            "📋 Пока нет ни одного партнёра.\n\n"
            "Добавить: <code>/partner_add &lt;user_id|@username&gt;</code>",
            parse_mode="HTML",
        )
        return

    total_pending = sum(s["pending"] for s in stats_list)
    total_paid_out = sum(s["paid_out"] for s in stats_list)

    lines = [f"📋 <b>Партнёров: {len(stats_list)}</b>\n"]
    for s in stats_list:
        name = s["display_name"] or f"<code>{s['telegram_id']}</code>"
        pct = _format_pct(s["commission_pct"])

        lines.append(
            f"\n⭐ <b>{name}</b> · {pct}% · <code>{s['telegram_id']}</code>\n"
            f"  Привёл: {s['clients_total']} · Купили: {s['clients_paid']}\n"
            f"  Заработал: <b>{s['earned_total']} ₸</b> "
            f"(за 30 дн: {s['earned_month']} ₸)\n"
            f"  Выплачено: {s['paid_out']} ₸ · "
            f"<b>К выплате: {s['pending']} ₸</b>\n"
            f"  👉 <code>/partner_paid {s['telegram_id']} {s['pending']}</code>"
        )

    lines.append(
        f"\n━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Всего к выплате: {total_pending} ₸</b>\n"
        f"📤 Всего выплачено: {total_paid_out} ₸"
    )

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("partner_paid"))
async def cmd_partner_paid(message: Message, command: CommandObject) -> None:
    """Зафиксировать факт выплаты партнёру."""
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    args = (command.args or "").split(maxsplit=2)
    if len(args) < 2:
        await message.answer(
            "<b>Использование:</b>\n"
            "<code>/partner_paid &lt;user_id|@username&gt; &lt;сумма&gt; [комментарий]</code>\n\n"
            "Пример: <code>/partner_paid @aidar 1500 за май</code>",
            parse_mode="HTML",
        )
        return

    target_arg, amount_str = args[0], args[1]
    comment = args[2] if len(args) > 2 else None

    try:
        amount = int(amount_str)
    except ValueError:
        await message.answer("❌ Сумма должна быть целым числом тенге.")
        return

    if amount <= 0:
        await message.answer("❌ Сумма должна быть положительной.")
        return

    target_id, err = await _resolve_target(target_arg)
    if err:
        await message.answer(f"❌ {err}")
        return

    payout_id = await record_partner_payout(target_id, amount, comment)
    if payout_id is None:
        await message.answer(
            f"❌ <code>{target_id}</code> не партнёр. "
            f"Сначала добавь через /partner_add.",
            parse_mode="HTML",
        )
        return

    # Обновлённая статистика после выплаты
    stats = await get_partner_stats(target_id)
    pending_str = f"{stats['pending']} ₸" if stats else "?"

    await message.answer(
        f"✅ Записана выплата #{payout_id}\n"
        f"Партнёру <code>{target_id}</code>: <b>{amount} ₸</b>\n"
        f"{'Комментарий: <i>' + comment + '</i>' if comment else ''}\n\n"
        f"Остаток к выплате: <b>{pending_str}</b>",
        parse_mode="HTML",
    )
    logger.info(
        "Админ %d записал выплату %d партнёру %d (сумма=%d, comment=%r).",
        message.from_user.id, payout_id, target_id, amount, comment,
    )

    # Уведомим партнёра — best effort
    try:
        await message.bot.send_message(
            target_id,
            f"💸 <b>Выплата получена</b>\n\n"
            f"Тебе зачислено: <b>{amount} ₸</b>\n"
            f"{'<i>' + comment + '</i>' if comment else ''}\n\n"
            f"Подробности — команда /me_partner",
            parse_mode="HTML",
        )
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logger.info("Не удалось уведомить партнёра %d о выплате: %s", target_id, e)
