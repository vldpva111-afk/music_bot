"""
Подключение к PostgreSQL через asyncpg.
Создаёт таблицы при первом запуске (если не существуют).
"""

import logging
import asyncpg
from config import settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None

# Максимум реферальных бонусов на одного пользователя
MAX_REFERRAL_BONUS = 5


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
                id             BIGSERIAL PRIMARY KEY,
                telegram_id    BIGINT UNIQUE NOT NULL,
                username       TEXT,
                first_name     TEXT,
                referred_by    BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
                bonus_credits  INT NOT NULL DEFAULT 0,
                free_used      BOOLEAN NOT NULL DEFAULT FALSE,
                created_at     TIMESTAMPTZ DEFAULT NOW()
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

        # Миграция: добавляем новые колонки если таблица уже существовала
        for col, definition in [
            ("referred_by",   "BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL"),
            ("bonus_credits", "INT NOT NULL DEFAULT 0"),
            ("free_used",     "BOOLEAN NOT NULL DEFAULT FALSE"),
        ]:
            await conn.execute(f"""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {definition};
            """)

    logger.info("Таблицы БД проверены / созданы.")


# ── Пользователи ──────────────────────────────────────────────────────────────

async def upsert_user(
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    referred_by: int | None = None,
) -> bool:
    """
    Создаёт пользователя или обновляет username при повторном /start.
    referred_by — telegram_id пригласившего, применяется только при первом создании.
    Возвращает True если пользователь создан впервые, False если уже существовал.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # COALESCE — не затираем сохранённые username/first_name, если
        # в текущем апдейте Telegram прислал NULL (юзер скрыл username и т.п.)
        row = await conn.fetchrow("""
            INSERT INTO users (telegram_id, username, first_name, referred_by)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (telegram_id) DO UPDATE
                SET username   = COALESCE(EXCLUDED.username,   users.username),
                    first_name = COALESCE(EXCLUDED.first_name, users.first_name)
            RETURNING (xmax = 0) AS is_new;
        """, telegram_id, username, first_name, referred_by)
        return row["is_new"]


# ── Реферальная система ───────────────────────────────────────────────────────

async def apply_referral_bonus(referrer_id: int) -> bool:
    """
    Начисляет +1 бонусный кредит рефереру, если не превышен MAX_REFERRAL_BONUS.
    Возвращает True если кредит начислен, False если лимит уже достигнут.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            UPDATE users
            SET bonus_credits = bonus_credits + 1
            WHERE telegram_id = $1
              AND bonus_credits < $2
            RETURNING bonus_credits;
        """, referrer_id, MAX_REFERRAL_BONUS)
        return row is not None


async def get_bonus_credits(telegram_id: int) -> int:
    """Возвращает текущий баланс бонусных кредитов пользователя."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT bonus_credits FROM users WHERE telegram_id = $1;
        """, telegram_id)
        return row["bonus_credits"] if row else 0


# ── Кредитная логика генерации ────────────────────────────────────────────────

async def try_consume_and_log(
    telegram_id: int,
    genre: str,
    mood: str,
    voice: str,
    lang: str,
) -> tuple[int, str] | None:
    """
    Атомарно проверяет наличие кредита и записывает генерацию.

    Порядок списания:
      1. Разовая бесплатная (free_used = FALSE) — для новых пользователей
      2. Бонусный кредит (bonus_credits > 0) — реферальные бонусы
      3. Платно — в будущем; сейчас возвращает None (нет доступа)

    Возвращает (generation_id, credit_type) где credit_type — одно из:
      'free'  — использована разовая бесплатная генерация
      'bonus' — списан реферальный кредит
    Возвращает None если кредитов нет.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Блокируем строку пользователя на время транзакции
            user = await conn.fetchrow("""
                SELECT free_used, bonus_credits
                FROM users
                WHERE telegram_id = $1
                FOR UPDATE;
            """, telegram_id)

            if not user:
                return None

            credit_type: str | None = None

            if not user["free_used"]:
                # Списываем разовую бесплатную
                await conn.execute("""
                    UPDATE users SET free_used = TRUE WHERE telegram_id = $1;
                """, telegram_id)
                credit_type = "free"

            elif user["bonus_credits"] > 0:
                # Списываем один бонусный кредит
                await conn.execute("""
                    UPDATE users SET bonus_credits = bonus_credits - 1
                    WHERE telegram_id = $1;
                """, telegram_id)
                credit_type = "bonus"

            else:
                # Нет доступных кредитов
                return None

            new_row = await conn.fetchrow("""
                INSERT INTO generations (telegram_id, genre, mood, voice, lang, has_music)
                VALUES ($1, $2, $3, $4, $5, FALSE)
                RETURNING id;
            """, telegram_id, genre, mood, voice, lang)

            return new_row["id"], credit_type


async def get_credits_info(telegram_id: int) -> dict:
    """
    Возвращает полную информацию о кредитах пользователя.
    Удобно для отображения остатка после генерации.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT free_used, bonus_credits FROM users WHERE telegram_id = $1;
        """, telegram_id)
        if not row:
            return {"free_available": False, "bonus_credits": 0}
        return {
            "free_available": not row["free_used"],
            "bonus_credits":  row["bonus_credits"],
        }


async def log_generation(
    telegram_id: int,
    genre: str,
    mood: str,
    voice: str,
    lang: str,
    has_music: bool = False,
) -> int:
    """Записывает факт генерации без проверки лимита. Используется для admins."""
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
                (SELECT COUNT(*)   FROM users)                                                   AS users_total,
                (SELECT COUNT(*)   FROM users  WHERE created_at >= CURRENT_DATE)                 AS users_today,
                (SELECT COUNT(*)   FROM users  WHERE created_at >= NOW() - INTERVAL '7 days')    AS users_week,

                -- Рефералы
                (SELECT COUNT(*)   FROM users  WHERE referred_by IS NOT NULL)                    AS referrals_total,
                (SELECT COALESCE(SUM(bonus_credits), 0) FROM users)                             AS bonus_credits_outstanding,

                -- Тексты (все генерации)
                (SELECT COUNT(*)   FROM generations)                                             AS texts_total,
                (SELECT COUNT(*)   FROM generations WHERE created_at >= CURRENT_DATE)            AS texts_today,
                (SELECT COUNT(*)   FROM generations WHERE created_at >= NOW() - INTERVAL '7 days') AS texts_week,

                -- Музыка (только has_music = true)
                (SELECT COUNT(*)   FROM generations WHERE has_music = TRUE)                      AS music_total,
                (SELECT COUNT(*)   FROM generations WHERE has_music = TRUE AND created_at >= CURRENT_DATE) AS music_today,
                (SELECT COUNT(*)   FROM generations WHERE has_music = TRUE AND created_at >= NOW() - INTERVAL '7 days') AS music_week,

                -- Конверсия текст → музыка (%)
                (SELECT ROUND(
                    100.0 * COUNT(*) FILTER (WHERE has_music = TRUE) / NULLIF(COUNT(*), 0), 1
                ) FROM generations)                                                              AS conversion_pct,

                -- Среднее генераций на пользователя
                (SELECT ROUND(
                    COUNT(*)::NUMERIC / NULLIF((SELECT COUNT(*) FROM users), 0), 1
                ) FROM generations)                                                              AS avg_per_user
        """)

        return {
            "users_total":             row["users_total"],
            "users_today":             row["users_today"],
            "users_week":              row["users_week"],
            "referrals_total":         row["referrals_total"],
            "bonus_credits_outstanding": row["bonus_credits_outstanding"],
            "texts_total":             row["texts_total"],
            "texts_today":             row["texts_today"],
            "texts_week":              row["texts_week"],
            "music_total":             row["music_total"],
            "music_today":             row["music_today"],
            "music_week":              row["music_week"],
            "conversion_pct":          row["conversion_pct"] or 0,
            "avg_per_user":            row["avg_per_user"] or 0,
        }