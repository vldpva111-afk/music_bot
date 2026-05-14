"""
Хэндлер генерации музыки через Suno API.
Передаёт жанр, настроение и голос как параметры стиля.
"""

import logging
import asyncio

from aiogram import Router
from aiogram.types import CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext

from states import SongCreation
from keyboards import get_done_keyboard
from services.music_service import generate_music_from_text
from constants import GENRE_STYLE, MOOD_STYLE, VOICE_STYLE
from database import mark_music_done, refund_credit, log_event, Events

# Таймаут на заливку одного mp3 в Telegram (в секундах).
# Дефолт в aiogram = 60 сек, этого не хватает на файлы 3–5 MB при медленном линке.
# 180 сек — страховочный запас, реальная заливка укладывается в 30–80 сек.
SEND_AUDIO_TIMEOUT = 180.0
from services.admin_alerts import alert_admins

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


_MAKING_MUSIC_KEY = "is_making_music"


@router.callback_query(SongCreation.editing, lambda c: c.data == "make_music")
async def on_make_music(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer()
        return

    # ── Защита от двойного клика ──────────────────────────────────────────────
    # aiogram обрабатывает апдейты конкурентно, поэтому два быстрых клика могут
    # оба пройти фильтр SongCreation.editing до того, как первый успеет
    # переключить состояние. Дополнительный флаг в FSM закрывает гонку.
    data = await state.get_data()
    if data.get(_MAKING_MUSIC_KEY):
        await callback.answer("⏳ Уже создаю музыку, подожди...", show_alert=False)
        return

    # Сразу проставляем флаг и меняем состояние — оба пишутся в Redis,
    # последующие клики либо увидят флаг, либо не пройдут фильтр editing.
    await state.update_data(**{_MAKING_MUSIC_KEY: True})
    await state.set_state(SongCreation.music)
    await callback.answer()
    await log_event(callback.from_user.id, Events.MUSIC_STARTED)

    song_text     = data.get("current_song")
    generation_id = data.get("generation_id")
    user_details  = (data.get("last_details") or "").strip()

    # Строим персональный заголовок песни из деталей запроса — чтобы в библиотеке
    # Telegram юзер мог отличить «песня маме» от «песня брату Алишеру».
    # Берём первую строку, первые 30 символов, чистим хвостовую пунктуацию.
    title_hint = user_details.split("\n")[0][:30].strip().rstrip(",.!?…- ")
    title_base = f"Песня · {title_hint}" if title_hint else "Твоя песня"

    if not song_text:
        await state.update_data(**{_MAKING_MUSIC_KEY: False})
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

    logger.info("Генерация музыки для %s: style=%s", callback.from_user.id, style)

    loading_msg   = await callback.message.answer(PROGRESS_MESSAGES[0])
    progress_task = asyncio.create_task(
        _animate_progress(loading_msg, PROGRESS_MESSAGES)
    )

    try:
        # generate_music_from_text теперь возвращает list[bytes]
        audio_chunks = await generate_music_from_text(song_text, style=style)

        if not audio_chunks:
            raise Exception("No audio data received from API")

        # Сначала заливаем все варианты — если хотя бы один упадёт, поймаем в except
        # и вернём кредит. mark_music_done вызываем ТОЛЬКО после успеха.
        for i, audio_bytes in enumerate(audio_chunks, start=1):
            caption = (
                "🎉 Твоя персональная песня готова! Слушай прямо здесь 👆"
                if i == 1
                else f"🎵 Вариант {i}"
            )
            # Уникальное имя файла критично: Telegram-клиенты кешируют
            # скачанные аудио по filename. Если у двух песен у одного юзера
            # имя совпадает — при «скачать» вторую он получит первую из кеша.
            # generation_id уникален в БД → коллизий не будет.
            unique_id = generation_id if generation_id else int(asyncio.get_event_loop().time() * 1000)
            audio_file = BufferedInputFile(
                file=audio_bytes,
                filename=f"pozdravok_{unique_id}_v{i}.mp3",
            )
            # Если вариантов больше одного — добавляем суффикс «(вар. N)»,
            # иначе чистый title без хвоста.
            song_title = (
                f"{title_base} (вар. {i})" if len(audio_chunks) > 1 else title_base
            )
            await callback.bot.send_audio(
                chat_id=callback.message.chat.id,
                audio=audio_file,
                title=song_title,
                performer="ПоздравОК",
                caption=caption,
                request_timeout=SEND_AUDIO_TIMEOUT,
            )

        # Все треки успешно залиты — теперь можно фиксировать доставку
        if generation_id:
            await mark_music_done(generation_id)

        # Удаляем статус только когда все треки уже отправлены
        try:
            await loading_msg.delete()
        except Exception:
            pass

        variants_text = "два варианта" if len(audio_chunks) > 1 else "один вариант"
        await callback.bot.send_message(
            chat_id=callback.message.chat.id,
            text=(
                f"🎊 Готово! Для тебя {variants_text} — выбери лучший.\n\n"
                "Хочешь создать ещё одну песню?"
            ),
            reply_markup=get_done_keyboard(),
        )

        await log_event(
            callback.from_user.id,
            Events.MUSIC_DELIVERED,
            {"generation_id": generation_id, "variants": len(audio_chunks)},
        )
        await state.clear()

    except Exception as e:
        logger.error("Ошибка генерации музыки для %s: %s", callback.from_user.id, e)

        # ВОЗВРАЩАЕМ КРЕДИТ — юзер не получил песню, не должен терять деньги.
        # credit_type сохранён в FSM из details.py при исходном списании.
        # Для админов он 'admin' — refund_credit вернёт False, это ok.
        credit_type = data.get("credit_type")
        refunded = False
        if credit_type and generation_id:
            try:
                refunded = await refund_credit(
                    telegram_id=callback.from_user.id,
                    credit_type=credit_type,
                    generation_id=generation_id,
                )
            except Exception as refund_err:
                logger.error(
                    "refund_credit упал для юзера %s (gen=%s): %s",
                    callback.from_user.id, generation_id, refund_err,
                )

        await log_event(
            callback.from_user.id,
            Events.MUSIC_FAILED,
            {
                "generation_id": generation_id,
                "error": str(e)[:200],
                "refunded": refunded,
                "credit_type": credit_type,
            },
        )

        # Возвращаем в editing — пользователь может попробовать снова
        await state.set_state(SongCreation.editing)
        await state.update_data(**{_MAKING_MUSIC_KEY: False})

        # Suno может вернуть разные формулировки:
        #   "insufficient_credits"  — старый формат
        #   "credits are insufficient. Please top up." — текущий ответ kie.ai
        #   "code":429               — числовой код в теле JSON
        # Ловим по подстрокам без учёта регистра.
        err_str = str(e).lower()
        is_no_credits = (
            "insufficient" in err_str
            or "top up" in err_str
            or '"code":429' in err_str
        )
        # Суффикс про возврат кредита — показываем только если реально вернули
        refund_suffix = (
            "\n\n💰 <i>Кредит возвращён, можешь попробовать ещё раз.</i>"
            if refunded else ""
        )

        if is_no_credits:
            error_text = (
                "😔 Временно не можем создать песню — идут технические работы.\n"
                "Попробуй чуть позже!"
                f"{refund_suffix}"
            )
            # Срочный алерт админам — нужно пополнить баланс Suno.
            # Cooldown внутри alert_admins по ключу 'suno_no_credits' защищает от спама,
            # если в выходные набежит десяток юзеров одновременно.
            await alert_admins(
                callback.bot,
                (
                    "⚠️ <b>Suno: кончились кредиты</b>\n\n"
                    f"Юзер <code>{callback.from_user.id}</code> "
                    f"не получил песню (generation_id={generation_id}).\n\n"
                    "👉 Пополни баланс на https://kie.ai/\n"
                    "<i>Следующий алерт об этой проблеме не раньше чем через 30 мин.</i>"
                ),
                key="suno_no_credits",
            )
        else:
            error_text = (
                "❌ Ошибка при создании музыки. Попробуй ещё раз или напиши /start"
                f"{refund_suffix}"
            )

        try:
            await loading_msg.edit_text(error_text, parse_mode="HTML")
        except Exception:
            # Сообщение уже удалено или недоступно — шлём новым
            await callback.bot.send_message(
                chat_id=callback.message.chat.id,
                text=error_text,
            )

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
