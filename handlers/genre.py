"""
Хэндлер выбора жанра.
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


@router.callback_query(SongCreation.genre, lambda c: c.data in VALID_GENRES)
async def on_genre_selected(callback: CallbackQuery, state: FSMContext) -> None:
    """Пользователь выбрал жанр — сохраняем и переходим к настроению."""
    await state.update_data(genre=callback.data)

    await callback.message.edit_text(
        "Какого настроения ты хочешь песню? 🎭",
        reply_markup=get_mood_keyboard(),
    )
    await state.set_state(SongCreation.mood)
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} выбрал жанр: {callback.data}")
