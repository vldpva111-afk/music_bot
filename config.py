"""
Конфигурация бота. Читает переменные окружения из .env файла.
"""

from dotenv import load_dotenv
import os

load_dotenv("mana.env")


class Settings:
    BOT_TOKEN      = os.getenv("BOT_TOKEN")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    MUSIC_API_KEY  = os.getenv("MUSIC_API_KEY")
    MUSIC_API_URL  = os.getenv("MUSIC_API_URL")

    # Railway автоматически добавляет эти переменные при подключении плагинов
    DATABASE_URL   = os.getenv("DATABASE_URL")   # PostgreSQL
    REDIS_URL      = os.getenv("REDIS_URL")       # Redis

    # Максимум бесплатных генераций в день
    FREE_DAILY_LIMIT: int = 3


settings = Settings()
