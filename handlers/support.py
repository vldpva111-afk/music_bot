"""
Двусторонняя поддержка через бота:

1. Команда /dm <user_id> <текст> — админ инициирует диалог с клиентом.
2. Любой текст от клиента ВНЕ активного FSM-состояния пересылается админам
   с маркером ID клиента.
3. Когда админ делает reply на пересланное сообщение — бот отправляет ответ
   обратно клиенту от своего имени.

Регистрировать ПОСЛЕДНИМ — иначе catch-all перехватит сообщения, которые
должны идти в основной флоу.
"""

import logging
import re

from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from config import settings

logger = logging.getLogger(__name__)
router = Router()


# Маркер, по которому при reply админа определяем, какому юзеру отправить ответ.
# Кладём в конец каждого пересланного сообщения. Регулярка ищет `#user_123456`.
_USER_TAG_RE = re.compile(r"#user_(\d+)")


def _format_forward_header(msg: Message) -> str:
    user = msg.from_user
    name = (user.full_name or "").strip() or "—"
    username = f"@{user.username}" if user.username else "без username"
    return (
        f"📩 <b>Сообщение от пользователя</b>\n"
        f"👤 <a href=\"tg://user?id={user.id}\">{name}</a> ({username})\n"
        f"🆔 <code>{user.id}</code>\n\n"
    )


# ── /dm <user_id> <текст> ─────────────────────────────────────────────────────

@router.message(Command("dm"))
async def cmd_dm(message: Message) -> None:
    """Админ-команда: /dm 123456 Здравствуйте! ..."""
    if message.from_user.id not in settings.ADMIN_IDS:
        return  # молча игнорируем для не-админов

    # Парсим: первый токен после /dm — user_id, остальное — текст
    args = (message.text or "").split(maxsplit=2)
    if len(args) < 3 or not args[1].isdigit():
        await message.answer(
            "Использование:\n<code>/dm USER_ID текст сообщения</code>\n\n"
            "Пример:\n<code>/dm 1831201161 Здравствуйте! Напишите в @pozdravok_support</code>",
            parse_mode="HTML",
        )
        return

    target_id = int(args[1])
    text = args[2]

    try:
        await message.bot.send_message(target_id, text)
        await message.answer(
            f"✅ Отправлено пользователю <code>{target_id}</code>",
            parse_mode="HTML",
        )
        logger.info("Admin %d sent DM to user %d", message.from_user.id, target_id)
    except TelegramForbiddenError:
        await message.answer(
            f"❌ Пользователь <code>{target_id}</code> заблокировал бота.",
            parse_mode="HTML",
        )
    except TelegramBadRequest as e:
        await message.answer(
            f"❌ Ошибка Telegram: <code>{e.message}</code>\n"
            f"Возможно, юзер никогда не нажимал /start.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception("Failed to send DM to %d", target_id)
        await message.answer(f"❌ Ошибка: {type(e).__name__}: {e}")


# ── Reply админа в личке бота → ответ клиенту ────────────────────────────────

@router.message(
    F.chat.type == "private",
    F.reply_to_message,
    F.text,
    StateFilter(None),
)
async def admin_reply_to_user(message: Message) -> None:
    """Если админ делает reply на пересланное от юзера сообщение — шлём клиенту."""
    if message.from_user.id not in settings.ADMIN_IDS:
        return  # пусть идёт дальше по цепочке (вернём, не обработав)

    # Ищем маркер #user_XXX в reply-источнике
    src = message.reply_to_message
    candidate_text = (src.text or src.caption or "")
    match = _USER_TAG_RE.search(candidate_text)
    if not match:
        return  # это не наш forward — пропускаем

    target_id = int(match.group(1))
    try:
        await message.bot.send_message(target_id, message.text)
        await message.reply(
            f"✅ Отправлено пользователю <code>{target_id}</code>",
            parse_mode="HTML",
        )
        logger.info(
            "Admin %d replied to user %d via forward",
            message.from_user.id, target_id,
        )
    except TelegramForbiddenError:
        await message.reply("❌ Пользователь заблокировал бота.")
    except Exception as e:
        logger.exception("Failed to forward admin reply to %d", target_id)
        await message.reply(f"❌ Ошибка: {type(e).__name__}: {e}")


# ── Catch-all: текст от юзера вне FSM → пересылаем админам ────────────────────

@router.message(
    F.chat.type == "private",
    F.text,
    StateFilter(None),
)
async def forward_user_text_to_admins(message: Message, state: FSMContext) -> None:
    """
    Любой текст от юзера, который НЕ попал в другие хэндлеры и у которого
    нет активного состояния FSM, пересылаем админам.

    Не пересылаем:
    - команды (/start и т.п.) — их ловят свои хэндлеры выше
    - сообщения от самих админов
    """
    if message.from_user.id in settings.ADMIN_IDS:
        return  # админ пишет сам себе — игнорируем
    if (message.text or "").startswith("/"):
        return  # команда без хэндлера — пусть просто игнорируется

    header = _format_forward_header(message)
    body = message.text
    # Маркер ставим в самом конце — не бросается в глаза, но парсится reply'ем
    tag = f"\n\n#user_{message.from_user.id}"

    forwarded_to_any = False
    for admin_id in settings.ADMIN_IDS:
        try:
            await message.bot.send_message(
                admin_id,
                header + body + tag,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            forwarded_to_any = True
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            logger.warning("Failed to forward user message to admin %d: %s", admin_id, e)
        except Exception:
            logger.exception("Unexpected error forwarding to admin %d", admin_id)

    if forwarded_to_any:
        await message.answer(
            "✉️ Спасибо! Мы получили твоё сообщение и ответим в ближайшее время.\n\n"
            "Если вопрос срочный — напиши в @pozdravok_support."
        )
    else:
        # Все админы недоступны — даём прямой контакт
        await message.answer(
            "Извини, поддержка временно недоступна.\n"
            "Напиши, пожалуйста, в @pozdravok_support — там быстро ответят."
        )
