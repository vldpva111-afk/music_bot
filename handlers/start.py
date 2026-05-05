"""
Хэндлер команды /start.
Показывает приветственное сообщение и кнопку для старта.
"""

import logging
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from states import SongCreation
from keyboards import get_start_keyboard, get_genre_keyboard

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Обрабатывает команду /start — сбрасывает состояние и показывает приветствие."""
    await state.clear()

    text = (
        "🎉 Привет! Я ПоздравОК"
"Я помогу тебе создать музыкальный подарок и подарить яркие эмоции "
        "твоим родным и близким. "
"Всего за несколько минут, я сделаю для тебя уникальную песню, "
        "которой ты можешь поздравить любимого человека, удивить друга или признаться в любви девушке. "

        "Давай начнем? 🎵"
    )

    await message.answer(text, reply_markup=get_start_keyboard())
    await state.set_state(SongCreation.start)
    logger.info(f"Пользователь {message.from_user.id} запустил бота.")


@router.callback_query(SongCreation.start, lambda c: c.data == "create_song")
@router.callback_query(lambda c: c.data == "create_song")  # Также из кнопки "Создать новую песню"
async def on_create_song(callback: CallbackQuery, state: FSMContext) -> None:
    """Пользователь нажал 'Создать песню' — переходим к выбору жанра."""
    await state.clear()
    await callback.message.edit_text(
        "В каком жанре мне сделать песню? 🎼",
        reply_markup=get_genre_keyboard(),
    )
    await state.set_state(SongCreation.genre)
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} начал создание песни.")
