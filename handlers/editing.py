"""
Хэндлер редактирования готовой песни.

Флоу правок:
  editing → [кнопка "Внести правки"] → awaiting_edit → [текст от юзера] → editing
  editing → [кнопка "Отмена" в awaiting_edit] → editing
"""

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from states import SongCreation
from keyboards import get_result_keyboard, get_cancel_edit_keyboard
from services.openai_service import edit_song, generate_song, RefusalError
from database import log_event, Events

logger = logging.getLogger(__name__)
router = Router()

_EDITING_KEY    = "is_editing"
_REVISIONS_KEY  = "revisions_used"

# Сколько раз за один цикл создания песни юзер может бесплатно
# воспользоваться "Внести правки" + "Сгенерировать заново" суммарно.
# Защита от фарма OpenAI-токенов на одном free-кредите.
# Считаются ТОЛЬКО успешные операции — если OpenAI упал, попытка не списывается.
MAX_REVISIONS_PER_CYCLE = 15


def _format_limit_message(used: int) -> str:
    return (
        f"⚠️ <b>Лимит правок исчерпан</b> ({used} / {MAX_REVISIONS_PER_CYCLE}).\n\n"
        f"Чтобы продолжать улучшать тексты — нажми «Создать песню» с текущим "
        f"вариантом или начни новую песню (потребуется кредит).\n\n"
        f"<i>Лимит сделан, чтобы AI-сервис оставался доступным для всех 🙏</i>"
    )


# ── Кнопка "Внести правки" ────────────────────────────────────────────────────

@router.callback_query(SongCreation.editing, lambda c: c.data == "edit_song")
async def on_edit_requested(callback: CallbackQuery, state: FSMContext) -> None:
    """Переводим в состояние ожидания правок — теперь любое сообщение = правки."""
    # Проверяем лимит ДО того как увести юзера в awaiting_edit —
    # иначе он напечатает свои правки впустую.
    data = await state.get_data()
    used = data.get(_REVISIONS_KEY, 0)
    if used >= MAX_REVISIONS_PER_CYCLE:
        await callback.answer("Лимит правок исчерпан", show_alert=False)
        await callback.message.answer(
            _format_limit_message(used),
            parse_mode="HTML",
            reply_markup=get_result_keyboard(),
        )
        return

    await state.set_state(SongCreation.awaiting_edit)
    await log_event(callback.from_user.id, Events.EDIT_REQUESTED)

    # Подсказка по остатку правок — мягко, чтобы юзер видел сколько у него ещё есть
    remaining = MAX_REVISIONS_PER_CYCLE - used
    hint = f"\n\n<i>Осталось правок: {remaining} из {MAX_REVISIONS_PER_CYCLE}</i>"

    await callback.message.answer(
        "✏️ Напиши, что хочешь изменить в песне:\n\n"
        "<i>Например: «сделай припев веселее», «добавь упоминание котика», «убери слово»</i>"
        + hint,
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

@router.message(SongCreation.awaiting_edit, F.text)
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

    # Доп.проверка лимита — на случай гонки или прямого попадания в awaiting_edit
    used = data.get(_REVISIONS_KEY, 0)
    if used >= MAX_REVISIONS_PER_CYCLE:
        await state.set_state(SongCreation.editing)
        await message.answer(
            _format_limit_message(used),
            parse_mode="HTML",
            reply_markup=get_result_keyboard(),
        )
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

        # Инкремент ТОЛЬКО при успехе — упавшая попытка не списывается
        new_used = used + 1
        await state.update_data(
            current_song=edited_song,
            **{_EDITING_KEY: False, _REVISIONS_KEY: new_used},
        )
        await state.set_state(SongCreation.editing)
        await loading_msg.delete()

        # Если это была последняя правка — сразу предупредим
        footer = ""
        if new_used >= MAX_REVISIONS_PER_CYCLE:
            footer = (
                f"\n\n⚠️ <i>Это была последняя правка "
                f"({new_used}/{MAX_REVISIONS_PER_CYCLE}). "
                f"Лимит исчерпан — теперь только «Создать песню».</i>"
            )
        elif MAX_REVISIONS_PER_CYCLE - new_used <= 3:
            footer = (
                f"\n\n<i>Осталось правок: "
                f"{MAX_REVISIONS_PER_CYCLE - new_used} из {MAX_REVISIONS_PER_CYCLE}</i>"
            )

        await message.answer(
            "🎵 <b>Вот обновлённый текст песни:</b>\n\n"
            f"{edited_song}"
            f"{footer}",
            parse_mode="HTML",
            reply_markup=get_result_keyboard(),
        )
        logger.info(
            "Правки внесены для %d (использовано %d/%d).",
            message.from_user.id, new_used, MAX_REVISIONS_PER_CYCLE,
        )
        await log_event(
            message.from_user.id,
            Events.EDIT_APPLIED,
            {"revisions_used": new_used},
        )

    except RefusalError as e:
        # Модель отказалась во всех попытках. Правки не стоят кредита — refund не нужен.
        # Не инкрементируем счётчик правок — юзер может попробовать ещё.
        logger.warning(
            "OpenAI отказался при правке для %d. raw=%r",
            message.from_user.id, e.raw_text[:200],
        )
        await state.update_data(**{_EDITING_KEY: False})
        await state.set_state(SongCreation.editing)
        await loading_msg.edit_text(
            "🤔 Не получилось внести эти правки. Попробуй сформулировать их иначе.\n\n"
            "Нажми «Внести правки» снова 👇",
        )

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

    # Лимит — общий со списком правок
    used = data.get(_REVISIONS_KEY, 0)
    if used >= MAX_REVISIONS_PER_CYCLE:
        await callback.answer("Лимит правок исчерпан", show_alert=False)
        await callback.message.answer(
            _format_limit_message(used),
            parse_mode="HTML",
            reply_markup=get_result_keyboard(),
        )
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

    await log_event(callback.from_user.id, Events.REGENERATE_CLICKED)
    await state.update_data(**{_EDITING_KEY: True})
    await callback.answer()
    loading_msg = await callback.message.answer("🔄 Генерирую новый вариант песни...")

    try:
        new_song = await generate_song(
            genre=genre, mood=mood, voice=voice, details=details, lang=lang,
        )

        # Инкремент только при успехе
        new_used = used + 1
        await state.update_data(
            current_song=new_song,
            **{_EDITING_KEY: False, _REVISIONS_KEY: new_used},
        )
        await loading_msg.delete()

        # Тот же footer-механизм, что и в правках
        footer = ""
        if new_used >= MAX_REVISIONS_PER_CYCLE:
            footer = (
                f"\n\n⚠️ <i>Это была последняя бесплатная регенерация "
                f"({new_used}/{MAX_REVISIONS_PER_CYCLE}). "
                f"Лимит исчерпан — теперь только «Создать песню».</i>"
            )
        elif MAX_REVISIONS_PER_CYCLE - new_used <= 3:
            footer = (
                f"\n\n<i>Осталось правок/регенераций: "
                f"{MAX_REVISIONS_PER_CYCLE - new_used} из {MAX_REVISIONS_PER_CYCLE}</i>"
            )

        await callback.message.answer(
            "🎵 <b>Новый вариант готов:</b>\n\n"
            f"{new_song}"
            f"{footer}",
            parse_mode="HTML",
            reply_markup=get_result_keyboard(),
        )
        logger.info(
            "Повторная генерация для %d (использовано %d/%d).",
            callback.from_user.id, new_used, MAX_REVISIONS_PER_CYCLE,
        )

    except RefusalError as e:
        # Регенерация тоже не стоит кредита — refund не нужен. Белим без инкремента счётчика.
        logger.warning(
            "OpenAI отказался при регенерации для %d. raw=%r",
            callback.from_user.id, e.raw_text[:200],
        )
        await state.update_data(**{_EDITING_KEY: False})
        await loading_msg.edit_text(
            "🤔 Не получилось сгенерировать новый вариант. "
            "Попробуй внести правки вместо этого 👇",
        )

    except Exception as e:
        logger.error("Ошибка повторной генерации для %d: %s", callback.from_user.id, e)
        await state.update_data(**{_EDITING_KEY: False})
        await loading_msg.edit_text(
            "😔 Ошибка при генерации. Попробуй ещё раз 👇",
        )


# Фоллбэк для не-текстовых сообщений в режиме ожидания правок
@router.message(SongCreation.awaiting_edit)
async def on_edit_non_text(message: Message) -> None:
    await message.answer(
        "Пожалуйста, опиши правки <b>текстом</b> 📝",
        parse_mode="HTML",
        reply_markup=get_cancel_edit_keyboard(),
    )