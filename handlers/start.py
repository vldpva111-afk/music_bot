"""
Хэндлер /start — отправляет картинку с приветствием и кнопкой «Начать».
"""

import logging
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, URLInputFile
from aiogram.fsm.context import FSMContext

from states import SongCreation
from keyboards import get_start_keyboard, get_genre_keyboard

logger = logging.getLogger(__name__)
router = Router()

# Тематическая картинка (музыка / подарок). Можно заменить на свою,
# положив файл рядом и используя FSInputFile, или вставив другой URL.
WELCOME_IMAGE_URL = "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=800&q=80"

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

    try:
        await message.answer_photo(
            photo=URLInputFile(WELCOME_IMAGE_URL),
            caption=WELCOME_TEXT,
            parse_mode="HTML",
            reply_markup=get_start_keyboard(),
        )
    except Exception:
        # Если картинка недоступна — отправляем просто текст
        await message.answer(
            WELCOME_TEXT,
            parse_mode="HTML",
            reply_markup=get_start_keyboard(),
        )

    await state.set_state(SongCreation.start)
    logger.info(f"Пользователь {message.from_user.id} запустил бота.")


@router.callback_query(lambda c: c.data == "create_song")
async def on_create_song(callback: CallbackQuery, state: FSMContext) -> None:
    """Кнопка «Начать» / «Создать новую песню» — переходим к жанру."""
    await state.clear()

    await callback.message.answer(
        "🎼 Отлично! Давай выберем, в каком жанре будет звучать твоя песня:",
        reply_markup=get_genre_keyboard(),
    )
    await state.set_state(SongCreation.genre)
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} начал создание песни.")
