"""
Примеры готовых песен для демонстрации новым пользователям.

Песни хранятся как Telegram file_id — их раздача мгновенна, не тратит API-кредиты
и файлы лежат у Telegram бесплатно. file_id привязан к боту: при смене токена
бота нужно перезалить и обновить здесь.

КАК ПОЛУЧИТЬ file_id:
  1. Запусти бота.
  2. Со своего аккаунта (должен быть в ADMIN_IDS) отправь боту MP3-файл.
  3. Бот ответит сообщением с file_id — скопируй и вставь сюда.

Подробности — в handlers/examples.py.
"""

# Каждый пример: file_id (Telegram) + подпись (HTML).
# Порядок в списке = порядок отправки пользователю.
EXAMPLE_SONGS: list[dict] = [
    {
        "file_id": "CQACAgIAAxkBAAIH8GoAAc_scBjehzGodsGupq0krKNnZwACFacAAkDiCUjc6-rwb1VYfDsE",
        "caption": "💖 <b>Песня для любимого человека</b>",
    },
    {
        "file_id": "CQACAgIAAxkBAAIH7moAAc-wkJrnG9lGB2zBrhtiTK3XmQACDacAAkDiCUgV-ChmYSeh2TsE",
        "caption": "🎂 <b>Туған күнімен құттықтау</b>",
    },
    {
        "file_id": "CQACAgIAAxkBAAIH7GoAAclBYFVKaxIObLpDXeBVnPNHnAACyaYAAkDiCUj_HUnyA4s_kTsE",
        "caption": "👨‍👩‍👧 <b>Песня для мамы и папы</b>",
    },
]


def examples_ready() -> bool:
    """True если все file_id заполнены (нет плейсхолдеров TODO_)."""
    return bool(EXAMPLE_SONGS) and all(
        not e["file_id"].startswith("TODO_") for e in EXAMPLE_SONGS
    )
