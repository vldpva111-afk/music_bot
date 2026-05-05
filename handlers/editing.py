"""
Хэндлер редактирования готовой песни.
"""

import logging
from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from states import SongCreation
from keyboards import get_result_keyboard
from services.openai_service import edit_song

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(SongCreation.editing, lambda c: c.data == "edit_song")
async def on_edit_requested(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "✏️ Напиши, что хочешь изменить в песне:\n\n"
        "<i>Например: «сделай припев веселее», «добавь упоминание котика», «убери слово»</i>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(SongCreation.editing)
async def on_edit_text_received(message: Message, state: FSMContext) -> None:
    edit_request = message.text.strip()

    if len(edit_request) < 3:
        await message.answer("Напиши подробнее, что именно изменить 🙏")
        return

    data = await state.get_data()
    original_song = data.get("current_song")

    if not original_song:
        await message.answer("Не могу найти оригинальный текст. Начни сначала — /start")
        return

    loading_msg = await message.answer("⏳ Вношу правки в песню...")

    try:
        edited_song = await edit_song(original_song=original_song, edit_request=edit_request)

        await state.update_data(current_song=edited_song)
        await loading_msg.delete()

        await message.answer(
            "🎵 <b>Вот обновлённый текст песни:</b>\n\n"
            f"{edited_song}",
            parse_mode="HTML",
            reply_markup=get_result_keyboard(),
        )
        logger.info(f"Правки внесены для {message.from_user.id}.")

    except Exception as e:
        logger.error(f"Ошибка правок для {message.from_user.id}: {e}")
        await loading_msg.edit_text("😔 Ошибка при редактировании. Попробуй ещё раз.")
