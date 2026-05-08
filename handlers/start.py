"""
Хэндлер /start — отправляет картинку с приветствием и кнопкой «Начать».
"""

import logging

from aiogram import Router, Bot
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery, URLInputFile
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from states import SongCreation
from keyboards import get_start_keyboard, get_genre_keyboard
from database import upsert_user, apply_referral_bonus, MAX_REFERRAL_BONUS, log_event, Events
from config import settings

logger = logging.getLogger(__name__)
router = Router()

WELCOME_IMAGE_URL = settings.WELCOME_IMAGE_URL

WELCOME_TEXT = (
    "🎁 <b>Привет! Я ПоздравОК</b>\n\n"
    "Помогу тебе создать уникальный музыкальный подарок — "
    "персональную песню для любого случая:\n\n"
    "🎂 поздравление с днём рождения\n"
    "💖 признание в любви\n"
    "😂 шутливый трек для друга\n"
    "🎓 поздравление с окончанием учёбы\n\n"
    "Всего за несколько минут я создам <b>уникальную песню</b> "
    "именно для твоего человека 🎵\n\n"
    "Нажми <b>«Начать»</b> — и поехали!"
)


def _parse_referrer_id(args: str | None, self_id: int) -> int | None:
    """
    Парсит параметр deep-link /start.
    Поддерживает формы: 'ref_12345' и просто '12345'.
    Возвращает None если формат не распознан или это self-referral.
    """
    if not args:
        return None
    raw = args.strip()
    if raw.startswith("ref_"):
        raw = raw[4:]
    if not raw.isdigit():
        return None
    referrer_id = int(raw)
    if referrer_id == self_id:
        return None
    return referrer_id


async def _notify_referrer(bot: Bot, referrer_id: int, new_user_name: str | None) -> None:
    """Сообщает пригласившему о начисленном бонусе. Best-effort."""
    name = new_user_name or "Новый пользователь"
    try:
        await bot.send_message(
            referrer_id,
            f"🎉 По твоей ссылке зарегистрировался <b>{name}</b>!\n"
            f"Тебе начислен +1 бонусный кредит на генерацию песни 🎵",
            parse_mode="HTML",
        )
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logger.info("Не удалось уведомить реферера %d: %s", referrer_id, e)


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    command: CommandObject,
) -> None:
    await state.clear()

    user = message.from_user
    referrer_id = _parse_referrer_id(command.args, self_id=user.id)

    is_new = await upsert_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        referred_by=referrer_id if referrer_id else None,
    )

    # Бонус начисляем только при первой регистрации по ссылке —
    # повторные /start с ?start=ref_... ничего не дают.
    if is_new and referrer_id:
        bonus_applied = await apply_referral_bonus(referrer_id)
        if bonus_applied:
            logger.info("Реферальный бонус начислен пользователю %d (приглашённый: %d).",
                        referrer_id, user.id)
            await _notify_referrer(message.bot, referrer_id, user.first_name)
        else:
            logger.info("Реферальный лимит (%d) для %d уже достигнут.",
                        MAX_REFERRAL_BONUS, referrer_id)

    try:
        await message.answer_photo(
            photo=URLInputFile(WELCOME_IMAGE_URL),
            caption=WELCOME_TEXT,
            parse_mode="HTML",
            reply_markup=get_start_keyboard(),
        )
    except Exception:
        await message.answer(
            WELCOME_TEXT,
            parse_mode="HTML",
            reply_markup=get_start_keyboard(),
        )

    logger.info("Пользователь %d запустил бота.", user.id)
    await log_event(
        user.id,
        Events.BOT_STARTED,
        {"is_new": is_new, "referrer": referrer_id},
    )


@router.callback_query(lambda c: c.data == "create_song")
async def on_create_song(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Кнопка «🎵 Новая песня» из главного меню — работает в любом состоянии,
    т.к. начало нового флоу всегда сбрасывает FSM.
    """
    await state.clear()
    await log_event(callback.from_user.id, Events.FLOW_STARTED)

    await callback.message.answer(
        "🎼 Отлично! Давай выберем, в каком жанре будет звучать твоя песня:",
        reply_markup=get_genre_keyboard(),
    )
    await state.set_state(SongCreation.genre)
    await callback.answer()
    logger.info("Пользователь %d начал создание песни.", callback.from_user.id)