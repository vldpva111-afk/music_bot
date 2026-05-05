"""
Сервис для работы с OpenAI API.
Генерирует тексты песен на основе параметров пользователя.
"""

import logging
from openai import AsyncOpenAI
from config import settings
from constants import GENRE_LABELS, MOOD_LABELS, VOICE_LABELS, LANG_PROMPT_LABELS

logger = logging.getLogger(__name__)

# Синглтон — создаём клиент один раз при импорте модуля
_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


async def generate_song(
    genre: str,
    mood: str,
    voice: str,
    details: str,
    lang: str = "ru",
) -> str:
    """
    Генерирует текст песни через OpenAI API.

    Args:
        genre:   callback_data жанра (напр. 'genre_rap')
        mood:    callback_data настроения (напр. 'mood_happy')
        voice:   callback_data голоса (напр. 'voice_male')
        details: свободный текст с описанием человека
        lang:    код языка ('ru', 'kz', 'tt', 'uz', 'en')

    Returns:
        Готовый текст песни.
    """
    genre_label = GENRE_LABELS.get(genre, genre)
    mood_label  = MOOD_LABELS.get(mood, mood)
    voice_label = VOICE_LABELS.get(voice, voice)
    lang_label  = LANG_PROMPT_LABELS.get(lang, "русском")

    prompt = f"""Ты — талантливый автор текстов песен.

Напиши персональный текст песни на {lang_label} языке со следующими параметрами:
- Жанр: {genre_label}
- Настроение: {mood_label}
- Стиль подачи текста (лирическая персона): {voice_label} голос (тон, подача и стиль написания строк)
- Информация о человеке, которому посвящена песня: {details}

Требования к тексту:
1. Структура: куплет + припев + куплет + припев
2. Обязательно используй рифмы в словах
3. Песня должна быть эмоциональной и личной
4. Упомяни имя и детали из описания человека
5. Соответствуй стилю жанра {genre_label}
6. Не слишком длинно — до 150 слов

Формат ответа:
[Куплет 1]
...

[Припев]
...

[Куплет 2]
...

[Припев]
...
"""

    # ВАЖНО: system prompt НЕ фиксирует язык — язык задаётся через prompt выше
    system_prompt = (
        "Ты профессиональный автор текстов песен. "
        "Пишешь на том языке, который указан в запросе пользователя. "
        "Создаёшь живые, эмоциональные и рифмованные тексты."
    )

    logger.info(
        f"Генерируем песню: жанр={genre_label}, настроение={mood_label}, "
        f"голос={voice_label}, язык={lang_label}"
    )

    try:
        response = await get_client().chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=1000,
            temperature=0.85,
        )
        song_text = response.choices[0].message.content.strip()
        logger.info("Текст песни успешно сгенерирован.")
        return song_text

    except Exception as e:
        logger.error(f"Ошибка OpenAI при генерации песни: {e}")
        raise


async def edit_song(original_song: str, edit_request: str) -> str:
    """
    Вносит правки в существующий текст песни.

    Args:
        original_song: оригинальный текст песни
        edit_request:  пожелания пользователя по правкам

    Returns:
        Исправленный текст песни.
    """
    prompt = f"""У тебя есть текст песни:

{original_song}

Пользователь просит внести следующие правки:
{edit_request}

Внеси правки, сохраняя общую структуру, рифму и стиль песни.
Верни только обновлённый текст песни без лишних комментариев.
"""

    logger.info("Редактируем текст песни по запросу пользователя.")

    try:
        response = await get_client().chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты профессиональный редактор текстов песен. "
                        "Вносишь правки аккуратно, сохраняя стиль и структуру."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=1000,
            temperature=0.75,
        )
        edited_song = response.choices[0].message.content.strip()
        logger.info("Правки успешно внесены.")
        return edited_song

    except Exception as e:
        logger.error(f"Ошибка OpenAI при редактировании песни: {e}")
        raise
