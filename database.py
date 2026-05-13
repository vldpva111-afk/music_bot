"""
Подключение к PostgreSQL через asyncpg.
Создаёт таблицы при первом запуске (если не существуют).
"""

import json
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

        # ── Журнал событий для воронки конверсии ──────────────────────────────
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS event_log (
                id          BIGSERIAL PRIMARY KEY,
                telegram_id BIGINT NOT NULL,
                event       TEXT NOT NULL,
                metadata    JSONB,
                ts          TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_event_log_event_ts
            ON event_log (event, ts DESC);
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_event_log_user_ts
            ON event_log (telegram_id, ts DESC);
        """)

        # ── Заказы (оплата через Kaspi, ручная обработка) ─────────────────────
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id            BIGSERIAL PRIMARY KEY,
                telegram_id   BIGINT NOT NULL,
                username      TEXT,
                first_name    TEXT,
                package_key   TEXT NOT NULL,
                credits       INT  NOT NULL,
                price         INT  NOT NULL,
                phone         TEXT NOT NULL,
                status        TEXT NOT NULL DEFAULT 'pending',
                created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                paid_at       TIMESTAMPTZ
            );
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_status_created
            ON orders (status, created_at DESC);
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_user_status
            ON orders (telegram_id, status);
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

        # ── Партнёры и выплаты ────────────────────────────────────────────────
        # commission_pct хранится как NUMERIC(5,2): возможны значения 0.00–100.00
        # с двумя знаками после запятой (например, 27.50).
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS partners (
                telegram_id     BIGINT PRIMARY KEY
                                REFERENCES users(telegram_id) ON DELETE CASCADE,
                display_name    TEXT,
                commission_pct  NUMERIC(5,2) NOT NULL DEFAULT 30.0,
                notes           TEXT,
                joined_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS partner_payouts (
                id          BIGSERIAL PRIMARY KEY,
                partner_id  BIGINT NOT NULL
                            REFERENCES partners(telegram_id) ON DELETE CASCADE,
                amount      INT  NOT NULL,
                comment     TEXT,
                paid_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_partner_payouts_partner
            ON partner_payouts (partner_id, paid_at DESC);
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


# ── Админские операции ────────────────────────────────────────────────────────

async def admin_add_bonus_credits(telegram_id: int, amount: int) -> int | None:
    """
    Начисляет N бонусных кредитов пользователю. Используется админом —
    лимит MAX_REFERRAL_BONUS не применяется.
    Возвращает новый баланс или None если пользователя нет в БД.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            UPDATE users
            SET bonus_credits = bonus_credits + $2
            WHERE telegram_id = $1
            RETURNING bonus_credits;
        """, telegram_id, amount)
        return row["bonus_credits"] if row else None


async def find_user_by_username(username: str) -> int | None:
    """
    Ищет telegram_id пользователя по username (регистронезависимо, без '@').
    Возвращает None если такого пользователя нет в БД.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT telegram_id FROM users
            WHERE LOWER(username) = LOWER($1);
        """, username)
        return row["telegram_id"] if row else None


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
                ) FROM generations)                                                              AS avg_per_user,

                -- Активность: уникальные юзеры, сделавшие любое действие (event_log)
                (SELECT COUNT(DISTINCT telegram_id) FROM event_log
                    WHERE ts >= CURRENT_DATE)                                                    AS active_today,
                (SELECT COUNT(DISTINCT telegram_id) FROM event_log
                    WHERE ts >= CURRENT_DATE - INTERVAL '1 day' AND ts < CURRENT_DATE)           AS active_yesterday,
                (SELECT COUNT(DISTINCT telegram_id) FROM event_log
                    WHERE ts >= CURRENT_DATE - INTERVAL '7 days')                                AS active_week,
                (SELECT COUNT(DISTINCT telegram_id) FROM event_log
                    WHERE ts >= CURRENT_DATE - INTERVAL '30 days')                               AS active_month,

                -- Новые vs возвращающиеся сегодня (разбивка DAU)
                (SELECT COUNT(DISTINCT el.telegram_id)
                    FROM event_log el
                    JOIN users u ON u.telegram_id = el.telegram_id
                    WHERE el.ts >= CURRENT_DATE
                      AND u.created_at >= CURRENT_DATE)                                          AS active_new_today,
                (SELECT COUNT(DISTINCT el.telegram_id)
                    FROM event_log el
                    JOIN users u ON u.telegram_id = el.telegram_id
                    WHERE el.ts >= CURRENT_DATE
                      AND u.created_at <  CURRENT_DATE)                                          AS active_returning_today
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
            "active_today":            row["active_today"],
            "active_yesterday":        row["active_yesterday"],
            "active_week":             row["active_week"],
            "active_month":            row["active_month"],
            "active_new_today":        row["active_new_today"],
            "active_returning_today":  row["active_returning_today"],
        }


# ── Журнал событий (воронка) ──────────────────────────────────────────────────

class Events:
    """
    Имена событий воронки. Использовать константы, а не строки —
    чтобы IDE подсвечивала опечатки и было где видеть полный список.
    Порядок объявления = порядок шагов воронки.
    """
    BOT_STARTED          = "bot_started"            # /start
    EXAMPLES_SHOWN       = "examples_shown"         # клик «🎧 Послушать примеры»
    BUY_CLICKED          = "buy_clicked"            # клик «💎 Купить кредиты»
    PACKAGE_SELECTED     = "package_selected"       # выбран тариф
    PHONE_SUBMITTED      = "phone_submitted"        # юзер отправил телефон
    ORDER_PAID           = "order_paid"             # админ подтвердил оплату
    FLOW_STARTED         = "flow_started"           # клик «🎵 Новая песня»
    GENRE_SELECTED       = "genre_selected"
    MOOD_SELECTED        = "mood_selected"
    VOICE_SELECTED       = "voice_selected"
    LANG_SELECTED        = "lang_selected"
    DETAILS_SUBMITTED    = "details_submitted"      # пользователь прислал текст
    NO_CREDITS_SHOWN     = "no_credits_shown"       # упёрся в кредиты
    TEXT_GENERATED       = "text_generated"         # успех генерации текста
    TEXT_FAILED          = "text_failed"
    EDIT_REQUESTED       = "edit_requested"         # клик «Внести правки»
    EDIT_APPLIED         = "edit_applied"
    REGENERATE_CLICKED   = "regenerate_clicked"
    MUSIC_STARTED        = "music_started"          # клик «Создать песню»
    MUSIC_DELIVERED      = "music_delivered"        # музыка отправлена
    MUSIC_FAILED         = "music_failed"


# Шаги воронки в порядке прохождения — для отчёта /funnel.
# Если хочешь добавить шаг — допиши в Events и сюда.
FUNNEL_STEPS = [
    Events.BOT_STARTED,
    Events.FLOW_STARTED,
    Events.GENRE_SELECTED,
    Events.MOOD_SELECTED,
    Events.VOICE_SELECTED,
    Events.DETAILS_SUBMITTED,
    Events.TEXT_GENERATED,
    Events.MUSIC_STARTED,
    Events.MUSIC_DELIVERED,
]


async def log_event(
    telegram_id: int,
    event: str,
    metadata: dict | None = None,
) -> None:
    """
    Пишет событие воронки. Best-effort: ошибки логируются, но не пробрасываются —
    падение БД не должно ломать пользовательский UX.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO event_log (telegram_id, event, metadata) "
                "VALUES ($1, $2, $3::jsonb);",
                telegram_id,
                event,
                json.dumps(metadata) if metadata else None,
            )
    except Exception as e:
        logger.warning(
            "log_event failed (event=%s, user=%d): %s",
            event, telegram_id, e,
        )


async def get_funnel_stats(period_days: int = 7) -> list[dict]:
    """
    Возвращает воронку за последние N дней:
      [{step, users_count, pct_from_start, pct_from_prev}, ...]
    users_count — уникальные пользователи, дошедшие до шага.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT event, COUNT(DISTINCT telegram_id) AS users_count
            FROM event_log
            WHERE ts >= NOW() - ($1 || ' days')::INTERVAL
              AND event = ANY($2::text[])
            GROUP BY event;
        """, str(period_days), FUNNEL_STEPS)

    counts = {r["event"]: r["users_count"] for r in rows}
    base = counts.get(FUNNEL_STEPS[0], 0)

    result = []
    prev = base
    for step in FUNNEL_STEPS:
        n = counts.get(step, 0)
        result.append({
            "step":           step,
            "users_count":    n,
            "pct_from_start": round(100.0 * n / base, 1) if base else 0.0,
            "pct_from_prev":  round(100.0 * n / prev, 1) if prev else 0.0,
        })
        prev = n if n > 0 else prev
    return result


# ── Заказы (Kaspi, ручная обработка) ──────────────────────────────────────────

async def create_order(
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    package_key: str,
    credits: int,
    price: int,
    phone: str,
) -> int:
    """Создаёт заказ в статусе pending. Возвращает id заказа."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO orders (
                telegram_id, username, first_name,
                package_key, credits, price, phone
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id;
        """, telegram_id, username, first_name, package_key, credits, price, phone)
        return row["id"]


async def get_pending_orders(limit: int = 20) -> list[dict]:
    """Возвращает свежие неоплаченные заказы (для админа)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, telegram_id, username, first_name,
                   package_key, credits, price, phone, created_at
            FROM orders
            WHERE status = 'pending'
            ORDER BY created_at DESC
            LIMIT $1;
        """, limit)
        return [dict(r) for r in rows]


async def mark_latest_order_paid(telegram_id: int) -> dict | None:
    """
    Помечает самый свежий pending-заказ юзера как оплаченный.
    Возвращает данные заказа или None если нет pending.
    Используется в /grant — чтобы одной командой и кредиты выдать,
    и заказ закрыть.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            UPDATE orders
            SET status = 'paid', paid_at = NOW()
            WHERE id = (
                SELECT id FROM orders
                WHERE telegram_id = $1 AND status = 'pending'
                ORDER BY created_at DESC
                LIMIT 1
            )
            RETURNING id, package_key, credits, price, phone;
        """, telegram_id)
        return dict(row) if row else None


# ── Партнёрская программа ─────────────────────────────────────────────────────

async def add_partner(
    telegram_id: int,
    display_name: str | None,
    commission_pct: float,
) -> bool:
    """
    Добавляет / обновляет партнёра. Возвращает True если юзер существует
    в `users` (иначе FK выкинет ошибку — но мы заранее проверяем).
    Идемпотентно: повторный вызов обновляет имя/процент.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Сначала убедимся что юзер вообще запускал бота
        user = await conn.fetchrow(
            "SELECT 1 FROM users WHERE telegram_id = $1;", telegram_id,
        )
        if not user:
            return False

        await conn.execute("""
            INSERT INTO partners (telegram_id, display_name, commission_pct)
            VALUES ($1, $2, $3)
            ON CONFLICT (telegram_id) DO UPDATE
              SET display_name   = COALESCE(EXCLUDED.display_name, partners.display_name),
                  commission_pct = EXCLUDED.commission_pct;
        """, telegram_id, display_name, commission_pct)
        return True


async def remove_partner(telegram_id: int) -> bool:
    """Удаляет партнёра. Возвращает True если был удалён, False если не было."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM partners WHERE telegram_id = $1;", telegram_id,
        )
        # asyncpg возвращает "DELETE 1" или "DELETE 0"
        return result.endswith("1")


async def get_partner(telegram_id: int) -> dict | None:
    """Возвращает данные партнёра или None."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT telegram_id, display_name, commission_pct, notes, joined_at
            FROM partners
            WHERE telegram_id = $1;
        """, telegram_id)
        return dict(row) if row else None


async def get_partner_stats(telegram_id: int) -> dict | None:
    """
    Возвращает статистику конкретного партнёра.
    Используется в команде /me_partner и в /partner_stats.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        partner = await conn.fetchrow("""
            SELECT telegram_id, display_name, commission_pct, joined_at
            FROM partners
            WHERE telegram_id = $1;
        """, telegram_id)
        if not partner:
            return None

        # Всего привёл клиентов
        clients_total = await conn.fetchval("""
            SELECT COUNT(*) FROM users WHERE referred_by = $1;
        """, telegram_id) or 0

        # Из них оплатили хотя бы один заказ
        clients_paid = await conn.fetchval("""
            SELECT COUNT(DISTINCT u.telegram_id)
            FROM users u
            JOIN orders o ON o.telegram_id = u.telegram_id
            WHERE u.referred_by = $1 AND o.status = 'paid';
        """, telegram_id) or 0

        # Сумма всех оплаченных заказов клиентов партнёра
        revenue_total = await conn.fetchval("""
            SELECT COALESCE(SUM(o.price), 0)
            FROM orders o
            JOIN users u ON u.telegram_id = o.telegram_id
            WHERE u.referred_by = $1 AND o.status = 'paid';
        """, telegram_id) or 0

        # За последние 30 дней
        revenue_month = await conn.fetchval("""
            SELECT COALESCE(SUM(o.price), 0)
            FROM orders o
            JOIN users u ON u.telegram_id = o.telegram_id
            WHERE u.referred_by = $1
              AND o.status = 'paid'
              AND o.paid_at >= NOW() - INTERVAL '30 days';
        """, telegram_id) or 0

        # Сколько уже выплачено партнёру
        paid_out = await conn.fetchval("""
            SELECT COALESCE(SUM(amount), 0)
            FROM partner_payouts
            WHERE partner_id = $1;
        """, telegram_id) or 0

        pct = float(partner["commission_pct"])
        earned_total = int(revenue_total * pct / 100)
        earned_month = int(revenue_month * pct / 100)
        pending = earned_total - int(paid_out)

        return {
            "telegram_id":     partner["telegram_id"],
            "display_name":    partner["display_name"],
            "commission_pct":  pct,
            "joined_at":       partner["joined_at"],
            "clients_total":   clients_total,
            "clients_paid":    clients_paid,
            "revenue_total":   int(revenue_total),
            "revenue_month":   int(revenue_month),
            "earned_total":    earned_total,
            "earned_month":    earned_month,
            "paid_out":        int(paid_out),
            "pending":         max(0, pending),
        }


async def list_partner_stats() -> list[dict]:
    """
    Возвращает статистику по всем партнёрам — для админской команды
    /partner_stats. Сортировка: pending DESC (кому больше всего должен).
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        partners = await conn.fetch("""
            SELECT telegram_id FROM partners ORDER BY joined_at ASC;
        """)
        rows = []
        for p in partners:
            stats = await get_partner_stats(p["telegram_id"])
            if stats:
                rows.append(stats)
        # Сортируем по pending убыванию
        rows.sort(key=lambda r: r["pending"], reverse=True)
        return rows


async def record_partner_payout(
    partner_id: int,
    amount: int,
    comment: str | None = None,
) -> int | None:
    """
    Записывает факт выплаты партнёру. Возвращает id записи или None
    если партнёр не найден.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM partners WHERE telegram_id = $1;", partner_id,
        )
        if not exists:
            return None
        row = await conn.fetchrow("""
            INSERT INTO partner_payouts (partner_id, amount, comment)
            VALUES ($1, $2, $3)
            RETURNING id;
        """, partner_id, amount, comment)
        return row["id"]