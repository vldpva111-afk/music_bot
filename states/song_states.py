"""
FSM состояния для диалога создания песни.
"""

from aiogram.fsm.state import State, StatesGroup


class SongCreation(StatesGroup):
    # Пользователь видит приветствие — ожидаем нажатия "Создать песню"
    start = State()

    # Ожидаем выбора жанра
    genre = State()

    # Ожидаем выбора настроения
    mood = State()

    # Ожидаем выбора голоса
    voice = State()

    # Ожидаем ввода деталей о человеке
    details = State()

    # Ожидаем правок к уже сгенерированном тексте песни
    editing = State()
