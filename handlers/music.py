"""
Хэндлер генерации музыки через Suno API.
Передаёт жанр, настроение и голос как параметры стиля.
"""

import logging
import asyncio

from aiogram import Router
from aiogram.types import CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext

from services.music_service import generate_music_from_text, download_audio
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


@router.callback_query(lambda c: c.data == "make_music")
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
        MOOD_STYLE.get(mood, "upbeat"),
        VOICE_STYLE.get(voice, "male vocals"),
    ])

    logger.info(f"Генерация музыки для {callback.from_user.id}: style={style}")

    loading_msg = await callback.message.answer(PROGRESS_MESSAGES[0])
    progress_task = asyncio.create_task(
        _animate_progress(loading_msg, PROGRESS_MESSAGES)
    )

    try:
        audio_url   = await generate_music_from_text(song_text, style=style)

        if not audio_url:
            raise Exception("Empty audio_url from API")

        audio_bytes = await download_audio(audio_url)
        logger.info(f"Размер аудио: {len(audio_bytes)} байт")

        if len(audio_bytes) < 10_000:
            raise Exception(f"Файл слишком маленький: {len(audio_bytes)} байт")

        progress_task.cancel()
        try:
            await progress_task
        except asyncio.CancelledError:
            pass

        # Отмечаем в БД что музыка успешно создана
        if generation_id:
            await mark_music_done(generation_id)

        await loading_msg.delete()

        await callback.bot.send_audio(
            chat_id=callback.message.chat.id,
            audio=BufferedInputFile(audio_bytes, filename="song.mp3"),
            title="🎵 Твоя песня",
            caption="🎉 Твоя персональная песня готова! Слушай прямо здесь 👆",
        )
        await callback.bot.send_message(
            chat_id=callback.message.chat.id,
            text=(
                "🎊 Готово! Хочешь создать ещё одну песню?\n\n"
                "Нажми /start — начнём сначала 🎵"
            ),
        )

    except Exception as e:
        progress_task.cancel()
        try:
            await progress_task
        except asyncio.CancelledError:
            pass

        logger.error(f"Ошибка генерации музыки для {callback.from_user.id}: {e}")

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
    """Обновляет сообщение каждые 15 секунд, циклически перебирая тексты."""
    try:
        idx = 1
        while True:
            await asyncio.sleep(15)
            text = messages[idx % len(messages)]
            try:
                await msg.edit_text(text)
            except Exception:
                pass
            idx += 1
    except asyncio.CancelledError:
        pass
