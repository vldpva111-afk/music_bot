"""
Клавиатуры бота. Все inline кнопки хранятся здесь централизованно.
Тексты кнопок берутся из constants.py — единственного источника правды.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from constants import GENRE_LABELS, MOOD_LABELS, VOICE_LABELS, LANG_LABELS


# ── Старт ─────────────────────────────────────────────────────────────────────

def get_start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎵 Начать", callback_data="create_song")]
    ])


# ── Жанр ─────────────────────────────────────────────────────────────────────

def get_genre_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=key)]
        for key, label in GENRE_LABELS.items()
    ])


# ── Настроение ────────────────────────────────────────────────────────────────

def get_mood_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=key)]
        for key, label in MOOD_LABELS.items()
    ] + [
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_genre")]
    ])


# ── Голос ─────────────────────────────────────────────────────────────────────

def get_voice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=key)]
        for key, label in VOICE_LABELS.items()
    ] + [
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_mood")]
    ])


# ── Детали: язык + свой текст ─────────────────────────────────────────────────

# Короткие метки для языковой строки — умещаются в одну строку
_LANG_SHORT: dict[str, str] = {
    "ru": "🇷🇺 Рус",
    "kz": "🇰🇿 Қаз",
    "tt": "🇷🇺 Тат",
    "uz": "🇺🇿 Ўзб",
    "en": "🇬🇧 Eng",
}


def get_details_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """
    Показывает текущий выбранный язык, строку быстрого переключения и кнопку 'Свой текст'.
    lang — текущий выбранный язык ('ru', 'kz', 'tt', 'uz', 'en').
    """
    selected_label = LANG_LABELS.get(lang, LANG_LABELS["ru"])

    return InlineKeyboardMarkup(inline_keyboard=[
        # Информационная строка с текущим языком
        [InlineKeyboardButton(
            text=f"🌍 Язык: {selected_label}",
            callback_data="lang_menu",
        )],
        # Быстрое переключение языка
        [
            InlineKeyboardButton(text=short, callback_data=f"lang_{code}")
            for code, short in _LANG_SHORT.items()
        ],
        [InlineKeyboardButton(text="✍️ У меня есть готовый текст", callback_data="own_text")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_voice")],
    ])


# ── После генерации текста ────────────────────────────────────────────────────

def get_result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎵 Создать песню",   callback_data="make_music")],
        [InlineKeyboardButton(text="✏️ Внести правки",   callback_data="edit_song")],
        [InlineKeyboardButton(text="🔄 Сгенерировать заново", callback_data="regenerate_song")],
    ])


# ── После получения музыки ────────────────────────────────────────────────────

def get_done_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎵 Создать новую песню", callback_data="create_song")],
    ])


# ── Во время ожидания правок ──────────────────────────────────────────────────

def get_cancel_edit_keyboard() -> InlineKeyboardMarkup:
    """Показывается пока бот ждёт текст правок — позволяет отменить."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_edit")],
    ])