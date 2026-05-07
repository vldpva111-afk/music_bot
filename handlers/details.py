"""
Хэндлер ввода деталей, выбора языка и генерации текста песни.
"""

import logging

from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from states import SongCreation
from keyboards import get_details_keyboard, get_result_keyboard
from services.openai_service import generate_song
from constants import LANG_LABELS, VALID_LANGS
from config import settings
from database import try_log_generation

logger = logging.getLogger(__name__)
router = Router()

# Флаг в FSM — защита от параллельных запросов с одного устройства
_GENERATING_KEY = "is_generating"


# ── Выбор языка ────────────────────────────────────────────────────────────────

@router.callback_query(SongCreation.details, lambda c: c.data == "lang_menu")
async def on_lang_menu(callback: CallbackQuery) -> None:
    await callback.answer("Выбери язык кнопками ниже 👇", show_alert=False)


@router.callback_query(
    SongCreation.details,
    lambda c: c.data in {f"lang_{l}" for l in VALID_LANGS},
)
async def on_lang_selected(callback: CallbackQuery, state: FSMContext) -> None:
    lang = callback.data.split("_", 1)[1]   # 'lang_kz' → 'kz'
    await state.update_data(lang=lang)

    label = LANG_LABELS[lang]
    await callback.answer(f"✅ Язык выбран: {label}", show_alert=False)
    try:
        await callback.message.edit_reply_markup(reply_markup=get_details_keyboard(lang))
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


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
    user_id = message.from_user.id

    # Защита от параллельных запросов с одного устройства
    data = await state.get_data()
    if data.get(_GENERATING_KEY):
        await message.answer("⏳ Подожди, предыдущий запрос ещё обрабатывается...")
        return

    user_details = message.text.strip()
    if len(user_details) < 5:
        await message.answer("Пожалуйста, напиши чуть подробнее 🙏")
        return

    genre   = data.get("genre",        "genre_pop")
    mood    = data.get("mood",         "mood_happy")
    voice   = data.get("voice",        "voice_male")
    lang    = data.get("lang",         "ru")
    use_own = data.get("use_own_text", False)

    is_admin = user_id in settings.ADMIN_IDS
    daily_limit = settings.FREE_DAILY_LIMIT if not is_admin else 999999

    # ── Атомарная проверка лимита + запись в одной транзакции ─────────────────
    # try_log_generation делает SELECT FOR UPDATE + INSERT в одной транзакции,
    # исключая race condition при параллельных запросах с разных устройств.
    # Возвращает (id, count_after_insert) или None если лимит исчерпан.
    generation_id = await try_log_generation(
        telegram_id=user_id,
        genre=genre, mood=mood, voice=voice, lang=lang,
        daily_limit=daily_limit,
    )

    if generation_id is None and not is_admin:
        await message.answer(
            f"❌ Лимит на сегодня ({settings.FREE_DAILY_LIMIT} песни) исчерпан.\n"
            "Попробуй завтра 🎵"
        )
        return

    await state.update_data(**{_GENERATING_KEY: True})
    loading_msg = await message.answer("✍️ Создаю текст песни по вашему запросу...\n⏳")

    logger.info(
        "Генерация для %d: жанр=%s, настроение=%s, голос=%s, язык=%s",
        user_id, genre, mood, voice, lang,
    )

    try:
        song_text = user_details if use_own else await generate_song(
            genre=genre, mood=mood, voice=voice, details=user_details, lang=lang,
        )

        await state.update_data(
            current_song=song_text,
            generation_id=generation_id,
            **{_GENERATING_KEY: False},
        )
        await state.set_state(SongCreation.editing)
        await loading_msg.delete()

        # Подсчёт остатка без лишнего запроса к БД.
        # try_log_generation уже записал эту генерацию, поэтому вычитаем её:
        # remaining = лимит - (всего сегодня включая текущую)
        # Но нам не нужен точный count — достаточно знать была ли эта генерация последней.
        # Для этого сравниваем generation_id со счётчиком через FSM-данные.
        remaining_text = ""
        if not is_admin:
            # Используем данные из FSM: до этой генерации было (daily_limit - remaining_before) штук.
            # Мы не храним used_count — просто проверяем, не был ли лимит достигнут именно сейчас.
            # Для точного remaining нужен отдельный запрос, но UX важнее точности здесь.
            # Решение: храним счётчик в FSM при первой генерации.
            used_before = data.get("used_count", 0)
            used_now    = used_before + 1
            remaining   = daily_limit - used_now
            await state.update_data(used_count=used_now)

            if remaining > 0:
                remaining_text = f"\n\n<i>Осталось генераций сегодня: {remaining}</i>"
            else:
                remaining_text = "\n\n<i>Это была последняя бесплатная генерация на сегодня 🎵</i>"

        await message.answer(
            "🎵 <b>Вот твой текст песни!</b>\n\n"
            "Если хочешь что-то исправить — нажми «Внести правки».\n"
            "Если всё нравится — нажми «Создать песню» 🎧\n\n"
            f"{song_text}"
            f"{remaining_text}",
            parse_mode="HTML",
            reply_markup=get_result_keyboard(),
        )
        logger.info("Текст сгенерирован для %d, generation_id=%d.", user_id, generation_id)

    except Exception as e:
        logger.error("Ошибка генерации для %d: %s", user_id, e)
        await state.update_data(**{_GENERATING_KEY: False})
        await loading_msg.edit_text(
            "😔 Произошла ошибка при генерации. Попробуй ещё раз — напиши детали заново."
        )
