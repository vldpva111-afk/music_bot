"""
Отправка админ-алертов в Telegram.

Используется для критических событий, о которых нужно знать оператору:
кончились кредиты у внешнего API, упала БД, и т.п.
"""

import logging
import time

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from config import settings

logger = logging.getLogger(__name__)

# Дефолтный кулдаун между алертами с одинаковым ключом — 30 минут.
# Защищает от спама, когда одна проблема генерирует десятки ошибок подряд
# (например, у Suno кончились кредиты — каждый юзер триггерит exception).
_DEFAULT_COOLDOWN = 30 * 60

# В памяти процесса: {alert_key: last_sent_unix_ts}.
# Для одного инстанса бота этого достаточно. Если будет несколько процессов —
# нужно будет переехать в Redis, но это уже другая задача.
_last_sent: dict[str, float] = {}


async def alert_admins(
    bot: Bot,
    text: str,
    *,
    key: str | None = None,
    cooldown: int = _DEFAULT_COOLDOWN,
) -> None:
    """
    Шлёт сообщение всем админам из ADMIN_IDS.

    Параметры:
        bot      — экземпляр aiogram Bot для отправки.
        text     — HTML-текст уведомления.
        key      — идентификатор типа алерта. Если задан, повторные алерты
                   с тем же ключом подавляются в течение cooldown секунд.
        cooldown — окно подавления для данного ключа, в секундах.

    Best-effort: ошибки отправки логируются, но не пробрасываются.
    """
    now = time.time()

    if key is not None:
        last = _last_sent.get(key, 0)
        if now - last < cooldown:
            remaining = int(cooldown - (now - last))
            logger.debug(
                "Alert '%s' suppressed by cooldown (next allowed in %ds)",
                key, remaining,
            )
            return
        _last_sent[key] = now

    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            logger.warning("Failed to alert admin %d: %s", admin_id, e)
        except Exception as e:
            logger.error("Unexpected error alerting admin %d: %s", admin_id, e)
