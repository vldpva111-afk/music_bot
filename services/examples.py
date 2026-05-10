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
        "file_id": "TODO_PASTE_FILE_ID_1",
        "caption": "👨‍👩‍👧 <b>Песня родителям</b> · на русском",
    },
    {
        "file_id": "TODO_PASTE_FILE_ID_2",
        "caption": "🎂 <b>Поздравление подруги с Днём рождения</b> · на казахском",
    },
    {
        "file_id": "TODO_PASTE_FILE_ID_3",
        "caption": "💕 <b>Любовная песня любимому</b> · на русском",
    },
]


def examples_ready() -> bool:
    """True если все file_id заполнены (нет плейсхолдеров TODO_)."""
    return bool(EXAMPLE_SONGS) and all(
        not e["file_id"].startswith("TODO_") for e in EXAMPLE_SONGS
    )
