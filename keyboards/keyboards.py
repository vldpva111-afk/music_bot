"""
Клавиатуры бота. Все inline кнопки хранятся здесь централизованно.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# ── Старт ────────────────────────────────────────────────────────────────────

def get_start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎵 Начать", callback_data="create_song")]
    ])


# ── Жанр ─────────────────────────────────────────────────────────────────────

def get_genre_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎤 Рэп/хип-хоп",  callback_data="genre_rap")],
        [InlineKeyboardButton(text="🎶 Поп",           callback_data="genre_pop")],
        [InlineKeyboardButton(text="🎸 Рок",           callback_data="genre_rock")],
        [InlineKeyboardButton(text="🎻 Шансон",        callback_data="genre_chanson")],
        [InlineKeyboardButton(text="🕺 Диско 80-х",    callback_data="genre_disco")],
        [InlineKeyboardButton(text="🎼 Классика",      callback_data="genre_classic")],
    ])


# ── Настроение ────────────────────────────────────────────────────────────────

def get_mood_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="😄 Радостное",  callback_data="mood_happy")],
        [InlineKeyboardButton(text="😢 Грустное",   callback_data="mood_sad")],
        [InlineKeyboardButton(text="😌 Спокойное",  callback_data="mood_calm")],
        [InlineKeyboardButton(text="❤️ Любовное",   callback_data="mood_love")],
    ])


# ── Голос ─────────────────────────────────────────────────────────────────────

def get_voice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨 Мужским",  callback_data="voice_male")],
        [InlineKeyboardButton(text="👩 Женским",  callback_data="voice_female")],
    ])


# ── Детали: язык + свой текст ─────────────────────────────────────────────────

def get_details_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """
    Показывает кнопку выбора языка (с раскрытием) и кнопку 'Свой текст'.
    lang — текущий выбранный язык ('ru', 'kz', 'tt', 'uz', 'en').
    """
    lang_labels = {
        "ru": "🇷🇺 Русский",
        "kz": "🇰🇿 Казакша",
        "tt": "🇷🇺 Татарча",
        "uz": "🇺🇿 Озбекча",
        "en": "🇬🇧 English",
    }
    # Основная кнопка языка — показывает текущий выбор
    selected_label = lang_labels.get(lang, "🇷🇺 Русский")

    return InlineKeyboardMarkup(inline_keyboard=[
        # Кнопка-заголовок (открывает варианты)
        [InlineKeyboardButton(
            text=f"🌍 Язык песни: {selected_label}",
            callback_data="lang_menu"
        )],
        # Языки всегда видны — одна строка
        [
            InlineKeyboardButton(text="🇷🇺 Рус",  callback_data="lang_ru"),
            InlineKeyboardButton(text="🇰🇿 Каз",  callback_data="lang_kz"),
            InlineKeyboardButton(text="🇷🇺 Тат",  callback_data="lang_tt"),
            InlineKeyboardButton(text="🇺🇿 Узб",  callback_data="lang_uz"),
            InlineKeyboardButton(text="🇬🇧 Eng",  callback_data="lang_en"),
        ],
        [InlineKeyboardButton(text="✍️ У меня есть готовый текст", callback_data="own_text")],
    ])


# ── После генерации текста ────────────────────────────────────────────────────

def get_result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎵 Создать песню",  callback_data="make_music")],
        [InlineKeyboardButton(text="✏️ Внести правки",  callback_data="edit_song")],
    ])
