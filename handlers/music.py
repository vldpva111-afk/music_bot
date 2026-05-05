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

router = Router()
logger = logging.getLogger(__name__)

# Человекочитаемые названия для передачи в Suno
GENRE_STYLE = {
    "genre_rap":     "Hip-hop rap",
    "genre_pop":     "Pop",
    "genre_rock":    "Rock",
    "genre_chanson":  "Chanson",
    "genre_disco":   "Disco 80s",
    "genre_classic": "Classical",
}

MOOD_STYLE = {
    "mood_happy": "upbeat joyful",
    "mood_sad":   "melancholic sad",
    "mood_calm":  "calm relaxing",
    "mood_love":  "romantic loving",
}

VOICE_STYLE = {
    "voice_male":   "male vocals",
    "voice_female": "female vocals",
}

# Сообщения прогресса — обновляются каждые ~15 секунд
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

    data = await state.get_data()
    song_text = data.get("current_song")

    if not song_text:
        await callback.message.answer("❌ Не найден текст песни. Начни сначала — /start")
        return

    # Собираем стиль из выборов пользователя
    genre = data.get("genre", "genre_pop")
    mood  = data.get("mood",  "mood_happy")
    voice = data.get("voice", "voice_male")

    style_parts = [
        GENRE_STYLE.get(genre, "Pop"),
        MOOD_STYLE.get(mood, "upbeat"),
        VOICE_STYLE.get(voice, "male vocals"),
    ]
    style = ", ".join(style_parts)

    logger.info(f"Генерация музыки для {callback.from_user.id}: style={style}")

    # Показываем первое сообщение о прогрессе
    loading_msg = await callback.message.answer(PROGRESS_MESSAGES[0])

    # Запускаем анимацию прогресса в фоне
    progress_task = asyncio.create_task(
        _animate_progress(loading_msg, PROGRESS_MESSAGES)
    )

    try:
        # Генерируем музыку — передаём текст и стиль
        audio_url = await generate_music_from_text(song_text, style=style)

        if not audio_url:
            raise Exception("Empty audio_url from API")

        # Скачиваем mp3
        audio_bytes = await download_audio(audio_url)
        logger.info(f"Размер аудио: {len(audio_bytes)} байт")

        if len(audio_bytes) < 10_000:
            raise Exception(f"Файл слишком маленький: {len(audio_bytes)} байт")

        # Останавливаем анимацию
        progress_task.cancel()
        await loading_msg.delete()

        # 1. Плеер — слушать прямо в Telegram
        await callback.bot.send_audio(
            chat_id=callback.message.chat.id,
            audio=BufferedInputFile(audio_bytes, filename="song.mp3"),
            title="🎵 Твоя песня",
            caption="🎉 Твоя персональная песня готова! Слушай прямо здесь 👆",
        )

        # 2. Документ — для скачивания
        await callback.bot.send_document(
            chat_id=callback.message.chat.id,
            document=BufferedInputFile(audio_bytes, filename="song.mp3"),
            caption=(
                "⬇️ <b>Нажми чтобы скачать MP3 на устройство</b>\n\n"
                "Хочешь создать ещё одну песню? Нажми /start"
            ),
            parse_mode="HTML",
        )

    except Exception as e:
        progress_task.cancel()
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
                pass  # сообщение могло уже удалиться
            idx += 1
    except asyncio.CancelledError:
        pass
