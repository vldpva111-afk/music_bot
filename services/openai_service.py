"""
Сервис для работы с OpenAI API.
Генерирует тексты песен на основе параметров пользователя.
Промпты живут в prompts.py — редактируй только там.
"""

import logging
import re

from openai import AsyncOpenAI
from config import settings
from services.prompts import build_generate_prompt, build_edit_prompt

logger = logging.getLogger(__name__)


# ── Постобработка ответа OpenAI ───────────────────────────────────────────────
# Модель регулярно нарушает запреты и добавляет: предисловия («Отличное! Я убрал...»),
# заголовки («Название: ...»), мета-теги в скобках («(Легкий ритм)»), которые Suno
# зачитывает голосом и портит песню. Чистим программно — defense in depth.

# Маркеры секций песни (после первого такого начинается «настоящий» текст)
_SECTION_PATTERN = re.compile(
    r"^\s*\[?\s*(Куплет|Припев|Бридж|Предприпев|Переход|Вступление|Финал|"
    r"Verse|Chorus|Bridge|Pre-?chorus|Hook|Intro|Outro|Pre|Post)",
    re.IGNORECASE,
)

# Префиксы строк, которые точно являются прологом / болтовнёй модели
_PROLOGUE_PREFIXES = (
    # Заголовки и подписи модели
    "название:", "title:",
    # Универсальные «вступительные» обороты
    "вот ", "готово", "надеюсь",
    "отлично", "отличное", "хорошо",
    "конечно", "понял", "поняла",
    "помните,", "помните ",
    "обратите внимание", "кстати",
    # «Я что-то сделал» — болтовня про сами правки
    "я убрал", "я добавил", "я сделал", "я переписал",
    "я изменил", "я постарался", "я попытался", "я попробовал",
    # Описания того, какой получилась песня
    "теперь песня", "теперь текст",
    "получилась", "получился",
    "надеюсь, песня", "надеюсь, текст",
    # Заигрывания с пользователем
    "как тебе", "как вам",
    # Английские эквиваленты (на случай en/смешанных запросов)
    "here is", "here's", "here you go",
    "i removed", "i added", "i changed",
    "hope you", "hope this",
)

# Ключевые слова, по которым опознаётся stage-direction в скобках
# (если в скобочной фразе есть хоть одно из этих слов — это режиссёрская ремарка,
# а не часть лирики; убираем).
_STAGE_KEYWORDS = (
    "ритм", "пауза", "тише", "громче", "бит", "соло", "крик",
    "шёпот", "шепот", "гитара", "затихающ", "вступает", "звучит",
    "настрой", "аккорд", "барабан", "бас", "припев играет",
    "fade", "intro", "outro",
)

_INLINE_STAGE_RE = re.compile(
    r"\(\s*[^()]*?(?:" + "|".join(_STAGE_KEYWORDS) + r")[^()]*?\)",
    re.IGNORECASE,
)


def _clean_lyrics(text: str) -> str:
    """
    Чистит ответ OpenAI от пролога, заголовка и stage-directions перед отправкой в Suno.

    1. Отрезает всё до первой секционной метки или первой стихотворной строки.
    2. Удаляет строки «Название: ...» и stage-directions в скобках.
    3. Удаляет inline-ремарки внутри строк ((Легкий ритм)).
    4. Сжимает подряд идущие пустые строки.
    """
    if not text:
        return text

    lines = text.split("\n")

    # 1. Найти первую «настоящую» строку песни
    start = 0
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        if _SECTION_PATTERN.match(s):
            start = i
            break
        low = s.lower()
        if any(low.startswith(p) for p in _PROLOGUE_PREFIXES):
            continue
        # Чистый stage-direction в скобках
        if re.fullmatch(r"\(.*?\)", s) and any(k in low for k in _STAGE_KEYWORDS):
            continue
        # Похоже на обычную строку песни — стартуем с неё
        start = i
        break

    # 2. Фильтруем тело
    out: list[str] = []
    for line in lines[start:]:
        s = line.strip()
        low = s.lower()

        # Пустая строка — оставляем (структурный разделитель)
        if not s:
            out.append("")
            continue

        # «Название: ...» где-то в середине
        if low.startswith(("название:", "title:")):
            continue

        # Целая строка-ремарка в скобках
        if re.fullmatch(r"\(.*?\)", s) and any(k in low for k in _STAGE_KEYWORDS):
            continue

        # Inline-ремарка внутри строки — вырезаем
        cleaned = _INLINE_STAGE_RE.sub("", line).rstrip()

        # Если после вырезания осталась пустая или почти пустая строка — пропускаем
        if not cleaned.strip():
            continue

        out.append(cleaned)

    # 3. Сжимаем подряд идущие пустые строки
    result: list[str] = []
    prev_empty = False
    for line in out:
        is_empty = not line.strip()
        if is_empty and prev_empty:
            continue
        prev_empty = is_empty
        result.append(line)

    return "\n".join(result).strip()

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
        raw = response.choices[0].message.content.strip()
        song_text = _clean_lyrics(raw)
        if len(raw) - len(song_text) > 20:
            logger.warning(
                "Очистили текст генерации: %d → %d символов (модель добавила мусор)",
                len(raw), len(song_text),
            )
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
        raw = response.choices[0].message.content.strip()
        edited_song = _clean_lyrics(raw)
        if len(raw) - len(edited_song) > 20:
            logger.warning(
                "Очистили текст правки: %d → %d символов (модель добавила пролог/ремарки)",
                len(raw), len(edited_song),
            )
        logger.info("Правки успешно внесены.")
        return edited_song

    except Exception as e:
        logger.error("Ошибка OpenAI при редактировании песни: %s", e)
        raise
