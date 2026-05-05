"""
Конфигурация бота. Читает переменные окружения из .env файла.
"""

from dotenv import load_dotenv

import os

load_dotenv("mana.env")  # важно явно указать файл

class Settings:

    BOT_TOKEN = os.getenv("BOT_TOKEN")

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    MUSIC_API_KEY = os.getenv("MUSIC_API_KEY")

    MUSIC_API_URL = os.getenv("MUSIC_API_URL")


settings = Settings()
