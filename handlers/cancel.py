"""
Глобальные хэндлеры команд (/menu, /invite, /balance, /cancel, /help)
и колбэков главного меню — доступны в любом состоянии FSM.
"""

import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import get_credits_info, MAX_REFERRAL_BONUS
from keyboards import get_main_menu_keyboard

logger = logging.getLogger(__name__)
router = Router()


MENU_TEXT = (
    "🎵 <b>ПоздравОК — главное меню</b>\n\n"
    "Что хочешь сделать?"
)

HELP_TEXT = (
    "🎵 <b>ПоздравОК — помощь</b>\n\n"
    "Я создаю персональные песни в подарок.\n\n"
    "<b>Команды:</b>\n"
    "/start — начать создание новой песни\n"
    "/menu — главное меню\n"
    "/invite — реферальная ссылка и баланс\n"
    "/balance — мой баланс кредитов\n"
    "/cancel — отменить текущее действие\n"
    "/help — это сообщение\n\n"
    "<b>Как это работает:</b>\n"
    "1️⃣ Выбери жанр и настроение\n"
    "2️⃣ Расскажи о человеке\n"
    "3️⃣ Получи готовый текст и музыку 🎧\n\n"
    "<i>Если что-то пошло не так — нажми /cancel и начни заново.</i>"
)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="HTML")


# ── Главное меню ──────────────────────────────────────────────────────────────

@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    """Показывает главное меню. Не очищает FSM — пользователь может вернуться к диалогу."""
    await message.answer(
        MENU_TEXT,
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(),
    )


# ── Реферальная ссылка / баланс — общие билдеры текста ───────────────────────

def _format_balance_lines(free_available: bool, bonus_credits: int) -> list[str]:
    lines = []
    if free_available:
        lines.append("🎁 Приветственная генерация: <b>1</b>")
    if bonus_credits > 0:
        lines.append(f"⭐ Бонусных кредитов: <b>{bonus_credits}</b>")
    if not lines:
        lines.append("<i>Кредитов нет — пригласи друзей, чтобы получить бонусы 👇</i>")
    return lines


async def _build_invite_text(message_or_callback) -> str:
    """
    Возвращает HTML-текст с балансом и реферальной ссылкой.
    Принимает Message или CallbackQuery — нужен только bot и from_user.
    """
    user_id = message_or_callback.from_user.id
    bot = message_or_callback.bot

    try:
        me = await bot.me()
        ref_link = f"https://t.me/{me.username}?start=ref_{user_id}"
    except Exception as e:
        logger.warning("Не удалось получить username бота: %s", e)
        ref_link = None

    credits = await get_credits_info(user_id)
    balance_lines = _format_balance_lines(
        credits["free_available"], credits["bonus_credits"],
    )

    text = (
        "💌 <b>Приглашай друзей и получай песни в подарок</b>\n\n"
        f"За каждого друга, который зарегистрируется по твоей ссылке, "
        f"тебе начислится <b>+1 бонусный кредит</b>.\n"
        f"Максимум — <b>{MAX_REFERRAL_BONUS}</b> бонусов на одного пользователя.\n\n"
        "<b>Твой баланс:</b>\n"
        + "\n".join(balance_lines)
    )

    if ref_link:
        text += (
            "\n\n<b>Твоя ссылка:</b>\n"
            f"<code>{ref_link}</code>\n\n"
            "<i>Скопируй и отправь друзьям 🎵</i>"
        )
    return text


async def _build_balance_text(user_id: int) -> str:
    """Короткий текст с балансом — для /balance и кнопки 'Мой баланс'."""
    credits = await get_credits_info(user_id)
    balance_lines = _format_balance_lines(
        credits["free_available"], credits["bonus_credits"],
    )
    return "💎 <b>Твой баланс</b>\n\n" + "\n".join(balance_lines)


@router.message(Command("invite"))
async def cmd_invite(message: Message) -> None:
    text = await _build_invite_text(message)
    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)


@router.message(Command("balance"))
async def cmd_balance(message: Message) -> None:
    text = await _build_balance_text(message.from_user.id)
    await message.answer(text, parse_mode="HTML")


# ── Колбэки кнопок главного меню ──────────────────────────────────────────────

@router.callback_query(F.data == "show_invite")
async def on_show_invite(callback: CallbackQuery) -> None:
    text = await _build_invite_text(callback)
    await callback.message.answer(text, parse_mode="HTML", disable_web_page_preview=True)
    await callback.answer()


@router.callback_query(F.data == "show_balance")
async def on_show_balance(callback: CallbackQuery) -> None:
    text = await _build_balance_text(callback.from_user.id)
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()

    if current_state is None:
        await message.answer(
            "Нечего отменять. Нажми /start чтобы создать песню 🎵"
        )
        return

    await state.clear()
    logger.info("Пользователь %d отменил сессию (состояние: %s).", message.from_user.id, current_state)

    await message.answer(
        "✅ Действие отменено.\n\n"
        "Нажми /start чтобы начать заново 🎵"
    )
