"""
Хэндлер выбора голоса исполнителя.
"""

import logging
from aiogram import Router
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from states import SongCreation
from keyboards import get_details_keyboard

logger = logging.getLogger(__name__)
router = Router()

VALID_VOICES = {"voice_male", "voice_female"}


@router.callback_query(SongCreation.voice, lambda c: c.data in VALID_VOICES)
async def on_voice_selected(callback: CallbackQuery, state: FSMContext) -> None:
    """Пользователь выбрал голос — сохраняем и просим ввести детали."""
    await state.update_data(voice=callback.data)

    text = (
        "Напиши несколько деталей о человеке, по которым я создам для тебя песню:\n\n"
        "• Как зовут?\n"
        "• Чем занимается?\n"
        "• Основные детали внешности?\n"
        "• Совместные истории?\n"
        "• Ты можешь написать что-то своё.\n\n"
        "• Пример: Александр, Работает электриком, добрый, любимый папа, хочу поздравить с днем рождения.\n\n"
        "✍️ Просто напиши всё в одном сообщении!"
    )

    await callback.message.edit_text(text, reply_markup=get_details_keyboard())
    await state.set_state(SongCreation.details)
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} выбрал голос: {callback.data}")
