"""
Хэндлер выбора настроения.
"""

import logging
from aiogram import Router
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from states import SongCreation
from keyboards import get_voice_keyboard

logger = logging.getLogger(__name__)
router = Router()

VALID_MOODS = {"mood_happy", "mood_sad", "mood_calm", "mood_love"}

MOOD_LABELS = {
    "mood_happy": "😄 Радостное",
    "mood_sad":   "😢 Грустное",
    "mood_calm":  "😌 Спокойное",
    "mood_love":  "❤️ Любовное",
}

GENRE_LABELS = {
    "genre_rap":     "🎤 Рэп/хип-хоп",
    "genre_pop":     "🎶 Поп",
    "genre_rock":    "🎸 Рок",
    "genre_chanson": "🎻 Шансон",
    "genre_disco":   "🕺 Диско 80-х",
    "genre_classic": "🎼 Классика",
}


@router.callback_query(SongCreation.mood, lambda c: c.data in VALID_MOODS)
async def on_mood_selected(callback: CallbackQuery, state: FSMContext) -> None:
    mood = callback.data
    await state.update_data(mood=mood)

    data = await state.get_data()
    genre_label = GENRE_LABELS.get(data.get("genre", ""), "")
    mood_label = MOOD_LABELS[mood]

    # Резюме
    await callback.message.answer(
        f"🎵 <b>Жанр песни:</b> {genre_label}\n"
        f"🎭 <b>Настроение:</b> {mood_label}",
        parse_mode="HTML",
    )

    # Следующий шаг
    await callback.message.answer(
        "🎤 Каким голосом ты хочешь песню?",
        reply_markup=get_voice_keyboard(),
    )

    await state.set_state(SongCreation.voice)
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} выбрал настроение: {mood}")
