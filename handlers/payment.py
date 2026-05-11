"""
Хэндлер покупки кредитов через Kaspi (ручная обработка).

Флоу:
  1. Юзер жмёт «💎 Купить кредиты» → показываем тарифы.
  2. Жмёт пакет → бот просит номер телефона (контактом или текстом).
  3. Юзер отправляет → бот создаёт заказ в БД, алертит админа с готовой
     командой /grant. Юзеру говорит «жди счёт».
  4. Админ выставляет счёт в Kaspi, ждёт оплату.
  5. Админ запускает /grant — кредиты начислены, заказ закрыт автоматически.
"""

import logging
import re

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext

from states import Payment
from keyboards import (
    get_packages_keyboard,
    get_phone_request_keyboard,
    get_main_menu_keyboard,
)
from constants import PACKAGES, VALID_PACKAGES
from database import create_order, log_event, Events
from services.admin_alerts import alert_admins
from config import settings

logger = logging.getLogger(__name__)
router = Router()


# ── Экран выбора тарифа ───────────────────────────────────────────────────────

BUY_INTRO = (
    "💎 <b>Купить кредиты</b>\n\n"
    "1 кредит = 1 готовая песня (текст + музыка).\n"
    "Кредиты не сгорают — используй когда захочешь.\n\n"
    "<b>Выбери пакет:</b>"
)


@router.callback_query(lambda c: c.data == "buy_credits")
async def on_buy_clicked(callback: CallbackQuery, state: FSMContext) -> None:
    """Точка входа в покупку через кнопку меню."""
    await state.clear()
    await log_event(callback.from_user.id, Events.BUY_CLICKED)

    await callback.message.answer(
        BUY_INTRO,
        parse_mode="HTML",
        reply_markup=get_packages_keyboard(),
    )
    await callback.answer()


@router.message(Command("offer"))
async def cmd_offer(message: Message) -> None:
    """Команда /offer — показывает ссылку на договор оферты."""
    if not settings.OFFER_URL:
        await message.answer(
            "Договор оферты пока не опубликован. Уточни у поддержки.",
        )
        return
    await message.answer(
        f"📄 <b>Договор публичной оферты</b>\n\n"
        f"Условия использования сервиса и обработки данных:\n"
        f"{settings.OFFER_URL}",
        parse_mode="HTML",
        disable_web_page_preview=False,
    )


@router.message(Command("buy"))
async def cmd_buy(message: Message, state: FSMContext) -> None:
    """Точка входа в покупку через команду /buy."""
    await state.clear()
    await log_event(message.from_user.id, Events.BUY_CLICKED)

    await message.answer(
        BUY_INTRO,
        parse_mode="HTML",
        reply_markup=get_packages_keyboard(),
    )


@router.callback_query(lambda c: c.data == "back_to_menu")
async def on_back_to_menu(callback: CallbackQuery, state: FSMContext) -> None:
    """Возврат в главное меню с экрана тарифов."""
    await state.clear()
    await callback.message.answer(
        "🏠 Главное меню",
        reply_markup=get_main_menu_keyboard(),
    )
    await callback.answer()


# ── Выбор конкретного пакета → запрос телефона ────────────────────────────────

@router.callback_query(lambda c: c.data in VALID_PACKAGES)
async def on_package_selected(callback: CallbackQuery, state: FSMContext) -> None:
    pkg_key = callback.data
    pkg = PACKAGES[pkg_key]

    # Сохраняем выбранный пакет в FSM
    await state.update_data(package_key=pkg_key)
    await state.set_state(Payment.awaiting_phone)
    await log_event(
        callback.from_user.id,
        Events.PACKAGE_SELECTED,
        {"package": pkg_key, "price": pkg["price"]},
    )

    # Блок про оферту — показываем только если ссылка задана в конфиге.
    # Так юзер видит, на что он соглашается, отправляя номер телефона.
    offer_block = ""
    if settings.OFFER_URL:
        offer_block = (
            f"\n\n<i>Отправляя номер, ты принимаешь "
            f"<a href=\"{settings.OFFER_URL}\">условия оферты</a> "
            f"и соглашаешься на обработку персональных данных.</i>"
        )

    await callback.message.answer(
        f"🛒 <b>Заказ:</b> {pkg['label']} — <b>{pkg['price']} ₸</b>\n\n"
        f"📱 Чтобы выставить счёт в Kaspi, мне нужен твой <b>номер телефона</b>.\n\n"
        f"Нажми кнопку <b>«Отправить мой номер»</b> или напиши номер вручную "
        f"(в формате <code>+7 777 123 45 67</code>)."
        f"{offer_block}",
        parse_mode="HTML",
        reply_markup=get_phone_request_keyboard(),
        disable_web_page_preview=True,
    )
    await callback.answer()


# ── Приём телефона: контактом ─────────────────────────────────────────────────

@router.message(Payment.awaiting_phone, F.contact)
async def on_phone_via_contact(message: Message, state: FSMContext) -> None:
    """Юзер прислал свой контакт через системную кнопку."""
    contact = message.contact

    # Безопасность: убеждаемся что юзер прислал СВОЙ номер, а не чей-то контакт
    if contact.user_id and contact.user_id != message.from_user.id:
        await message.answer(
            "⚠️ Пожалуйста, отправь именно <b>свой</b> номер.",
            parse_mode="HTML",
            reply_markup=get_phone_request_keyboard(),
        )
        return

    await _finalize_order(message, state, contact.phone_number)


# ── Приём телефона: текстом ───────────────────────────────────────────────────

# Грубая проверка: 10–15 цифр (с учётом '+' и пробелов уже выкинутых)
_PHONE_RE = re.compile(r"^\+?\d{10,15}$")


@router.message(Payment.awaiting_phone, F.text == "❌ Отменить заказ")
async def on_cancel_order(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "❌ Заказ отменён.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer("🏠 Главное меню", reply_markup=get_main_menu_keyboard())


@router.message(Payment.awaiting_phone, F.text)
async def on_phone_via_text(message: Message, state: FSMContext) -> None:
    """Юзер написал номер руками. Нормализуем и валидируем."""
    raw = (message.text or "").strip()
    # Убираем всё кроме цифр и плюса
    cleaned = re.sub(r"[^\d+]", "", raw)

    if not _PHONE_RE.match(cleaned):
        await message.answer(
            "🤔 Это не похоже на номер. Пришли в формате "
            "<code>+7 777 123 45 67</code> или нажми кнопку ниже.",
            parse_mode="HTML",
            reply_markup=get_phone_request_keyboard(),
        )
        return

    await _finalize_order(message, state, cleaned)


# Фоллбэк для не-текстовых не-контактных сообщений в этом состоянии
@router.message(Payment.awaiting_phone)
async def on_phone_wrong_type(message: Message) -> None:
    await message.answer(
        "📱 Пожалуйста, отправь номер кнопкой или текстом — "
        "стикеры/фото в этом шаге не работают.",
        reply_markup=get_phone_request_keyboard(),
    )


# ── Финализация заказа ────────────────────────────────────────────────────────

async def _finalize_order(
    message: Message,
    state: FSMContext,
    phone: str,
) -> None:
    """Создаём заказ в БД, алертим админа, отвечаем юзеру."""
    data = await state.get_data()
    pkg_key: str = data.get("package_key", "")
    pkg = PACKAGES.get(pkg_key)

    if not pkg:
        # Защита от рассинхронизации: юзер каким-то образом попал сюда без пакета
        await state.clear()
        await message.answer(
            "⚠️ Что-то пошло не так. Попробуй заказать заново через /menu",
            reply_markup=ReplyKeyboardRemove(),
        )
        logger.warning(
            "Юзер %d дошёл до _finalize_order без package_key.",
            message.from_user.id,
        )
        return

    user = message.from_user
    # Нормализуем телефон: всегда с '+'
    normalized_phone = phone if phone.startswith("+") else f"+{phone}"

    order_id = await create_order(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        package_key=pkg_key,
        credits=pkg["credits"],
        price=pkg["price"],
        phone=normalized_phone,
    )

    await log_event(
        user.id,
        Events.PHONE_SUBMITTED,
        {"order_id": order_id, "package": pkg_key},
    )

    await state.clear()

    # Подтверждение юзеру
    await message.answer(
        f"✅ <b>Заказ #{order_id} принят</b>\n\n"
        f"📦 Пакет: <b>{pkg['label']}</b>\n"
        f"💰 Сумма: <b>{pkg['price']} ₸</b>\n"
        f"📱 Номер: <code>{normalized_phone}</code>\n\n"
        f"⏳ В ближайшее время на этот номер придёт <b>счёт в Kaspi</b>.\n"
        f"После оплаты кредиты <b>автоматически зачислятся</b> на твой баланс — "
        f"я пришлю уведомление 🎵",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer("🏠 Главное меню", reply_markup=get_main_menu_keyboard())

    # Алерт админу — с готовой к копированию командой /grant
    username_str = f"@{user.username}" if user.username else "<i>без username</i>"
    name_str = user.first_name or "—"
    await alert_admins(
        message.bot,
        (
            f"💰 <b>Новый заказ #{order_id}</b>\n\n"
            f"<b>Юзер:</b> {username_str} (<code>{user.id}</code>)\n"
            f"<b>Имя:</b> {name_str}\n"
            f"<b>Пакет:</b> {pkg['label']} — <b>{pkg['price']} ₸</b>\n"
            f"<b>Телефон:</b> <code>{normalized_phone}</code>\n\n"
            f"👉 <b>Действия:</b>\n"
            f"1. Выставь счёт на этот номер в Kaspi.\n"
            f"2. После оплаты — выполни:\n"
            f"<code>/grant {user.id} {pkg['credits']}</code>"
        ),
        # Без cooldown: каждый заказ важен и должен прийти отдельно
        key=None,
    )

    logger.info(
        "Заказ #%d создан: user=%d, pkg=%s, phone=%s",
        order_id, user.id, pkg_key, normalized_phone,
    )
