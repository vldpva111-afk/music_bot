"""
Хэндлер генерации музыки через Suno API.
Передаёт жанр, настроение и голос как параметры стиля.
"""

import logging
import asyncio

from aiogram import Router
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from states import SongCreation
from keyboards import get_done_keyboard
from services.music_service import generate_music_from_text
from constants import GENRE_STYLE, MOOD_STYLE, VOICE_STYLE
from database import mark_music_done

router = Router()
logger = logging.getLogger(__name__)

PROGRESS_MESSAGES = [
    "🎵 Создаю вашу песню...\n⏳ Ожидание может занять несколько минут",
    "🎵 Создаю вашу песню...\n🎼 Подбираю мелодию и аранжировку",
    "🎵 Создаю вашу песню...\n🎤 Записываю вокал",
    "🎵 Создаю вашу песню...\n🎧 Финальная обработка трека",
    "🎵 Создаю вашу песню...\n✨ Почти готово, ещё немного!",
]

PROGRESS_INTERVAL = 15  # секунд между обновлениями прогресса


@router.callback_query(SongCreation.editing, lambda c: c.data == "make_music")
async def on_make_music(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    if not callback.message:
        return

    data          = await state.get_data()
    song_text     = data.get("current_song")
    generation_id = data.get("generation_id")

    if not song_text:
        await callback.message.answer("❌ Не найден текст песни. Начни сначала — /start")
        return

    # Переводим в состояние music — блокирует повторное нажатие и правки
    await state.set_state(SongCreation.music)

    genre = data.get("genre", "genre_pop")
    mood  = data.get("mood",  "mood_happy")
    voice = data.get("voice", "voice_male")

    style = ", ".join([
        GENRE_STYLE.get(genre, "Pop"),
        MOOD_STYLE.get(mood, "upbeat"),
        VOICE_STYLE.get(voice, "male vocals"),
    ])

    logger.info("Генерация музыки для %s: style=%s", callback.from_user.id, style)

    loading_msg   = await callback.message.answer(PROGRESS_MESSAGES[0])
    progress_task = asyncio.create_task(
        _animate_progress(loading_msg, PROGRESS_MESSAGES)
    )

    try:
        audio_urls = await generate_music_from_text(song_text, style=style)

        if not audio_urls:
            raise Exception("No audio URLs from API")

        if generation_id:
            await mark_music_done(generation_id)

        await loading_msg.delete()

        for i, url in enumerate(audio_urls, start=1):
            caption = (
                "🎉 Твоя персональная песня готова! Слушай прямо здесь 👆"
                if i == 1
                else f"🎵 Вариант {i}"
            )
            await callback.bot.send_audio(
                chat_id=callback.message.chat.id,
                audio=url,
                title=f"🎵 Твоя песня — вариант {i}",
                caption=caption,
            )

        variants_text = "два варианта" if len(audio_urls) > 1 else "один вариант"
        await callback.bot.send_message(
            chat_id=callback.message.chat.id,
            text=(
                f"🎊 Готово! Для тебя {variants_text} — выбери лучший.\n\n"
                "Хочешь создать ещё одну песню?"
            ),
            reply_markup=get_done_keyboard(),
        )

        await state.clear()

    except Exception as e:
        logger.error("Ошибка генерации музыки для %s: %s", callback.from_user.id, e)

        # Возвращаем в editing — пользователь может попробовать снова
        await state.set_state(SongCreation.editing)

        if "insufficient_credits" in str(e):
            error_text = (
                "😔 Временно не можем создать песню — идёт пополнение баланса.\n"
                "Попробуй чуть позже!"
            )
        else:
            error_text = "❌ Ошибка при создании музыки. Попробуй ещё раз или напиши /start"

        await loading_msg.edit_text(error_text)

    finally:
        # Гарантированно отменяем задачу анимации в любом случае
        progress_task.cancel()
        try:
            await progress_task
        except asyncio.CancelledError:
            pass


async def _animate_progress(msg, messages: list, interval: int = PROGRESS_INTERVAL) -> None:
    try:
        idx = 1
        while True:
            await asyncio.sleep(interval)
            try:
                await msg.edit_text(messages[idx % len(messages)])
            except Exception:
                pass
            idx += 1
    except asyncio.CancelledError:
        pass
