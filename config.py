"""
Конфигурация бота. Читает переменные окружения из .env файла.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BOT_TOKEN: str
    OPENAI_API_KEY: str

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
