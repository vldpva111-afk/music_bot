"""
Хэндлер демонстрационных песен + утилита получения file_id для админа.

Поток для админа (одноразовая настройка):
  1. Запустить бота.
  2. Со своего аккаунта (должен быть в settings.ADMIN_IDS) отправить боту MP3.
  3. Бот ответит сообщением с file_id и подсказкой куда его вставить.
  4. Скопировать file_id в services/examples.py → EXAMPLE_SONGS.
  5. Перезапустить бота.

Поток для пользователя:
  1. Жмёт «🎧 Послушать примеры» в главном меню.
  2. Бот шлёт пачкой все примеры с подписями + CTA «Создай свою».
"""

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from config import settings
from keyboards import get_main_menu_keyboard
from database import log_event, Events
from services.examples import EXAMPLE_SONGS, examples_ready

logger = logging.getLogger(__name__)
router = Router()


# ── Утилита для админа: получить file_id из присланного аудио ─────────────────

@router.message(F.audio)
async def on_admin_audio(message: Message) -> None:
    """
    Когда админ присылает аудио — отвечаем его file_id.
    Для не-админов ничего не делаем (сообщение пройдёт дальше по роутерам).
    """
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    file_id = message.audio.file_id
    title = message.audio.title or "(без названия)"
    duration = message.audio.duration or 0

    await message.reply(
        f"🎵 <b>Получен аудиофайл</b>\n\n"
        f"<b>Название:</b> {title}\n"
        f"<b>Длительность:</b> {duration} сек\n\n"
        f"<b>file_id:</b>\n<code>{file_id}</code>\n\n"
        f"<i>Скопируй и вставь в services/examples.py → EXAMPLE_SONGS</i>",
        parse_mode="HTML",
    )
    logger.info("Выдан file_id админу %d: %s", message.from_user.id, file_id)


# ── Показ примеров пользователю ───────────────────────────────────────────────

INTRO_TEXT = (
    "🎧 <b>Послушай примеры готовых песен</b>\n\n"
    "Вот что получают пользователи бота 👇"
)

CTA_TEXT = (
    "✨ <b>Понравилось?</b>\n\n"
    "Создай свою уникальную песню — "
    "первая генерация бесплатно 🎁"
)


@router.callback_query(lambda c: c.data == "show_examples")
async def on_show_examples(callback: CallbackQuery) -> None:
    if not examples_ready():
        # Защита от показа плейсхолдеров — если админ ещё не загрузил file_id
        await callback.answer(
            "Примеры пока загружаются. Попробуй чуть позже!",
            show_alert=True,
        )
        logger.warning(
            "Юзер %d нажал «Примеры», но EXAMPLE_SONGS не настроены.",
            callback.from_user.id,
        )
        return

    await callback.answer()
    await log_event(callback.from_user.id, Events.EXAMPLES_SHOWN)

    # Заголовок
    await callback.message.answer(INTRO_TEXT, parse_mode="HTML")

    # Сами треки. Каждый шлём отдельным send_audio, чтобы можно было
    # подписать и юзер мог переслать понравившийся отдельно.
    for i, example in enumerate(EXAMPLE_SONGS, start=1):
        try:
            await callback.bot.send_audio(
                chat_id=callback.message.chat.id,
                audio=example["file_id"],
                caption=example["caption"],
                parse_mode="HTML",
            )
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            # Один битый file_id не должен ломать всю выдачу
            logger.warning(
                "Не удалось отправить пример %d юзеру %d: %s",
                i, callback.from_user.id, e,
            )

    # CTA с кнопкой создания
    await callback.message.answer(
        CTA_TEXT,
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(),
    )

    logger.info("Примеры показаны пользователю %d.", callback.from_user.id)
