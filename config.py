"""
Конфигурация бота. Читает переменные окружения из .env файла.
Валидирует обязательные переменные при старте — чтобы падать сразу с понятной ошибкой.
"""

from dotenv import load_dotenv
import os

# Имя файла можно переопределить через ENV_FILE (удобно для деплоя)
_env_file = os.getenv("ENV_FILE", ".env")
load_dotenv(_env_file)


class Settings:
    BOT_TOKEN           = os.getenv("BOT_TOKEN")
    OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY")
    MUSIC_API_KEY       = os.getenv("MUSIC_API_KEY")
    MUSIC_API_URL       = os.getenv("MUSIC_API_URL")
    MUSIC_CALLBACK_URL  = os.getenv("MUSIC_CALLBACK_URL")   # опционально

    # Railway автоматически добавляет эти переменные при подключении плагинов
    DATABASE_URL        = os.getenv("DATABASE_URL")          # PostgreSQL
    REDIS_URL           = os.getenv("REDIS_URL")             # Redis

    # Максимум бесплатных генераций в день
    FREE_DAILY_LIMIT: int = int(os.getenv("FREE_DAILY_LIMIT", "3"))

    # Список Telegram ID администраторов через запятую: 123456,789012
    ADMIN_IDS: frozenset[int] = frozenset(
        int(x.strip())
        for x in os.getenv("ADMIN_IDS", "").split(",")
        if x.strip().isdigit()
    )

    # ── OpenAI ────────────────────────────────────────────────────────────────
    # Вынесено в конфиг — меняй модель и температуры без правки кода сервиса
    OPENAI_MODEL: str                  = os.getenv("OPENAI_MODEL", "gpt-4o")
    OPENAI_TEMPERATURE_GENERATE: float = float(os.getenv("OPENAI_TEMPERATURE_GENERATE", "0.85"))
    OPENAI_TEMPERATURE_EDIT: float     = float(os.getenv("OPENAI_TEMPERATURE_EDIT", "0.75"))

    # ── Suno / Music API ──────────────────────────────────────────────────────
    MUSIC_MODEL: str = os.getenv("MUSIC_MODEL", "V4_5ALL")

    # ── Приветственное изображение ────────────────────────────────────────────
    WELCOME_IMAGE_URL: str = os.getenv(
        "WELCOME_IMAGE_URL",
        "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=800&q=80",
    )

    def validate(self) -> None:
        """Проверяет обязательные переменные. Вызывать при старте приложения."""
        required = {
            "BOT_TOKEN":      self.BOT_TOKEN,
            "OPENAI_API_KEY": self.OPENAI_API_KEY,
            "DATABASE_URL":   self.DATABASE_URL,
            "REDIS_URL":      self.REDIS_URL,
        }
        missing = [name for name, val in required.items() if not val]
        if missing:
            raise EnvironmentError(
                f"Отсутствуют обязательные переменные окружения: {', '.join(missing)}\n"
                f"Проверь файл {_env_file}"
            )


settings = Settings()
