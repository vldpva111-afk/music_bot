"""
Хэндлер выбора настроения.
"""

import logging
from aiogram import Router
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from states import SongCreation
from keyboards import get_voice_keyboard
from constants import GENRE_LABELS, MOOD_LABELS, VALID_MOODS

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(SongCreation.mood, lambda c: c.data in VALID_MOODS)
async def on_mood_selected(callback: CallbackQuery, state: FSMContext) -> None:
    mood = callback.data
    await state.update_data(mood=mood)

    data = await state.get_data()
    genre_label = GENRE_LABELS.get(data.get("genre", ""), "")
    mood_label  = MOOD_LABELS[mood]

    await callback.message.edit_text(
        f"🎵 <b>Жанр:</b> {genre_label}\n"
        f"🎭 <b>Настроение:</b> {mood_label}\n\n"
        "🎤 Каким голосом ты хочешь песню?",
        parse_mode="HTML",
        reply_markup=get_voice_keyboard(),
    )

    await state.set_state(SongCreation.voice)
    await callback.answer()
    logger.info("Пользователь %d выбрал настроение: %s", callback.from_user.id, mood)
