"""
Хэндлер выбора жанра.
После выбора показывает резюме и предлагает выбрать настроение.
"""

import logging
from aiogram import Router
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from states import SongCreation
from keyboards import get_mood_keyboard

logger = logging.getLogger(__name__)
router = Router()

VALID_GENRES = {"genre_rap", "genre_pop", "genre_rock", "genre_chanson", "genre_disco", "genre_classic"}

GENRE_LABELS = {
    "genre_rap":     "🎤 Рэп/хип-хоп",
    "genre_pop":     "🎶 Поп",
    "genre_rock":    "🎸 Рок",
    "genre_chanson": "🎻 Шансон",
    "genre_disco":   "🕺 Диско 80-х",
    "genre_classic": "🎼 Классика",
}


@router.callback_query(SongCreation.genre, lambda c: c.data in VALID_GENRES)
async def on_genre_selected(callback: CallbackQuery, state: FSMContext) -> None:
    genre = callback.data
    await state.update_data(genre=genre)

    label = GENRE_LABELS[genre]

    # Резюме выбора
    await callback.message.answer(f"🎵 <b>Жанр песни:</b> {label}")

    # Следующий шаг
    await callback.message.answer(
        "😊 Теперь выбери настроение твоей будущей песни:",
        reply_markup=get_mood_keyboard(),
    )

    await state.set_state(SongCreation.mood)
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} выбрал жанр: {genre}")
