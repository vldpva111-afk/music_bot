"""
FSM состояния для диалога создания песни.
"""

from aiogram.fsm.state import State, StatesGroup


class SongCreation(StatesGroup):
    # Ожидаем выбора жанра
    genre = State()

    # Ожидаем выбора настроения
    mood = State()

    # Ожидаем выбора голоса
    voice = State()

    # Ожидаем ввода деталей о человеке
    details = State()

    # Ожидаем действия с готовым текстом (правки или генерация музыки)
    editing = State()
