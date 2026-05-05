"""
Хэндлер ввода деталей, выбора языка и генерации текста песни.
"""

import logging

from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from states import SongCreation
from keyboards import get_details_keyboard, get_result_keyboard
from services.openai_service import generate_song
from constants import LANG_LABELS, VALID_LANGS
from config import settings
from database import count_generations_today, log_generation, upsert_user

logger = logging.getLogger(__name__)
router = Router()


# ── Выбор языка ────────────────────────────────────────────────────────────────

@router.callback_query(SongCreation.details, lambda c: c.data == "lang_menu")
async def on_lang_menu(callback: CallbackQuery) -> None:
    await callback.answer("Выбери язык кнопками ниже 👇", show_alert=False)


@router.callback_query(
    SongCreation.details,
    lambda c: c.data in {f"lang_{l}" for l in VALID_LANGS},
)
async def on_lang_selected(callback: CallbackQuery, state: FSMContext) -> None:
    lang = callback.data.split("_", 1)[1]  # 'lang_kz' → 'kz'
    await state.update_data(lang=lang)

    label = LANG_LABELS[lang]
    await callback.answer(f"✅ Язык выбран: {label}", show_alert=False)
    await callback.message.edit_reply_markup(reply_markup=get_details_keyboard(lang))


# ── Свой текст ─────────────────────────────────────────────────────────────────

@router.callback_query(SongCreation.details, lambda c: c.data == "own_text")
async def on_own_text(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(use_own_text=True)
    await callback.message.answer(
        "✍️ Отлично! Напиши или вставь свой текст песни — "
        "я передам его напрямую для создания музыки."
    )
    await callback.answer()


# ── Ввод деталей / текста ──────────────────────────────────────────────────────

@router.message(SongCreation.details)
async def on_details_entered(message: Message, state: FSMContext) -> None:
    user    = message.from_user
    user_id = user.id

    # Регистрируем / обновляем пользователя в БД
    await upsert_user(
        telegram_id=user_id,
        username=user.username,
        first_name=user.first_name,
    )

    # Лимит из PostgreSQL — не сбрасывается при рестарте
    used_today = await count_generations_today(user_id)
    if used_today >= settings.FREE_DAILY_LIMIT:
        await message.answer(
            f"❌ Лимит на сегодня ({settings.FREE_DAILY_LIMIT} песни) исчерпан.\n"
            "Попробуй завтра 🎵"
        )
        return

    user_details = message.text.strip()
    if len(user_details) < 5:
        await message.answer("Пожалуйста, напиши чуть подробнее 🙏")
        return

    loading_msg = await message.answer("✍️ Создаю текст песни по вашему запросу...\n⏳")

    data    = await state.get_data()
    genre   = data.get("genre",        "genre_pop")
    mood    = data.get("mood",         "mood_happy")
    voice   = data.get("voice",        "voice_male")
    lang    = data.get("lang",         "ru")
    use_own = data.get("use_own_text", False)

    logger.info(
        f"Генерация для {user_id}: жанр={genre}, настроение={mood}, "
        f"голос={voice}, язык={lang}"
    )

    try:
        song_text = user_details if use_own else await generate_song(
            genre=genre, mood=mood, voice=voice, details=user_details, lang=lang,
        )

        # Записываем генерацию в БД (has_music=False — музыка ещё не создана)
        generation_id = await log_generation(
            telegram_id=user_id,
            genre=genre, mood=mood, voice=voice, lang=lang,
            has_music=False,
        )

        await state.update_data(current_song=song_text, generation_id=generation_id)
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
        logger.info(f"Текст сгенерирован для {user_id}, generation_id={generation_id}.")

    except Exception as e:
        logger.error(f"Ошибка генерации для {user_id}: {e}")
        await loading_msg.edit_text(
            "😔 Произошла ошибка при генерации. Попробуй ещё раз — напиши детали заново."
        )
