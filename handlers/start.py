"""
Хэндлер /start — отправляет картинку с приветствием и кнопкой «Начать».
"""

import logging

from aiogram import Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.state import default_state
from aiogram.types import Message, CallbackQuery, URLInputFile
from aiogram.fsm.context import FSMContext

from states import SongCreation
from keyboards import get_start_keyboard, get_genre_keyboard
from database import upsert_user
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


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()

    user = message.from_user
    await upsert_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

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


@router.callback_query(
    StateFilter(default_state, SongCreation.genre),
    lambda c: c.data == "create_song",
)
async def on_create_song(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Кнопка «Начать» / «Создать новую песню».
    Принимается только из начального состояния или со шага выбора жанра —
    чтобы не сбрасывать FSM посередине уже начатого флоу.
    """
    await state.clear()

    await callback.message.answer(
        "🎼 Отлично! Давай выберем, в каком жанре будет звучать твоя песня:",
        reply_markup=get_genre_keyboard(),
    )
    await state.set_state(SongCreation.genre)
    await callback.answer()
    logger.info("Пользователь %d начал создание песни.", callback.from_user.id)