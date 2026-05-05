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

VOICE_LABELS = {
    "voice_male":   "👨 Мужской",
    "voice_female": "👩 Женский",
}

GENRE_LABELS = {
    "genre_rap":     "🎤 Рэп/хип-хоп",
    "genre_pop":     "🎶 Поп",
    "genre_rock":    "🎸 Рок",
    "genre_chanson": "🎻 Шансон",
    "genre_disco":   "🕺 Диско 80-х",
    "genre_classic": "🎼 Классика",
}

MOOD_LABELS = {
    "mood_happy": "😄 Радостное",
    "mood_sad":   "😢 Грустное",
    "mood_calm":  "😌 Спокойное",
    "mood_love":  "❤️ Любовное",
}

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

    # Резюме
    await callback.message.answer(
        f"🎵 <b>Жанр песни:</b> {genre_label}\n"
        f"🎭 <b>Настроение:</b> {mood_label}\n"
        f"🎤 <b>Голос:</b> {voice_label}",
        parse_mode="HTML",
    )

    # Следующий шаг — детали
    await callback.message.answer(
        DETAILS_TEXT,
        parse_mode="HTML",
        reply_markup=get_details_keyboard("ru"),
    )

    await state.set_state(SongCreation.details)
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} выбрал голос: {voice}")
