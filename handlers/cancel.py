"""
Хэндлеры /cancel и /help — доступны в любом состоянии FSM.
"""

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

logger = logging.getLogger(__name__)
router = Router()

HELP_TEXT = (
    "🎵 <b>ПоздравОК — помощь</b>\n\n"
    "Я создаю персональные песни в подарок.\n\n"
    "<b>Команды:</b>\n"
    "/start — начать создание новой песни\n"
    "/cancel — отменить текущее действие\n"
    "/help — это сообщение\n\n"
    "<b>Как это работает:</b>\n"
    "1️⃣ Выбери жанр и настроение\n"
    "2️⃣ Расскажи о человеке\n"
    "3️⃣ Получи готовый текст и музыку 🎧\n\n"
    f"<i>Если что-то пошло не так — нажми /cancel и начни заново.</i>"
)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="HTML")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()

    if current_state is None:
        await message.answer(
            "Нечего отменять. Нажми /start чтобы создать песню 🎵"
        )
        return

    await state.clear()
    logger.info("Пользователь %d отменил сессию (состояние: %s).", message.from_user.id, current_state)

    await message.answer(
        "✅ Действие отменено.\n\n"
        "Нажми /start чтобы начать заново 🎵"
    )
