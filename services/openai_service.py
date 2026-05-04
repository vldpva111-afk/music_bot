"""
Сервис для работы с OpenAI API.
Генерирует тексты песен на основе параметров пользователя.
"""

import logging
from openai import AsyncOpenAI
from config import settings

logger = logging.getLogger(__name__)

# Инициализируем клиент один раз при импорте модуля
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

# Словари для человекочитаемых названий
GENRE_LABELS = {
    "genre_rap": "Рэп/хип-хоп",
    "genre_pop": "Поп",
    "genre_rock": "Рок",
    "genre_chanson": "Шансон",
    "genre_disco": "Диско 80-х",
    "genre_classic": "Классика",
}

MOOD_LABELS = {
    "mood_happy": "радостное",
    "mood_sad": "грустное",
    "mood_calm": "спокойное",
    "mood_love": "любовное",
}

VOICE_LABELS = {
    "voice_male": "мужской",
    "voice_female": "женский",
}


async def generate_song(
    genre: str,
    mood: str,
    voice: str,
    details: str,
) -> str:
    """
    Генерирует текст песни через OpenAI API.

    Args:
        genre: callback_data жанра (напр. 'genre_rap')
        mood: callback_data настроения (напр. 'mood_happy')
        voice: callback_data голоса (напр. 'voice_male')
        details: свободный текст с описанием человека

    Returns:
        Готовый текст песни или сообщение об ошибке.
    """
    genre_label = GENRE_LABELS.get(genre, genre)
    mood_label = MOOD_LABELS.get(mood, mood)
    voice_label = VOICE_LABELS.get(voice, voice)

    prompt = f"""Ты — талантливый автор текстов песен.

Напиши уникальный персонализированный текст песни на русском языке со следующими параметрами:
- Жанр: {genre_label}
- Настроение: {mood_label}
- Голос исполнителя: {voice_label}
- Информация о человеке, которому посвящена песня: {details}

Требования к тексту:
1. Структура: 2 куплета + припев (припев повторяется после каждого куплета)
2. Обязательно используй рифмы
3. Песня должна быть эмоциональной и личной
4. Упомяни детали из описания человека
5. Соответствуй стилю жанра {genre_label}
6. Длина: примерно 16-24 строки

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

    logger.info(f"Генерируем песню: жанр={genre_label}, настроение={mood_label}, голос={voice_label}")

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "Ты профессиональный автор текстов песен. Пишешь только на русском языке. Создаёшь живые, эмоциональные и рифмованные тексты.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=1000,
            temperature=0.85,
        )
        song_text = response.choices[0].message.content.strip()
        logger.info("Текст песни успешно сгенерирован.")
        return song_text

   except Exception as e:
        logger.exception("OPENAI ERROR")
        return f"ERROR: {e}"


async def edit_song(original_song: str, edit_request: str) -> str:
    """
    Вносит правки в существующий текст песни.

    Args:
        original_song: оригинальный текст песни
        edit_request: пожелания пользователя по правкам

    Returns:
        Исправленный текст песни или сообщение об ошибке.
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
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "Ты профессиональный редактор текстов песен. Вносишь правки аккуратно, сохраняя стиль и структуру.",
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
