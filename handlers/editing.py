"""
Хэндлер редактирования готовой песни.

Флоу правок:
  editing → [кнопка "Внести правки"] → awaiting_edit → [текст от юзера] → editing
  editing → [кнопка "Отмена" в awaiting_edit] → editing
"""

import logging

from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from states import SongCreation
from keyboards import get_result_keyboard, get_cancel_edit_keyboard
from services.openai_service import edit_song, generate_song

logger = logging.getLogger(__name__)
router = Router()

_EDITING_KEY = "is_editing"


# ── Кнопка "Внести правки" ────────────────────────────────────────────────────

@router.callback_query(SongCreation.editing, lambda c: c.data == "edit_song")
async def on_edit_requested(callback: CallbackQuery, state: FSMContext) -> None:
    """Переводим в состояние ожидания правок — теперь любое сообщение = правки."""
    await state.set_state(SongCreation.awaiting_edit)
    await callback.message.answer(
        "✏️ Напиши, что хочешь изменить в песне:\n\n"
        "<i>Например: «сделай припев веселее», «добавь упоминание котика», «убери слово»</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_edit_keyboard(),
    )
    await callback.answer()


# ── Кнопка "Отмена" во время ожидания правок ──────────────────────────────────

@router.callback_query(SongCreation.awaiting_edit, lambda c: c.data == "cancel_edit")
async def on_cancel_edit(callback: CallbackQuery, state: FSMContext) -> None:
    """Возвращаем обратно к просмотру текста без изменений."""
    await state.set_state(SongCreation.editing)
    data = await state.get_data()
    song_text = data.get("current_song", "")

    await callback.message.answer(
        "↩️ Правки отменены. Текст без изменений:\n\n"
        f"{song_text}",
        parse_mode="HTML",
        reply_markup=get_result_keyboard(),
    )
    await callback.answer()


# ── Получаем текст правок ─────────────────────────────────────────────────────

@router.message(SongCreation.awaiting_edit)
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
        await state.set_state(SongCreation.editing)
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
        await state.set_state(SongCreation.editing)
        await loading_msg.edit_text(
            "😔 Ошибка при редактировании. Попробуй ещё раз.\n\n"
            "Нажми «Внести правки» снова 👇",
        )


# ── Кнопка "Сгенерировать заново" ────────────────────────────────────────────

@router.callback_query(SongCreation.editing, lambda c: c.data == "regenerate_song")
async def on_regenerate(callback: CallbackQuery, state: FSMContext) -> None:
    """Генерирует новый вариант текста с теми же параметрами, без правок."""
    data = await state.get_data()

    # Защита от параллельных запросов
    if data.get(_EDITING_KEY):
        await callback.answer("⏳ Подожди, ещё обрабатываю...", show_alert=False)
        return

    genre   = data.get("genre",  "genre_pop")
    mood    = data.get("mood",   "mood_happy")
    voice   = data.get("voice",  "voice_male")
    lang    = data.get("lang",   "ru")
    details = data.get("last_details", "")  # подробнее ниже

    if not details:
        await callback.answer(
            "Не могу найти детали для повторной генерации. Попробуй /start",
            show_alert=True,
        )
        return

    await state.update_data(**{_EDITING_KEY: True})
    await callback.answer()
    loading_msg = await callback.message.answer("🔄 Генерирую новый вариант песни...")

    try:
        new_song = await generate_song(
            genre=genre, mood=mood, voice=voice, details=details, lang=lang,
        )

        await state.update_data(current_song=new_song, **{_EDITING_KEY: False})
        await loading_msg.delete()

        await callback.message.answer(
            "🎵 <b>Новый вариант готов:</b>\n\n"
            f"{new_song}",
            parse_mode="HTML",
            reply_markup=get_result_keyboard(),
        )
        logger.info("Повторная генерация для %d.", callback.from_user.id)

    except Exception as e:
        logger.error("Ошибка повторной генерации для %d: %s", callback.from_user.id, e)
        await state.update_data(**{_EDITING_KEY: False})
        await loading_msg.edit_text(
            "😔 Ошибка при генерации. Попробуй ещё раз 👇",
        )