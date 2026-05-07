"""
Хэндлер выбора жанра.
"""

import logging
from aiogram import Router
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from states import SongCreation
from keyboards import get_mood_keyboard
from constants import GENRE_LABELS, VALID_GENRES

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(SongCreation.genre, lambda c: c.data in VALID_GENRES)
async def on_genre_selected(callback: CallbackQuery, state: FSMContext) -> None:
    genre = callback.data
    await state.update_data(genre=genre)

    label = GENRE_LABELS[genre]

    # Редактируем исходное сообщение с клавиатурой вместо отправки нового —
    # чат не засоряется промежуточными резюме на каждом шаге
    await callback.message.edit_text(
        f"🎵 <b>Жанр:</b> {label}\n\n"
        "😊 Теперь выбери настроение твоей будущей песни:",
        parse_mode="HTML",
        reply_markup=get_mood_keyboard(),
    )

    await state.set_state(SongCreation.mood)
    await callback.answer()
    logger.info("Пользователь %d выбрал жанр: %s", callback.from_user.id, genre)
