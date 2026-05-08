"""
Хэндлер выбора голоса исполнителя.
"""

import logging
from aiogram import Router
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from states import SongCreation
from keyboards import get_details_keyboard, get_voice_keyboard
from constants import GENRE_LABELS, MOOD_LABELS, VOICE_LABELS, VALID_VOICES

logger = logging.getLogger(__name__)
router = Router()

DETAILS_TEXT = (
    "✍️ Напиши несколько деталей о человеке, "
    "по которым я создам для тебя песню:\n\n"
    "• Как зовут?\n"
    "• Чем занимается?\n"
    "• Основные детали внешности?\n"
    "• Совместные истории?\n"
    "• Что-то своё.\n\n"
    "<i>Пример: Александр, работает электриком, добрый, "
    "любимый папа, хочу поздравить с днём рождения.</i>\n\n"
    "Просто напиши всё в одном сообщении 👇"
)


@router.callback_query(SongCreation.voice, lambda c: c.data in VALID_VOICES)
async def on_voice_selected(callback: CallbackQuery, state: FSMContext) -> None:
    voice = callback.data
    await state.update_data(voice=voice, lang="ru")  # язык по умолчанию — русский

    data = await state.get_data()
    genre_label = GENRE_LABELS.get(data.get("genre", ""), "")
    mood_label  = MOOD_LABELS.get(data.get("mood", ""), "")
    voice_label = VOICE_LABELS[voice]

    await callback.message.edit_text(
        f"🎵 <b>Жанр:</b> {genre_label}\n"
        f"🎭 <b>Настроение:</b> {mood_label}\n"
        f"🎤 <b>Голос:</b> {voice_label}\n\n"
        f"{DETAILS_TEXT}",
        parse_mode="HTML",
        reply_markup=get_details_keyboard("ru"),
    )

    await state.set_state(SongCreation.details)
    await callback.answer()
    logger.info("Пользователь %d выбрал голос: %s", callback.from_user.id, voice)


# ── Назад: детали → голос ────────────────────────────────────────────────────

@router.callback_query(SongCreation.details, lambda c: c.data == "back_to_voice")
async def on_back_to_voice(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    genre_label = GENRE_LABELS.get(data.get("genre", ""), "")
    mood_label  = MOOD_LABELS.get(data.get("mood", ""), "")

    await state.set_state(SongCreation.voice)
    await callback.message.edit_text(
        f"🎵 <b>Жанр:</b> {genre_label}\n"
        f"🎭 <b>Настроение:</b> {mood_label}\n\n"
        "🎤 Каким голосом ты хочешь песню?",
        parse_mode="HTML",
        reply_markup=get_voice_keyboard(),
    )
    await callback.answer()
    logger.info("Пользователь %d вернулся к выбору голоса.", callback.from_user.id)