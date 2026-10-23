import asyncio
import os
import time
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BotCommand,
    MenuButtonDefault
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ──────────────────────────────────────────────
# ЛОГИРОВАНИЕ В CMD / КОНСОЛЬ ХОСТИНГА
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("SMK_BOT")

# ──────────────────────────────────────────────
# КОНФИГУРАЦИЯ (С поддержкой переменных хостинга)
# ──────────────────────────────────────────────
TOKEN = os.getenv("BOT_TOKEN", "8278881697:AAFzGGlxf2FOhkPuDY3E4oB68xsHr6B3Ykc")
ADMIN_ID = int(os.getenv("ADMIN_ID", "928510760"))

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

START_COOLDOWN_SECONDS = 2
_start_last_seen: dict[int, float] = {}
_start_guard_lock = asyncio.Lock()


class OrderStates(StatesGroup):
    waiting_for_repost_proof = State()
    admin_waiting_reject_reason = State()


# ── КЛАВИАТУРЫ ──
def build_main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎟 Входные билеты", callback_data="buy_ticket")],
        [InlineKeyboardButton(text="📄 Правила и оферта", callback_data="show_legal")],
        [InlineKeyboardButton(text="🔞 Возрастной контроль 18+", callback_data="show_rules")]
    ])


def build_ticket_selection_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Стандартный билет — 500 ₽", callback_data="ticket_single")],
        [InlineKeyboardButton(text="Билет за репост — 400 ₽", callback_data="ticket_repost")],
        [InlineKeyboardButton(text="← В главное меню", callback_data="back_to_start")]
    ])


def build_single_ticket_pay_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить 500 ₽", callback_data="pay_process_single")],
        [InlineKeyboardButton(text="← Назад к тарифам", callback_data="buy_ticket")]
    ])


def build_repost_ticket_pay_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Отправить скриншот репоста", callback_data="repost_proof")],
        [InlineKeyboardButton(text="💳 Оплатить 400 ₽", callback_data="pay_process_repost")],
        [InlineKeyboardButton(text="← Назад к тарифам", callback_data="buy_ticket")]
    ])


def build_admin_repost_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Одобрить", callback_data=f"repost_accept_start:{user_id}"),
            InlineKeyboardButton(text="Отклонить", callback_data=f"repost_reject_start:{user_id}")
        ],
        [
            InlineKeyboardButton(text="Написать гостю", url=f"tg://user?id={user_id}")
        ]
    ])


def build_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← В главное меню", callback_data="back_to_start")]
    ])


async def set_bot_commands():
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="tickets", description="Входные билеты"),
        BotCommand(command="legal", description="Правила и оферта"),
        BotCommand(command="rules", description="Возрастной контроль 18+")
    ]
    await bot.set_my_commands(commands)
    try:
        await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
    except Exception as e:
        logger.warning(f"Ошибка сброса MenuButton: {e}")


# ── ОБРАБОТКА КОМАНДЫ СТАРТ ──
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    now = time.monotonic()

    async with _start_guard_lock:
        last_seen = _start_last_seen.get(user_id, 0.0)
        if now - last_seen < START_COOLDOWN_SECONDS:
            return
        _start_last_seen[user_id] = now

    await state.clear()
    logger.info(f"Команда /start от user_id={user_id} (@{message.from_user.username})")

    caption = (
        "<b>SMK EVENT // ** NOVEMBER 2026</b>\n"
        "<i>Санкт-Петербург • 18:00 – 23:00</i>\n\n"
        "Добро пожаловать в официальный сервис бронирования билетов на закрытое "
        "культурно-развлекательное мероприятие SMK EVENT.\n\n"
        "<b>Каталог билетов и услуг:</b>\n"
        "🟢 Стандартный билет на мероприятие — 500 ₽\n"
        "🟢 Билет со скидкой за репост анонса — 400 ₽\n\n"
        "• <b>Возрастной ценз:</b> строго 18+ (вход исключительно по оригиналу паспорта или прав)\n"
        "• <b>Формат доступа:</b> предварительная регистрация / Face Control\n\n"
        "Для выбора тарифа и оформления заказа воспользуйтесь меню ниже:"
    )

    await message.answer(text=caption, parse_mode="HTML", reply_markup=build_main_menu_keyboard())


@dp.message(Command("tickets"))
async def cmd_tickets(message: types.Message):
    await show_tickets_menu(message)


@dp.message(Command("legal"))
async def cmd_legal(message: types.Message):
    await send_legal_info(message)


@dp.message(Command("rules"))
async def cmd_rules(message: types.Message):
    await send_rules_info(message)


# ── КАТАЛОГ БИЛЕТОВ (ТРЕБОВАНИЕ ЮКАССЫ) ──
async def show_tickets_menu(target: types.Message | types.CallbackQuery):
    text = (
        "<b>ВХОДНЫЕ БИЛЕТЫ // ВЫБОР ТАРИФА:</b>\n\n"
        "• <b>Стандартный билет — 500 ₽</b>\n"
        "Входной билет на 1 гостя. Доступ ко всем площадкам мероприятия, интерактивной программе и свободному фуршету.\n\n"
        "• <b>Билет за репост — 400 ₽</b>\n"
        "Льготный тариф. Доступ на мероприятие со скидкой при подтверждении публикации анонса в своих социальных сетях.\n\n"
        "Выберите интересующий билет для перехода к оформлению заказа:"
    )
    if isinstance(target, types.CallbackQuery):
        try:
            await target.message.edit_text(text, parse_mode="HTML", reply_markup=build_ticket_selection_keyboard())
        except Exception:
            await target.message.answer(text, parse_mode="HTML", reply_markup=build_ticket_selection_keyboard())
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=build_ticket_selection_keyboard())


@dp.callback_query(lambda c: c.data == "buy_ticket")
async def process_buy_ticket(callback: types.CallbackQuery):
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} открыл тарифы")
    await show_tickets_menu(callback)


# ── СТАНДАРТНЫЙ БИЛЕТ ──
@dp.callback_query(lambda c: c.data == "ticket_single")
async def process_ticket_single(callback: types.CallbackQuery):
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} открыл оформление Стандартного билета")
    text = (
        "🎟 <b>Стандартный билет на SMK EVENT</b>\n\n"
        "<b>Стоимость:</b> 500 ₽\n"
        "<b>Мероприятие:</b> SMK EVENT // ** NOVEMBER 2026\n"
        "<b>Время:</b> 18:00 – 23:00\n\n"
        "<b>Что входит в билет:</b>\n"
        "✓ Входной доступ на 1 персону\n"
        "✓ Полная развлекательная программа и живые выступления\n"
        "✓ Персональный электронный посадочный талон с QR-кодом\n\n"
        "Нажмите кнопку ниже для подтверждения и оплаты заказа:"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=build_single_ticket_pay_keyboard())


# ── БИЛЕТ ЗА РЕПОСТ ──
@dp.callback_query(lambda c: c.data == "ticket_repost")
async def process_ticket_repost(callback: types.CallbackQuery):
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} открыл оформление Билета за репост")
    text = (
        "🎟 <b>Билет за репост на SMK EVENT</b>\n\n"
        "<b>Стоимость:</b> 400 ₽ <i>(скидка 100 ₽)</i>\n"
        "<b>Мероприятие:</b> SMK EVENT // ** NOVEMBER 2026\n"
        "<b>Время:</b> 18:00 – 23:00\n\n"
        "<b>Условия предоставления скидки:</b>\n"
        "1. Сделайте репост анонса в свой Telegram-канал или историю.\n"
        "2. Отправьте скриншот публикации на проверку организаторам.\n\n"
        "Нажмите кнопку ниже для отправки скриншота или перехода к оплате:"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=build_repost_ticket_pay_keyboard())


# ── ВСПЛЫВАЮЩЕЕ ОКНО НАСТРОЙКИ ПЛАТЕЖЕЙ (ALERT) ──
@dp.callback_query(lambda c: c.data in ["pay_process_single", "pay_process_repost"])
async def process_payment_alert(callback: types.CallbackQuery):
    logger.info(f"Пользователь {callback.from_user.id} нажал кнопку оплаты ({callback.data})")
    alert_text = (
        "⚠️ Мы ещё настраиваем приём онлайн-платежей через ЮKassa.\n\n"
        "Платёжный шлюз проходит финальное подключение. Приём оплаты станет доступен сразу после завершения модерации."
    )
    await callback.answer(text=alert_text, show_alert=True)


# ── СИСТЕМА ПРОВЕРКИ РЕПОСТОВ ──
@dp.callback_query(lambda c: c.data == "repost_proof")
async def request_repost_proof(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(OrderStates.waiting_for_repost_proof)
    logger.info(f"Пользователь {callback.from_user.id} переведён в режим отправки скриншота")
    await callback.message.edit_text(
        "Отправьте скриншот публикации ответным сообщением (в описании можно прикрепить ссылку на ваш канал или профиль):"
    )


@dp.message(StateFilter(OrderStates.waiting_for_repost_proof), F.photo | F.document)
async def handle_repost_proof(message: types.Message, state: FSMContext):
    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    is_doc = message.document is not None

    logger.info(f"Получен скриншот репоста от user_id={message.from_user.id}")

    caption = (
        "<b>ПРОВЕРКА РЕПОСТА</b>\n\n"
        f"От: {message.from_user.full_name}\n"
        f"ID: <code>{message.from_user.id}</code>\n"
        f"Username: @{message.from_user.username or 'отсутствует'}\n"
        f"Комментарий: {message.caption or '—'}"
    )
    markup = build_admin_repost_keyboard(message.from_user.id)

    try:
        if is_doc:
            await bot.send_document(ADMIN_ID, file_id, caption=caption, parse_mode="HTML", reply_markup=markup)
        else:
            await bot.send_photo(ADMIN_ID, file_id, caption=caption, parse_mode="HTML", reply_markup=markup)
        logger.info(f"Заявка на репост от {message.from_user.id} передана администратору {ADMIN_ID}")
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление администратору: {e}")

    await message.answer(
        "✓ Скриншот принят на модерацию. Ожидайте подтверждения от администратора.",
        reply_markup=build_back_keyboard()
    )
    await state.clear()


@dp.callback_query(lambda c: c.data and c.data.startswith("repost_accept_start:"))
async def admin_repost_accept(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    user_id = int(callback.data.split(":")[1])
    logger.info(f"Администратор ОДОБРИЛ репост для user_id={user_id}")

    text = (
        "✓ <b>Репост подтверждён администратором!</b>\n\n"
        "За вами закреплена скидка: <b>Билет за репост (400 ₽)</b>.\n"
        "Оплата билета через ЮKassa станет доступна сразу после завершения настройки платёжного шлюза."
    )
    try:
        await bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка отправки пользователю {user_id}: {e}")

    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n<b>✓ ОДОБРЕНО АДМИНИСТРАТОРОМ</b>",
        parse_mode="HTML",
        reply_markup=None
    )
    await callback.answer("Репост одобрен")


@dp.callback_query(lambda c: c.data and c.data.startswith("repost_reject_start:"))
async def admin_repost_reject(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    user_id = int(callback.data.split(":")[1])
    logger.info(f"Администратор начал отклонение репоста для user_id={user_id}")

    await state.set_state(OrderStates.admin_waiting_reject_reason)
    await state.update_data(reject_user_id=user_id)
    await callback.message.answer("Укажите причину отклонения заявки текстом:")
    await callback.answer()


@dp.message(StateFilter(OrderStates.admin_waiting_reject_reason))
async def admin_reject_reason_input(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await state.clear()
        return

    data = await state.get_data()
    user_id = data.get("reject_user_id")
    reason = (message.text or "Публикация не найдена или не соответствует условиям акции").strip()

    logger.info(f"Администратор ОТКЛОНИЛ репост для user_id={user_id}. Причина: {reason}")

    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"❌ Заявка на льготный тариф отклонена.\nПричина: {reason}\n\nВы можете оформить стандартный билет или отправить скриншот повторно."
        )
        await message.answer("Уведомление об отказе отправлено пользователю.")
    except Exception as e:
        await message.answer(f"Не удалось доставить сообщение: {e}")

    await state.clear()


# ── ВОЗРАСТНОЙ КОНТРОЛЬ 18+ ──
async def send_rules_info(target: types.Message | types.CallbackQuery):
    text = (
        "<b>ВОЗРАСТНОЙ КОНТРОЛЬ И ПРАВИЛА ВХОДА:</b>\n\n"
        "🔞 <b>Возрастной ценз строго 18+:</b>\n"
        "Вход на мероприятие осуществляется исключительно при предъявлении оригинала документа, "
        "удостоверяющего личность (паспорт гражданина РФ или водительское удостоверение).\n\n"
        "⚠️ <b>Внимание:</b> фотографии документов с экрана смартфона, копии и студенческие билеты "
        "службой безопасности не принимаются.\n\n"
        "🛡 <b>Face Control:</b>\n"
        "Служба контроля оставляет за собой право отказать во входе лицам в состоянии сильного "
        "алкогольного или токсического опьянения, а также при проявлении агрессивного поведения."
    )
    if isinstance(target, types.CallbackQuery):
        try:
            await target.message.edit_text(text, parse_mode="HTML", reply_markup=build_back_keyboard())
        except Exception:
            await target.message.answer(text, parse_mode="HTML", reply_markup=build_back_keyboard())
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=build_back_keyboard())


@dp.callback_query(lambda c: c.data == "show_rules")
async def cb_show_rules(callback: types.CallbackQuery):
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} запросил правила 18+")
    await send_rules_info(callback)


# ── ПРАВИЛА И ОФЕРТА ──
async def send_legal_info(target: types.Message | types.CallbackQuery):
    text = (
        "<b>ПОЛЬЗОВАТЕЛЬСКОЕ СОГЛАШЕНИЕ И УСЛОВИЯ ОФЕРТЫ:</b>\n\n"
        "1. Настоящее мероприятие SMK EVENT является закрытым частным культурно-развлекательным событием. "
        "Участие осуществляется на основании предварительной регистрации и приобретения входного билета.\n\n"
        "2. Входной взнос обеспечивает покрытие расходов по бронированию площадки, организации звукового "
        "сопровождения и шоу-программы.\n\n"
        "3. <b>Условия возврата билетов:</b>\n"
        "Возврат денежных средств за приобретённые билеты осуществляется <b>исключительно в случае полной отмены "
        "мероприятия по инициативе организаторов</b>.\n"
        "В случае отказа гостю в допуске на площадку по причине отсутствия оригинала документа (18+), "
        "нахождения в состоянии сильного алкогольного опьянения или нарушения правил поведения средства "
        "возврату не подлежат в связи с фактическим бронированием места.\n\n"
        "4. <b>Персональные данные:</b>\n"
        "Сбор и обработка информации (ФИО, Telegram ID) осуществляется исключительно в рамках исполнения "
        "настоящего соглашения в соответствии с Федеральным законом № 152-ФЗ."
    )
    if isinstance(target, types.CallbackQuery):
        try:
            await target.message.edit_text(text, parse_mode="HTML", reply_markup=build_back_keyboard())
        except Exception:
            await target.message.answer(text, parse_mode="HTML", reply_markup=build_back_keyboard())
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=build_back_keyboard())


@dp.callback_query(lambda c: c.data == "show_legal")
async def cb_show_legal(callback: types.CallbackQuery):
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} запросил правила и оферту")
    await send_legal_info(callback)


# ── НАВИГАЦИЯ НАЗАД ──
@dp.callback_query(lambda c: c.data == "back_to_start")
async def back_to_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    logger.info(f"Пользователь {callback.from_user.id} вернулся в главное меню")

    caption = (
        "<b>SMK EVENT // ** NOVEMBER 2026</b>\n"
        "<i>Санкт-Петербург • 18:00 – 23:00</i>\n\n"
        "Главное меню. Выберите интересующий раздел:"
    )
    try:
        await callback.message.edit_text(caption, parse_mode="HTML", reply_markup=build_main_menu_keyboard())
    except Exception:
        await callback.message.answer(caption, parse_mode="HTML", reply_markup=build_main_menu_keyboard())


# ── ЗАПУСК ──
async def main():
    await set_bot_commands()
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Очередь старых сообщений сброшена.")
    logger.info("Бот SMK EVENT запущен на BotHost.")
    try:
        await dp.start_polling(bot, drop_pending_updates=True)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")