"""
Общие константы бота — жанры, настроения, голоса, языки.
Единственный источник правды. Импортируй отсюда, не дублируй.
"""

# ── Жанры ─────────────────────────────────────────────────────────────────────

GENRE_LABELS: dict[str, str] = {
    "genre_rap":     "🎤 Рэп/хип-хоп",
    "genre_pop":     "🎶 Поп",
    "genre_rock":    "🎸 Рок",
    "genre_chanson": "🎻 Шансон",
    "genre_disco":   "🕺 Диско 80-х",
    "genre_classic": "🎼 Классика",
}

# Стиль для передачи в Suno API
GENRE_STYLE: dict[str, str] = {
    "genre_rap":     "Hip-hop rap",
    "genre_pop":     "Pop",
    "genre_rock":    "Rock",
    "genre_chanson": "Chanson",
    "genre_disco":   "Disco 80s",
    "genre_classic": "Classical",
}

VALID_GENRES: frozenset[str] = frozenset(GENRE_LABELS)

# ── Настроения ────────────────────────────────────────────────────────────────

MOOD_LABELS: dict[str, str] = {
    "mood_happy": "😄 Радостное",
    "mood_sad":   "😢 Грустное",
    "mood_calm":  "😌 Спокойное",
    "mood_love":  "❤️ Любовное",
}

MOOD_STYLE: dict[str, str] = {
    "mood_happy": "upbeat joyful",
    "mood_sad":   "melancholic sad",
    "mood_calm":  "calm relaxing",
    "mood_love":  "romantic loving",
}

VALID_MOODS: frozenset[str] = frozenset(MOOD_LABELS)

# ── Голоса ────────────────────────────────────────────────────────────────────

VOICE_LABELS: dict[str, str] = {
    "voice_male":   "👨 Мужской",
    "voice_female": "👩 Женский",
}

VOICE_STYLE: dict[str, str] = {
    "voice_male":   "male vocals",
    "voice_female": "female vocals",
}

VALID_VOICES: frozenset[str] = frozenset(VOICE_LABELS)

# ── Языки ─────────────────────────────────────────────────────────────────────

LANG_LABELS: dict[str, str] = {
    "ru": "🇷🇺 Русский",
    "kz": "🇰🇿 Қазақша",
    "tt": "🇷🇺 Татарча",
    "uz": "🇺🇿 Oʻzbekcha",
    "en": "🇬🇧 English",
}

# Полное название для промпта OpenAI
LANG_PROMPT_LABELS: dict[str, str] = {
    "ru": "русском",
    "kz": "казахском",
    "tt": "татарском",
    "uz": "узбекском",
    "en": "английском",
}

VALID_LANGS: frozenset[str] = frozenset(LANG_LABELS)


# ── Тарифы (оплата через Kaspi, ручная обработка) ─────────────────────────────

# key (callback_data) → описание пакета.
# Цены в тенге, credits — сколько песен начисляется после оплаты.
PACKAGES: dict[str, dict] = {
    "pkg_1":  {"credits": 1,  "price": 790,  "label": "1 песня",   "per_unit": 790},
    "pkg_3":  {"credits": 3,  "price": 1990, "label": "3 песни",   "per_unit": 663},
    "pkg_5":  {"credits": 5,  "price": 2990, "label": "5 песен",   "per_unit": 598},
    "pkg_10": {"credits": 10, "price": 4990, "label": "10 песен",  "per_unit": 499},
}

VALID_PACKAGES: frozenset[str] = frozenset(PACKAGES)
