"""
Хэндлер ввода деталей и генерации песни.
Здесь происходит основной вызов OpenAI API.
"""

import logging
from datetime import datetime

from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from states import SongCreation
from keyboards import get_details_keyboard, get_result_keyboard
from services.openai_service import generate_song

logger = logging.getLogger(__name__)
router = Router()
user_limits = {}

@router.callback_query(SongCreation.details, lambda c: c.data == "lang_ru")
async def on_lang_selected(callback: CallbackQuery) -> None:
    """Пользователь нажал кнопку выбора языка — язык уже русский, просто уведомляем."""
    await callback.answer("✅ Язык: Русский. Напишите детали о человеке!", show_alert=False)


@router.callback_query(SongCreation.details, lambda c: c.data == "own_text")
async def on_own_text(callback: CallbackQuery, state: FSMContext) -> None:
    """Пользователь хочет вставить свой готовый текст."""
    await callback.message.edit_text(
        "Отлично! Напиши свой текст песни, и я его немного доработаю. ✍️"
    )
    await callback.answer()


@router.message(SongCreation.details)
async def on_details_entered(message: Message, state: FSMContext) -> None:
    print("HANDLER START:", message.from_user.id)
    """
    Пользователь ввёл детали о человеке.
    Запускаем генерацию песни через OpenAI.

    """
    # 🔥 ЛИМИТ В ДЕНЬ

    user_id = message.from_user.id

    today = datetime.now().date()

    if user_id not in user_limits:

        user_limits[user_id] = {"date": today, "count": 0}

    if user_limits[user_id]["date"] != today:

        user_limits[user_id] = {"date": today, "count": 0}

    if user_limits[user_id]["count"] >= 5:
        print("LIMIT HIT:", user_id)

        await message.answer("❌ Лимит на сегодня (5 песен) исчерпан. Попробуй завтра 🎵")

        return

    user_limits[user_id]["count"] += 1
    user_details = message.text.strip()

    if len(user_details) < 5:
        await message.answer("Пожалуйста, напиши чуть подробнее — мне нужно больше деталей для создания песни! 🎵")
        return

    # Показываем индикатор загрузки
    loading_msg = await message.answer("⏳ Создаю текст песни по вашему запросу...")

    # Получаем сохранённые данные из FSM
    data = await state.get_data()
    genre = data.get("genre", "genre_pop")
    mood = data.get("mood", "mood_happy")
    voice = data.get("voice", "voice_male")

    logger.info(
        f"Пользователь {message.from_user.id} начинает генерацию: "
        f"жанр={genre}, настроение={mood}, голос={voice}"
    )

    try:
        # Генерируем текст песни
        song_text = await generate_song(
            genre=genre,
            mood=mood,
            voice=voice,
            details=user_details,
        )

        # Сохраняем сгенерированную песню в состоянии для возможных правок
        await state.update_data(current_song=song_text)
        await state.set_state(SongCreation.editing)

        # Удаляем сообщение "⏳ Создаю..."
        await loading_msg.delete()

        # Отправляем результат
        result_header = "🎵 Вот твой текст песни, если хочешь что-то исправить — напиши мне:\n\n"
        await message.answer(
            result_header + song_text,
            reply_markup=get_result_keyboard(),
        )
        logger.info(f"Песня успешно сгенерирована для пользователя {message.from_user.id}.")

    except Exception as e:
        logger.error(f"Ошибка генерации для пользователя {message.from_user.id}: {e}")
        await loading_msg.edit_text(
            "😔 Произошла ошибка при генерации песни. Попробуй ещё раз — напиши детали заново."
        )
