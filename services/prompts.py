"""
Промпты для OpenAI API. Единственное место где редактируются тексты запросов.
"""

from constants import GENRE_LABELS, MOOD_LABELS, VOICE_LABELS, LANG_PROMPT_LABELS


def build_generate_prompt(
    genre: str,
    mood: str,
    voice: str,
    details: str,
    lang: str,
) -> tuple[str, str]:
    """
    Возвращает (system_prompt, user_prompt) для генерации текста песни.
    """
    genre_label = GENRE_LABELS.get(genre, genre)
    mood_label  = MOOD_LABELS.get(mood, mood)
    voice_label = VOICE_LABELS.get(voice, voice)
    lang_label  = LANG_PROMPT_LABELS.get(lang, "русском")

    system_prompt = (
        "Ты профессиональный автор текстов песен. "
        "Пишешь на том языке, который указан в запросе пользователя. "
        "Создаёшь живые, эмоциональные и рифмованные тексты."
    )

    user_prompt = f"""Ты — талантливый автор текстов песен.

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
    return system_prompt, user_prompt


def build_edit_prompt(
    original_song: str,
    edit_request: str,
    genre: str | None = None,
    mood: str | None = None,
    voice: str | None = None,
) -> tuple[str, str]:
    """
    Возвращает (system_prompt, user_prompt) для редактирования песни.
    Принимает опциональный контекст жанра/настроения/голоса чтобы
    модель не съезжала со стиля при правках.
    """
    context_lines = []
    if genre:
        context_lines.append(f"- Жанр: {GENRE_LABELS.get(genre, genre)}")
    if mood:
        context_lines.append(f"- Настроение: {MOOD_LABELS.get(mood, mood)}")
    if voice:
        context_lines.append(f"- Голос: {VOICE_LABELS.get(voice, voice)}")

    context_block = (
        "\nСохраняй оригинальный стиль:\n" + "\n".join(context_lines) + "\n"
        if context_lines else ""
    )

    system_prompt = (
        "Ты профессиональный редактор текстов песен. "
        "Вносишь правки аккуратно, сохраняя стиль и структуру."
    )

    user_prompt = f"""У тебя есть текст песни:

{original_song}
{context_block}
Пользователь просит внести следующие правки:
{edit_request}

Внеси правки, сохраняя общую структуру, рифму и стиль песни.
Верни только обновлённый текст песни без лишних комментариев.
"""
    return system_prompt, user_prompt
