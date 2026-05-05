"""
Хэндлер ввода деталей, выбора языка и генерации текста песни.
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

user_limits: dict = {}

LANG_LABELS = {
    "ru": "🇷🇺 Русский",
    "kz": "🇰🇿 Казакша",
    "tt": "🇷🇺 Татарча",
    "uz": "🇺🇿 Озбекча",
    "en": "🇬🇧 English",
}

VALID_LANGS = set(LANG_LABELS.keys())

# ── Выбор языка ────────────────────────────────────────────────────────────────

@router.callback_query(SongCreation.details, lambda c: c.data == "lang_menu")
async def on_lang_menu(callback: CallbackQuery) -> None:
    """Нажатие на заголовок языка — подсказка."""
    await callback.answer("Выбери язык кнопками ниже 👇", show_alert=False)


@router.callback_query(SongCreation.details, lambda c: c.data in {f"lang_{l}" for l in ("ru","kz","tt","uz","en")})
async def on_lang_selected(callback: CallbackQuery, state: FSMContext) -> None:
    """Пользователь выбрал язык — сохраняем и обновляем клавиатуру."""
    lang = callback.data.split("_")[1]  # 'lang_kz' → 'kz'
    await state.update_data(lang=lang)

    label = LANG_LABELS[lang]
    await callback.answer(f"✅ Язык выбран: {label}", show_alert=False)

    # Обновляем кнопки — подсвечиваем выбранный язык
    await callback.message.edit_reply_markup(
        reply_markup=get_details_keyboard(lang)
    )


# ── Свой текст ─────────────────────────────────────────────────────────────────

@router.callback_query(SongCreation.details, lambda c: c.data == "own_text")
async def on_own_text(callback: CallbackQuery, state: FSMContext) -> None:
    """Пользователь хочет вставить свой готовый текст."""
    await state.update_data(use_own_text=True)
    await callback.message.answer(
        "✍️ Отлично! Напиши или вставь свой текст песни — "
        "я передам его напрямую для создания музыки."
    )
    await callback.answer()


# ── Ввод деталей / текста ──────────────────────────────────────────────────────

@router.message(SongCreation.details)
async def on_details_entered(message: Message, state: FSMContext) -> None:
    """Пользователь ввёл детали — генерируем текст песни через OpenAI."""

    # Дневной лимит
    user_id = message.from_user.id
    today = datetime.now().date()

    if user_id not in user_limits:
        user_limits[user_id] = {"date": today, "count": 0}
    if user_limits[user_id]["date"] != today:
        user_limits[user_id] = {"date": today, "count": 0}
    if user_limits[user_id]["count"] >= 5:
        await message.answer("❌ Лимит на сегодня (5 песен) исчерпан. Попробуй завтра 🎵")
        return

    user_details = message.text.strip()
    if len(user_details) < 5:
        await message.answer("Пожалуйста, напиши чуть подробнее 🙏")
        return

    user_limits[user_id]["count"] += 1

    # Анимация ожидания
    loading_msg = await message.answer("✍️ Создаю текст песни по вашему запросу...\n⏳")

    data = await state.get_data()
    genre  = data.get("genre", "genre_pop")
    mood   = data.get("mood",  "mood_happy")
    voice  = data.get("voice", "voice_male")
    lang   = data.get("lang",  "ru")
    use_own = data.get("use_own_text", False)

    logger.info(f"Генерация для {user_id}: жанр={genre}, настроение={mood}, голос={voice}, язык={lang}")

    try:
        if use_own:
            # Свой текст — сохраняем как есть, без OpenAI
            song_text = user_details
        else:
            song_text = await generate_song(
                genre=genre,
                mood=mood,
                voice=voice,
                details=user_details,
                lang=lang,
            )

        await state.update_data(current_song=song_text)
        await state.set_state(SongCreation.editing)

        await loading_msg.delete()

        await message.answer(
            "🎵 <b>Вот твой текст песни!</b>\n\n"
            "Если хочешь что-то исправить — нажми «Внести правки».\n"
            "Если всё нравится — нажми «Создать песню» 🎧\n\n"
            f"{song_text}",
            parse_mode="HTML",
            reply_markup=get_result_keyboard(),
        )
        logger.info(f"Текст сгенерирован для {user_id}.")

    except Exception as e:
        logger.error(f"Ошибка генерации для {user_id}: {e}")
        await loading_msg.edit_text(
            "😔 Произошла ошибка при генерации. Попробуй ещё раз — напиши детали заново."
        )
