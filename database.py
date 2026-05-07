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


async def try_log_generation(
    telegram_id: int,
    genre: str,
    mood: str,
    voice: str,
    lang: str,
    daily_limit: int,
) -> int | None:
    """
    Атомарно проверяет лимит и записывает генерацию в одной транзакции.

    Использует SELECT ... FOR UPDATE чтобы заблокировать строки пользователя
    на время проверки — исключает race condition при параллельных запросах.

    Возвращает id новой записи, если лимит не исчерпан.
    Возвращает None, если лимит исчерпан.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Блокируем строки пользователя за сегодня — FOR UPDATE не даёт
            # параллельному запросу пройти до коммита этой транзакции
            row = await conn.fetchrow("""
                SELECT COUNT(*) AS cnt
                FROM generations
                WHERE telegram_id = $1
                  AND created_at >= CURRENT_DATE::TIMESTAMPTZ
                FOR UPDATE;
            """, telegram_id)

            if row["cnt"] >= daily_limit:
                return None

            new_row = await conn.fetchrow("""
                INSERT INTO generations (telegram_id, genre, mood, voice, lang, has_music)
                VALUES ($1, $2, $3, $4, $5, FALSE)
                RETURNING id;
            """, telegram_id, genre, mood, voice, lang)

            return new_row["id"]


async def log_generation(
    telegram_id: int,
    genre: str,
    mood: str,
    voice: str,
    lang: str,
    has_music: bool = False,
) -> int:
    """
    Записывает факт генерации текста в БД без проверки лимита.
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


# ── Статистика ────────────────────────────────────────────────────────────────

async def get_stats() -> dict:
    """Возвращает сводную статистику для команды /stats."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                -- Пользователи
                (SELECT COUNT(*)            FROM users)                                         AS users_total,
                (SELECT COUNT(*)            FROM users  WHERE created_at >= CURRENT_DATE)       AS users_today,
                (SELECT COUNT(*)            FROM users  WHERE created_at >= NOW() - INTERVAL '7 days') AS users_week,

                -- Тексты (все генерации)
                (SELECT COUNT(*)            FROM generations)                                   AS texts_total,
                (SELECT COUNT(*)            FROM generations WHERE created_at >= CURRENT_DATE)  AS texts_today,
                (SELECT COUNT(*)            FROM generations WHERE created_at >= NOW() - INTERVAL '7 days') AS texts_week,

                -- Музыка (только has_music = true)
                (SELECT COUNT(*)            FROM generations WHERE has_music = TRUE)            AS music_total,
                (SELECT COUNT(*)            FROM generations WHERE has_music = TRUE AND created_at >= CURRENT_DATE) AS music_today,
                (SELECT COUNT(*)            FROM generations WHERE has_music = TRUE AND created_at >= NOW() - INTERVAL '7 days') AS music_week,

                -- Конверсия текст → музыка (%)
                (SELECT ROUND(
                    100.0 * COUNT(*) FILTER (WHERE has_music = TRUE) / NULLIF(COUNT(*), 0), 1
                ) FROM generations)                                                             AS conversion_pct,

                -- Среднее генераций на пользователя
                (SELECT ROUND(
                    COUNT(*)::NUMERIC / NULLIF((SELECT COUNT(*) FROM users), 0), 1
                ) FROM generations)                                                             AS avg_per_user
        """)

        return {
            "users_total":      row["users_total"],
            "users_today":      row["users_today"],
            "users_week":       row["users_week"],
            "texts_total":      row["texts_total"],
            "texts_today":      row["texts_today"],
            "texts_week":       row["texts_week"],
            "music_total":      row["music_total"],
            "music_today":      row["music_today"],
            "music_week":       row["music_week"],
            "conversion_pct":   row["conversion_pct"] or 0,
            "avg_per_user":     row["avg_per_user"] or 0,
        }
