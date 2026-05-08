"""
Хэндлер ввода деталей, выбора языка и генерации текста песни.
"""

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from states import SongCreation
from keyboards import get_details_keyboard, get_result_keyboard
from services.openai_service import generate_song
from constants import LANG_LABELS, VALID_LANGS
from config import settings
from database import try_consume_and_log, log_generation, get_credits_info

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

async def _build_no_credits_text(message: Message) -> str:
    """Сообщение когда у пользователя кончились кредиты — со ссылкой-приглашением."""
    user_id = message.from_user.id
    try:
        me = await message.bot.me()
        ref_link = f"https://t.me/{me.username}?start=ref_{user_id}"
    except Exception:
        # На случай если bot.me() упадёт — отдадим сообщение без ссылки
        ref_link = None

    text = (
        "❌ У тебя закончились бесплатные генерации.\n\n"
        "Получи <b>+1 бонусный кредит</b> за каждого друга, "
        "который зарегистрируется по твоей ссылке 🎵"
    )
    if ref_link:
        text += f"\n\n<b>Твоя ссылка:</b>\n<code>{ref_link}</code>"
    return text


def _format_remaining(credit_type: str, free_available: bool, bonus_credits: int) -> str:
    """Текст про остаток кредитов после успешной генерации (отдельным сообщением)."""
    parts = []
    if credit_type == "free":
        parts.append("🎁 <b>Использована приветственная генерация</b>")
    elif credit_type == "bonus":
        parts.append("⭐ <b>Использован бонусный кредит</b>")

    remain = []
    if free_available:
        remain.append("🎁 приветственная: 1")
    if bonus_credits > 0:
        remain.append(f"⭐ бонусных: {bonus_credits}")

    if remain:
        parts.append("Осталось — " + ", ".join(remain))
    else:
        parts.append("Это была твоя последняя бесплатная генерация 🎵")

    return "\n".join(parts)


@router.message(SongCreation.details, F.text)
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

    # ── Списание кредита + запись генерации ───────────────────────────────────
    # Для админов — безлимит: пишем в журнал без списания.
    # Для остальных — try_consume_and_log делает FOR UPDATE + UPDATE + INSERT
    # в одной транзакции. Возвращает (id, credit_type) или None если кредитов нет.
    if is_admin:
        generation_id = await log_generation(
            telegram_id=user_id, genre=genre, mood=mood, voice=voice, lang=lang,
        )
        credit_type = "admin"
    else:
        result = await try_consume_and_log(
            telegram_id=user_id, genre=genre, mood=mood, voice=voice, lang=lang,
        )
        if result is None:
            await message.answer(
                await _build_no_credits_text(message),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            return
        generation_id, credit_type = result

    await state.update_data(**{_GENERATING_KEY: True})
    loading_msg = await message.answer("✍️ Создаю текст песни по вашему запросу...\n⏳")

    logger.info(
        "Генерация для %d: жанр=%s, настроение=%s, голос=%s, язык=%s, credit=%s",
        user_id, genre, mood, voice, lang, credit_type,
    )

    try:
        song_text = user_details if use_own else await generate_song(
            genre=genre, mood=mood, voice=voice, details=user_details, lang=lang,
        )

        await state.update_data(
            current_song=song_text,
            generation_id=generation_id,
            last_details=user_details,
            **{_GENERATING_KEY: False},
        )
        await state.set_state(SongCreation.editing)
        await loading_msg.delete()

        # Сначала — отдельное сообщение про списание и остаток кредитов
        if not is_admin:
            credits = await get_credits_info(user_id)
            remaining_text = _format_remaining(
                credit_type=credit_type,
                free_available=credits["free_available"],
                bonus_credits=credits["bonus_credits"],
            )
            await message.answer(remaining_text, parse_mode="HTML")

        # Затем — сам текст песни с клавиатурой (кнопки на самом свежем сообщении)
        await message.answer(
            "🎵 <b>Вот твой текст песни!</b>\n\n"
            "Если хочешь что-то исправить — нажми «Внести правки».\n"
            "Если всё нравится — нажми «Создать песню» 🎧\n\n"
            f"{song_text}",
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


# Фоллбэк для не-текстовых сообщений (фото, стикеры, голос и т.п.)
# Должен идти после основного хэндлера — иначе перехватит всё.
@router.message(SongCreation.details)
async def on_details_non_text(message: Message) -> None:
    await message.answer(
        "Пожалуйста, отправь описание <b>текстом</b> 📝",
        parse_mode="HTML",
    )
