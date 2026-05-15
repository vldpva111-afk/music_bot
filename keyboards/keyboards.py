"""
Клавиатуры бота. Все inline кнопки хранятся здесь централизованно.
Тексты кнопок берутся из constants.py — единственного источника правды.
"""

from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from constants import GENRE_LABELS, MOOD_LABELS, VOICE_LABELS, LANG_LABELS, PACKAGES
from config import settings


def _support_button() -> list[InlineKeyboardButton] | None:
    """
    Возвращает строку с URL-кнопкой поддержки, если SUPPORT_USERNAME задан.
    URL-кнопка не требует хэндлера — Telegram сам открывает переписку.
    """
    if not settings.SUPPORT_USERNAME:
        return None
    return [InlineKeyboardButton(
        text="💬 Служба поддержки",
        url=f"https://t.me/{settings.SUPPORT_USERNAME}",
    )]


# ── Старт / Главное меню ──────────────────────────────────────────────────────

def get_start_keyboard() -> InlineKeyboardMarkup:
    """Алиас главного меню — оставлен для совместимости вызовов в /start."""
    return get_main_menu_keyboard()


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню: создание песни, примеры, покупка, реферал, баланс."""
    rows = [
        [InlineKeyboardButton(text="🎵 Новая песня",        callback_data="create_song")],
        [InlineKeyboardButton(text="🎧 Послушать примеры",  callback_data="show_examples")],
        [InlineKeyboardButton(text="💎 Купить кредиты",     callback_data="buy_credits")],
        [InlineKeyboardButton(text="💌 Пригласить друга",   callback_data="show_invite")],
        [InlineKeyboardButton(text="💰 Мой баланс",         callback_data="show_balance")],
    ]
    if (btn := _support_button()):
        rows.append(btn)
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Покупка кредитов ──────────────────────────────────────────────────────────

def get_packages_keyboard() -> InlineKeyboardMarkup:
    """Список тарифов. Каждая кнопка — callback_data = ключ пакета."""
    rows = []
    for key, pkg in PACKAGES.items():
        rows.append([InlineKeyboardButton(
            text=f"{pkg['label']} — {pkg['price']} ₸",
            callback_data=key,
        )])
    rows.append([InlineKeyboardButton(text="◀️ В меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_phone_request_keyboard() -> ReplyKeyboardMarkup:
    """
    Reply-клавиатура с запросом номера телефона. В отличие от inline,
    позволяет Telegram'у самому прислать номер юзера одной кнопкой.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить мой номер", request_contact=True)],
            [KeyboardButton(text="❌ Отменить заказ")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


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
    """После готовой музыки показываем главное меню — все варианты под рукой."""
    return get_main_menu_keyboard()


# ── Сообщение об ошибке ───────────────────────────────────────────────────────

def get_error_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура к сообщению об ошибке: кнопка поддержки (если настроена) + в меню.
    Ловим юзера на пике раздражения и даём прямой канал связи.
    """
    rows: list[list[InlineKeyboardButton]] = []
    if (btn := _support_button()):
        rows.append(btn)
    rows.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Во время ожидания правок ──────────────────────────────────────────────────

def get_cancel_edit_keyboard() -> InlineKeyboardMarkup:
    """Показывается пока бот ждёт текст правок — позволяет отменить."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_edit")],
    ])