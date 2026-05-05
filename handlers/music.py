import logging

from aiogram import Router

from aiogram.types import CallbackQuery

from aiogram.fsm.context import FSMContext

from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton

from services.music_service import generate_music_from_text, download_audio

router = Router()

logger = logging.getLogger(__name__)

@router.callback_query(lambda c: c.data == "make_music")

async def on_create_song(callback: CallbackQuery, state: FSMContext):

    await callback.answer()

    if not callback.message:

        return

    loading_msg = await callback.message.answer("🎧 Создаю песню... подожди немного")

    try:

        logger.info(f"Generating music for user {callback.from_user.id}")

        data = await state.get_data()

        song_text = data.get("current_song")

        if not song_text:

            await callback.message.answer("❌ Не найден текст песни")

            return

        await state.clear()

        # 1. получаем ссылку на музыку (НЕ bytes!)

        audio_url = await generate_music_from_text(song_text)

        logger.info(f"AUDIO URL: {audio_url}")

        if not audio_url:

            raise Exception("Empty audio url returned from API")

        # 2. скачиваем mp3

        audio_bytes = await download_audio(audio_url)

        logger.info(f"AUDIO SIZE: {len(audio_bytes)} bytes")

        # защита от ошибок (твоя старая проблема 141 байт)

        if len(audio_bytes) < 10000:

            raise Exception("Audio file too small, likely API error")

        # 3. отправляем в Telegram

        audio = BufferedInputFile(audio_bytes, filename="song.mp3")

        download_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬇️ Скачать MP3", url=audio_url)]
        ])

        # 1. плеер — можно слушать прямо в Telegram
        await callback.bot.send_audio(
            chat_id=callback.message.chat.id,
            audio=audio,
            title="Твоя песня 🎵",
        )

        # 2. тот же файл как документ — очевидная кнопка скачать
        await callback.bot.send_document(
            chat_id=callback.message.chat.id,
            document=BufferedInputFile(audio_bytes, filename="song.mp3"),
            caption="⬇️ Нажми чтобы скачать песню на устройство",
        )

    except Exception as e:

        logger.error(f"Music error: {e}")

        await callback.message.answer("❌ Ошибка при создании музыки")

    finally:

        try:

            await loading_msg.delete()

        except:

            pass
