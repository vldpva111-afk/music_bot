"""
Хэндлер генерации музыки через Suno API.
Передаёт жанр, настроение и голос как параметры стиля.
"""

import asyncio
import logging

import aiohttp
from aiogram import Router
from aiogram.types import BufferedInputFile, CallbackQuery
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

    genre = data.get("genre", "genre_pop")
    mood  = data.get("mood",  "mood_happy")
    voice = data.get("voice", "voice_male")

    style = ", ".join([
        GENRE_STYLE.get(genre, "Pop"),
        MOOD_STYLE.get(mood,   "upbeat"),
        VOICE_STYLE.get(voice, "male vocals"),
    ])

    logger.info("Генерация музыки для %d: style=%s", callback.from_user.id, style)

    loading_msg   = await callback.message.answer(PROGRESS_MESSAGES[0])
    progress_task = asyncio.create_task(_animate_progress(loading_msg, PROGRESS_MESSAGES))

    try:
        audio_urls = await generate_music_from_text(song_text, style=style)

        if not audio_urls:
            raise Exception("No audio URLs from API")

        progress_task.cancel()
        await _suppress_cancelled(progress_task)

        if generation_id:
            await mark_music_done(generation_id)

        await loading_msg.delete()

        async with aiohttp.ClientSession() as session:
            for i, url in enumerate(audio_urls, start=1):
                caption = (
                    "🎉 Твоя персональная песня готова! Слушай прямо здесь 👆"
                    if i == 1
                    else f"🎵 Вариант {i}"
                )
                async with session.get(url) as resp:
                    audio_bytes = await resp.read()

                await callback.bot.send_audio(
                    chat_id=callback.message.chat.id,
                    audio=BufferedInputFile(audio_bytes, filename=f"Твоя песня №{i}.mp3"),
                    title=f"Твоя песня №{i}",
                    caption=caption,
                )

        variants_text = "два варианта" if len(audio_urls) > 1 else "один вариант"
        await callback.bot.send_message(
            chat_id=callback.message.chat.id,
            text=f"🎊 Готово! Для тебя {variants_text} — выбери лучший.",
            reply_markup=get_done_keyboard(),
        )

    except Exception as e:
        progress_task.cancel()
        await _suppress_cancelled(progress_task)

        logger.error("Ошибка генерации музыки для %d: %s", callback.from_user.id, e)

        if "insufficient_credits" in str(e):
            await loading_msg.edit_text(
                "😔 Временно не можем создать песню — идёт пополнение баланса.\n"
                "Попробуй чуть позже!"
            )
        else:
            await loading_msg.edit_text(
                "❌ Ошибка при создании музыки. Попробуй ещё раз или напиши /start"
            )


async def _animate_progress(msg, messages: list) -> None:
    try:
        idx = 1
        while True:
            await asyncio.sleep(15)
            try:
                await msg.edit_text(messages[idx % len(messages)])
            except Exception:
                pass
            idx += 1
    except asyncio.CancelledError:
        pass


async def _suppress_cancelled(task: asyncio.Task) -> None:
    """Ждёт завершения задачи, подавляя CancelledError."""
    try:
        await task
    except asyncio.CancelledError:
        pass
