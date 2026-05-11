"""
FSM состояния для оплаты через Kaspi (ручная обработка администратором).
"""

from aiogram.fsm.state import State, StatesGroup


class Payment(StatesGroup):
    # Юзер выбрал пакет, бот ждёт номер телефона для счёта.
    awaiting_phone = State()
