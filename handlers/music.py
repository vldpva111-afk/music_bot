import logging
from aiogram import Router
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from services.music_service import generate_music_from_text

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(lambda c: c.data == "create_song")
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

        audio_bytes = await generate_music_from_text(song_text)

        await callback.bot.send_audio(

            chat_id=callback.message.chat.id,

            audio=audio_bytes,

            title="Твоя песня 🎵"

        )

    except Exception as e:

        logger.error(f"Music error: {e}")

        await callback.message.answer("❌ Ошибка при создании музыки")

    finally:
        try:
            await loading_msg.delete()
        except:
            pass
