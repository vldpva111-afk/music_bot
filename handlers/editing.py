"""
Хэндлер редактирования готовой песни.
Обрабатывает нажатие 'Внести правки' и новый текст пользователя.
"""

import logging
from datetime import datetime
from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from states import SongCreation
from keyboards import get_result_keyboard
from services.openai_service import edit_song

logger = logging.getLogger(__name__)
router = Router()
user_limits = {}


@router.callback_query(SongCreation.editing, lambda c: c.data == "edit_song")
async def on_edit_requested(callback: CallbackQuery, state: FSMContext) -> None:
    """Пользователь нажал 'Внести правки' — просим написать что изменить."""
    await callback.message.answer(
        "✏️ Напиши, что хочешь изменить в песне:\n\n"
        "Например: «сделай припев веселее», «добавь упоминание кота», «убери последний куплет»"
    )
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} хочет внести правки.")


@router.message(SongCreation.editing)
async def on_edit_text_received(message: Message, state: FSMContext) -> None:
    """
    Пользователь написал пожелания по правкам.
    Отправляем в OpenAI с контекстом оригинальной песни.
    """
    # 🔥 ЛИМИТ ПРАВОК
    user_id = message.from_user.id
    today = datetime.now().date()

    if user_id not in user_limits:
        user_limits[user_id] = {
            "date": today,
            "create_count": 0,
            "edit_count": 0
        }

    if user_limits[user_id]["date"] != today:
        user_limits[user_id] = {
            "date": today,
            "create_count": 0,
            "edit_count": 0
        }

    if user_limits[user_id]["edit_count"] >= 5:
        await message.answer("❌ Лимит правок на сегодня (5) исчерпан. Попробуй завтра 🎵")
        return

    edit_request = message.text.strip()

    if len(edit_request) < 3:
        await message.answer("Напиши подробнее, что именно изменить 🙏")
        return

    data = await state.get_data()
    original_song = data.get("current_song")

    if not original_song:
        await message.answer(
            "Не могу найти оригинальный текст песни. Давай начнём сначала — нажми /start"
        )
        return

    loading_msg = await message.answer("⏳ Вношу правки в песню...")

    logger.info(f"Редактируем песню для пользователя {message.from_user.id}.")

    try:
        edited_song = await edit_song(
            original_song=original_song,
            edit_request=edit_request,
        )

        # Обновляем текущую версию песни в состоянии
        await state.update_data(current_song=edited_song)

        await loading_msg.delete()

        await message.answer(
            "🎵 Вот обновлённый текст песни:\n\n" + edited_song,
            reply_markup=get_result_keyboard(),
        )
        logger.info(f"Правки успешно внесены для пользователя {message.from_user.id}.")

    except Exception as e:
        logger.error(f"Ошибка редактирования для пользователя {message.from_user.id}: {e}")
        await loading_msg.edit_text(
            "😔 Произошла ошибка при редактировании. Попробуй написать правки ещё раз."
        )
