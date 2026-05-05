"""
Подключение к PostgreSQL через asyncpg.
Создаёт таблицы при первом запуске (если не существуют).
"""

import logging
import asyncpg
from config import settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=settings.DATABASE_URL,
            min_size=2,
            max_size=10,
        )
        await _create_tables(_pool)
        logger.info("PostgreSQL пул подключений создан.")
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL пул закрыт.")


async def _create_tables(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id          BIGSERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                username    TEXT,
                first_name  TEXT,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS generations (
                id          BIGSERIAL PRIMARY KEY,
                telegram_id BIGINT NOT NULL REFERENCES users(telegram_id),
                genre       TEXT,
                mood        TEXT,
                voice       TEXT,
                lang        TEXT,
                has_music   BOOLEAN DEFAULT FALSE,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # Индекс для быстрого подсчёта генераций за день
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_generations_user_date
            ON generations (telegram_id, created_at);
        """)

    logger.info("Таблицы БД проверены / созданы.")


# ── Пользователи ──────────────────────────────────────────────────────────────

async def upsert_user(telegram_id: int, username: str | None, first_name: str | None) -> None:
    """Создаёт пользователя или обновляет username при повторном /start."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (telegram_id, username, first_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (telegram_id) DO UPDATE
                SET username   = EXCLUDED.username,
                    first_name = EXCLUDED.first_name;
        """, telegram_id, username, first_name)


# ── Лимиты ────────────────────────────────────────────────────────────────────

async def count_generations_today(telegram_id: int) -> int:
    """Возвращает количество генераций пользователя за сегодня (по UTC)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT COUNT(*) AS cnt
            FROM generations
            WHERE telegram_id = $1
              AND created_at >= CURRENT_DATE::TIMESTAMPTZ;
        """, telegram_id)
        return row["cnt"]


async def log_generation(
    telegram_id: int,
    genre: str,
    mood: str,
    voice: str,
    lang: str,
    has_music: bool = False,
) -> int:
    """
    Записывает факт генерации текста в БД.
    Возвращает id записи — чтобы позже обновить has_music.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO generations (telegram_id, genre, mood, voice, lang, has_music)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id;
        """, telegram_id, genre, mood, voice, lang, has_music)
        return row["id"]


async def mark_music_done(generation_id: int) -> None:
    """Помечает генерацию как завершённую с музыкой."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE generations SET has_music = TRUE WHERE id = $1;
        """, generation_id)
