"""
Клавиатуры бота.
Все inline и reply кнопки хранятся здесь централизованно.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


# ─────────────────────────────────────────────
# Стартовая клавиатура
# ─────────────────────────────────────────────

def get_start_keyboard() -> InlineKeyboardMarkup:
    """Кнопка 'Создать песню' на старте."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎵 Создать песню", callback_data="create_song")]
        ]
    )


# ─────────────────────────────────────────────
# Выбор жанра
# ─────────────────────────────────────────────

def get_genre_keyboard() -> InlineKeyboardMarkup:
    """Кнопки выбора музыкального жанра."""
    genres = [
        ("🎤 Рэп/хип-хоп", "genre_rap"),
        ("🎶 Поп", "genre_pop"),
        ("🎸 Рок", "genre_rock"),
        ("🎻 Шансон", "genre_chanson"),
        ("🕺 Диско 80-х", "genre_disco"),
        ("🎼 Классика", "genre_classic"),
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=cb)]
            for label, cb in genres
        ]
    )


# ─────────────────────────────────────────────
# Выбор настроения
# ─────────────────────────────────────────────

def get_mood_keyboard() -> InlineKeyboardMarkup:
    """Кнопки выбора настроения песни."""
    moods = [
        ("😄 Радостное", "mood_happy"),
        ("😢 Грустное", "mood_sad"),
        ("😌 Спокойное", "mood_calm"),
        ("❤️ Любовное", "mood_love"),
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=cb)]
            for label, cb in moods
        ]
    )


# ─────────────────────────────────────────────
# Выбор голоса
# ─────────────────────────────────────────────

def get_voice_keyboard() -> InlineKeyboardMarkup:
    """Кнопки выбора голоса исполнителя."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👨 Мужским", callback_data="voice_male")],
            [InlineKeyboardButton(text="👩 Женским", callback_data="voice_female")],
        ]
    )


# ─────────────────────────────────────────────
# Ввод деталей / язык
# ─────────────────────────────────────────────

def get_details_keyboard() -> InlineKeyboardMarkup:
    """Дополнительные опции при вводе деталей."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🇷🇺 Язык песни: Русский", callback_data="lang_ru")],
            [InlineKeyboardButton(text="✍️ У меня есть свой текст", callback_data="own_text")],
        ]
    )


# ─────────────────────────────────────────────
# После генерации песни
# ─────────────────────────────────────────────

def get_result_keyboard() -> InlineKeyboardMarkup:
    """Кнопки после показа готовой песни."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎵 Создать песню", callback_data="create_song")],
            [InlineKeyboardButton(text="✏️ Внести правки", callback_data="edit_song")],
        ]
    )
