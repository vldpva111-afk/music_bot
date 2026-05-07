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

_EDITING_KEY = "is_editing"


@router.callback_query(SongCreation.editing, lambda c: c.data == "edit_song")
async def on_edit_requested(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer(
        "✏️ Напиши, что хочешь изменить в песне:\n\n"
        "<i>Например: «сделай припев веселее», «добавь упоминание котика», «убери слово»</i>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(SongCreation.editing)
async def on_edit_text_received(message: Message, state: FSMContext) -> None:
    data = await state.get_data()

    # Защита от параллельных правок
    if data.get(_EDITING_KEY):
        await message.answer("⏳ Подожди, предыдущие правки ещё обрабатываются...")
        return

    edit_request = message.text.strip()
    if len(edit_request) < 3:
        await message.answer("Напиши подробнее, что именно изменить 🙏")
        return

    original_song = data.get("current_song")
    if not original_song:
        await message.answer("Не могу найти оригинальный текст. Начни сначала — /start")
        return

    await state.update_data(**{_EDITING_KEY: True})
    loading_msg = await message.answer("⏳ Вношу правки в песню...")

    try:
        edited_song = await edit_song(
            original_song=original_song,
            edit_request=edit_request,
            genre=data.get("genre"),
            mood=data.get("mood"),
            voice=data.get("voice"),
        )

        await state.update_data(current_song=edited_song, **{_EDITING_KEY: False})
        await loading_msg.delete()

        await message.answer(
            "🎵 <b>Вот обновлённый текст песни:</b>\n\n"
            f"{edited_song}",
            parse_mode="HTML",
            reply_markup=get_result_keyboard(),
        )
        logger.info("Правки внесены для %d.", message.from_user.id)

    except Exception as e:
        logger.error("Ошибка правок для %d: %s", message.from_user.id, e)
        await state.update_data(**{_EDITING_KEY: False})
        await loading_msg.edit_text("😔 Ошибка при редактировании. Попробуй ещё раз.")
