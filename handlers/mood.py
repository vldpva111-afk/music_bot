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


@router.callback_query(SongCreation.mood, lambda c: c.data in VALID_MOODS)
async def on_mood_selected(callback: CallbackQuery, state: FSMContext) -> None:
    """Пользователь выбрал настроение — сохраняем и переходим к голосу."""
    await state.update_data(mood=callback.data)

    await callback.message.edit_text(
        "Каким голосом ты хочешь песню? 🎤",
        reply_markup=get_voice_keyboard(),
    )
    await state.set_state(SongCreation.voice)
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} выбрал настроение: {callback.data}")
