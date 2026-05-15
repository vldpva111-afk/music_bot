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

    # Список Telegram ID администраторов через запятую: 123456,789012
    # Задаётся исключительно через переменную окружения ADMIN_IDS
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
    OPENAI_MAX_TOKENS: int             = int(os.getenv("OPENAI_MAX_TOKENS", "1000"))
    OPENAI_TIMEOUT: float              = float(os.getenv("OPENAI_TIMEOUT", "60.0"))

    # ── Suno / Music API ──────────────────────────────────────────────────────
    MUSIC_MODEL: str    = os.getenv("MUSIC_MODEL", "V4_5ALL")
    MUSIC_TIMEOUT: float = float(os.getenv("MUSIC_TIMEOUT", "30.0"))

    # ── Приветственное изображение ────────────────────────────────────────────
    WELCOME_IMAGE_URL: str = os.getenv(
        "WELCOME_IMAGE_URL",
        "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=800&q=80",
    )

    # ── Юридическое ──────────────────────────────────────────────────────────
    # Ссылка на публичную оферту (Telegra.ph / Notion / любой публичный URL).
    # Показывается на экране покупки. Пусто — раздел про оферту не показываем.
    OFFER_URL: str = os.getenv("OFFER_URL", "")

    # ── Поддержка ────────────────────────────────────────────────────────────
    # Username аккаунта, куда юзер пишет при нажатии «Поддержка». Без @.
    # Пусто — кнопка поддержки не показывается.
    SUPPORT_USERNAME: str = os.getenv("SUPPORT_USERNAME", "").lstrip("@")

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

        if not self.ADMIN_IDS:
            raise EnvironmentError(
                "Переменная ADMIN_IDS не задана или пуста.\n"
                "Укажи хотя бы один Telegram ID администратора: ADMIN_IDS=123456789"
            )


settings = Settings()
