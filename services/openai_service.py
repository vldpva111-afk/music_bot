"""
Сервис для работы с OpenAI API.
Генерирует тексты песен на основе параметров пользователя.
Промпты живут в prompts.py — редактируй только там.
"""

import logging
from openai import AsyncOpenAI
from config import settings
from services.prompts import build_generate_prompt, build_edit_prompt

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=settings.OPENAI_TIMEOUT,
        )
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
    system_prompt, user_prompt = build_generate_prompt(
        genre=genre, mood=mood, voice=voice, details=details, lang=lang,
    )

    logger.info(
        "Генерируем песню: жанр=%s, настроение=%s, голос=%s, язык=%s",
        genre, mood, voice, lang,
    )

    try:
        response = await get_client().chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=settings.OPENAI_MAX_TOKENS,
            temperature=settings.OPENAI_TEMPERATURE_GENERATE,
        )
        song_text = response.choices[0].message.content.strip()
        logger.info("Текст песни успешно сгенерирован.")
        return song_text

    except Exception as e:
        logger.error("Ошибка OpenAI при генерации песни: %s", e)
        raise


async def edit_song(
    original_song: str,
    edit_request: str,
    genre: str | None = None,
    mood: str | None = None,
    voice: str | None = None,
) -> str:
    """
    Вносит правки в существующий текст песни.
    Принимает контекст жанра/настроения/голоса чтобы сохранить стиль.

    Args:
        original_song: оригинальный текст песни
        edit_request:  пожелания пользователя по правкам
        genre:         callback_data жанра (опционально)
        mood:          callback_data настроения (опционально)
        voice:         callback_data голоса (опционально)

    Returns:
        Исправленный текст песни.
    """
    system_prompt, user_prompt = build_edit_prompt(
        original_song=original_song,
        edit_request=edit_request,
        genre=genre,
        mood=mood,
        voice=voice,
    )

    logger.info("Редактируем текст песни по запросу пользователя.")

    try:
        response = await get_client().chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=settings.OPENAI_MAX_TOKENS,
            temperature=settings.OPENAI_TEMPERATURE_EDIT,
        )
        edited_song = response.choices[0].message.content.strip()
        logger.info("Правки успешно внесены.")
        return edited_song

    except Exception as e:
        logger.error("Ошибка OpenAI при редактировании песни: %s", e)
        raise
