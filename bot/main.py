import asyncio
import logging
from typing import Callable, Union
import json
import datetime

from loguru import logger
from telegram import Update, ReplyKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
# Добавим ParseMode для HTML-разметки
from telegram.constants import ParseMode

from bot.config import get_settings
from bot.repository import FlatRepository
from bot.services import MonitorService
from bot.models import Flat

logging.basicConfig(level=logging.INFO)


# --------------------------- command handlers --------------------------


aSYNC_DEF = Callable[[Update, ContextTypes.DEFAULT_TYPE], None]


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["Студии 🏠", "1-к. 🚪"],
        ["Статистика 📊", "Обновить сейчас 🔄"],
        ["Mock 🛠"],  # dev-кнопка
    ]
    await update.message.reply_text(
        "Привет! Я слежу за ценами в ЖК «Яуза Парк». Выберите команду:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        parse_mode=ParseMode.HTML,
    )


async def cmd_studios(update: Update, context: ContextTypes.DEFAULT_TYPE):
    repo: FlatRepository = context.application.bot_data["repo"]
    flats = await repo.select_cheapest(["0", "studio"], limit=10)
    if not flats:
        await update.message.reply_text("Нет данных. Попробуйте позже.")
        return
    lines: list[str] = []
    for idx, flat in enumerate(flats):
        line = (
            f"#{idx + 1}: {flat.price / 1_000_000:.2f} млн · этаж {flat.floor} · {flat.url}"
        )
        # Статусы отличные от 'free' считаем забронированными и зачёркиваем строку
        if flat.status != "free":
            line = f"<s>{line}</s>"
        lines.append(line)

    await update.message.reply_text(
        "Самые дешёвые студии:\n" + "\n".join(lines), parse_mode=ParseMode.HTML
    )


async def cmd_one(update: Update, context: ContextTypes.DEFAULT_TYPE):
    repo: FlatRepository = context.application.bot_data["repo"]
    flats = await repo.select_cheapest(["1"], limit=10)
    if not flats:
        await update.message.reply_text("Нет данных. Попробуйте позже.")
        return
    lines: list[str] = []
    for idx, flat in enumerate(flats):
        line = (
            f"#{idx + 1}: {flat.price / 1_000_000:.2f} млн · этаж {flat.floor} · {flat.url}"
        )
        if flat.status != "free":
            line = f"<s>{line}</s>"
        lines.append(line)

    await update.message.reply_text(
        "Самые дешёвые 1-к.:\n" + "\n".join(lines), parse_mode=ParseMode.HTML
    )


async def cmd_mockupdate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет замоканное сообщение-обновление из JSON-файла."""
    MOCK_FILE_PATH = "mock_data.json"
    try:
        with open(MOCK_FILE_PATH, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except FileNotFoundError:
        await update.message.reply_text(
            f"Не удалось найти файл {MOCK_FILE_PATH}. Положите mock JSON рядом с ботом."
        )
        return
    except json.JSONDecodeError:
        await update.message.reply_text(
            f"Файл {MOCK_FILE_PATH} содержит некорректный JSON."
        )
        return

    # raw_data должен быть списком квартир как из API
    if not isinstance(raw_data, list):
        await update.message.reply_text(
            "Ожидался JSON-массив с объектами квартир, как в ответе v1/flat."
        )
        return

    flats: list[Flat] = []
    for item in raw_data:
        if not isinstance(item, dict):
            continue
        # Используем ту же маппинг-логику, что и в PIKApiClient
        flats.append(
            Flat(
                id=item.get("id"),
                rooms=str(item.get("rooms")),
                price=item.get("price", 0),
                status=item.get("status", "unknown"),
                url=item.get("url", ""),
                area=item.get("area"),
                floor=item.get("floor"),
                # дополнительные поля
                location=item.get("location"),
                type_id=item.get("type_id"),
                guid=item.get("guid"),
                bulk_id=item.get("bulk_id"),
                section_id=item.get("section_id"),
                sale_scheme_id=item.get("saleSchemeId"),
                ceiling_height=item.get("ceilingHeight"),
                is_pre_sale=item.get("isPreSale"),
                rooms_fact=item.get("rooms_fact"),
                number=item.get("number"),
                number_bti=item.get("number_bti"),
                number_stage=item.get("number_stage"),
                min_month_fee=item.get("minMonthFee"),
                discount=item.get("discount"),
                has_advertising_price=item.get("has_advertising_price"),
                has_new_price=item.get("hasNewPrice"),
                area_bti=item.get("area_bti"),
                area_project=item.get("area_project"),
                callback=item.get("callback"),
                kitchen_furniture=item.get("kitchenFurniture"),
                booking_cost=item.get("bookingCost"),
                compass_angle=item.get("compass_angle"),
                booking_status=item.get("bookingStatus"),
                pdf=item.get("pdf"),
                is_resell=item.get("isResell"),
            )
        )

    monitor: MonitorService = context.application.bot_data["monitor"]
    summary = await monitor.update_from_list(flats)
    await _send_long_text(context.bot, update.effective_chat.id, summary)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    repo: FlatRepository = context.application.bot_data["repo"]  # только чтобы TypeChecker не ругался
    monitor: MonitorService = context.application.bot_data["monitor"]

    stats = await monitor.stats_text(include_links=True)
    
    # Добавляем время следующего обновления
    next_update_time = _get_next_update_time(context)
    stats += f"\n\n⏰ Следующее автообновление: {next_update_time}"
    
    await _send_long_text(context.bot, update.effective_chat.id, stats)


# --------------------------- jobs --------------------------------------


TELEGRAM_LIMIT = 4096

async def _send_long_text(bot, chat_id: Union[str, int], text: str) -> None:
    """Отправить длинный текст несколькими сообщениями, если превышает лимит Telegram."""
    if len(text) <= TELEGRAM_LIMIT:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
        return

    chunk: list[str] = []
    current_len = 0
    for line in text.split("\n"):
        # +1 учитывает символ новой строки при склейке
        if current_len + len(line) + 1 > TELEGRAM_LIMIT:
            await bot.send_message(chat_id=chat_id, text="\n".join(chunk), parse_mode=ParseMode.HTML)
            chunk = [line]
            current_len = len(line) + 1
        else:
            chunk.append(line)
            current_len += len(line) + 1

    if chunk:
        await bot.send_message(chat_id=chat_id, text="\n".join(chunk), parse_mode=ParseMode.HTML)


def _get_next_update_time(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Получить время следующего автообновления."""
    settings = get_settings()
    current_jobs = context.job_queue.get_jobs_by_name("hourly_update")
    
    if current_jobs:
        next_run = current_jobs[0].next_t
        if next_run:
            # Конвертируем в московское время (UTC+3)
            moscow_time = next_run + datetime.timedelta(hours=3)
            return moscow_time.strftime("%H:%M")
    
    return "неизвестно"


async def cmd_update_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ручное обновление данных с отменой и пересозданием автообновления."""
    monitor: MonitorService = context.application.bot_data["monitor"]
    settings = get_settings()
    
    # Отменяем текущие задачи автообновления
    current_jobs = context.job_queue.get_jobs_by_name("hourly_update")
    for job in current_jobs:
        job.schedule_removal()
    
    # Выполняем обновление
    summary = await monitor.update_from_api()
    
    # Создаём новую задачу автообновления
    context.job_queue.run_repeating(
        hourly_job,
        interval=settings.summary_interval_seconds,
        first=settings.summary_interval_seconds,
        data={"monitor": monitor},
        name="hourly_update"
    )
    
    # Добавляем время следующего обновления
    next_update_time = _get_next_update_time(context)
    summary += f"\n\n🔄 <b>Ручное обновление выполнено</b>\n⏰ Следующее автообновление: {next_update_time}"
    
    await _send_long_text(context.bot, update.effective_chat.id, summary)


async def hourly_job(context: ContextTypes.DEFAULT_TYPE):
    monitor: MonitorService = context.job.data["monitor"]
    settings = get_settings()
    summary = await monitor.update_from_api()
    
    # Добавляем время следующего обновления
    next_update_time = _get_next_update_time(context)
    summary += f"\n\n⏰ Следующее автообновление: {next_update_time}"
    
    await _send_long_text(context.bot, settings.telegram_chat_id, summary)


# --------------------------- main --------------------------------------


def main() -> None:
    # Создаём и устанавливаем event loop заранее, чтобы ApplicationBuilder мог его получить
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    settings = get_settings()

    # Инициализируем БД в этом же loop
    repo = FlatRepository()
    loop.run_until_complete(repo.init_db())

    monitor = MonitorService(repo)

    app = Application.builder().token(settings.telegram_token).build()

    # задаём список доступных команд с описанием и эмодзи
    commands = [
        BotCommand("start", "ℹ️ помощь"),
        BotCommand("studios", "🏠 10 дешёвых студий"),
        BotCommand("one", "🚪 10 дешёвых 1-к."),
        BotCommand("stats", "📊 статистика"),
        BotCommand("update", "🔄 обновить сейчас"),
        BotCommand("mock", "🛠 mock-обновление (dev)"),
    ]
    loop.run_until_complete(app.bot.set_my_commands(commands))

    # сохраняем repo и monitor для хендлеров
    app.bot_data["repo"] = repo
    app.bot_data["monitor"] = monitor

    # Регистрация команд
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("studios", cmd_studios))
    app.add_handler(CommandHandler("one", cmd_one))
    app.add_handler(CommandHandler("mock", cmd_mockupdate))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("update", cmd_update_now))

    # Обработчики для кнопок-клавиатуры (тексты без слеша)
    button_map = {
        "Студии 🏠": cmd_studios,
        "1-к. 🚪": cmd_one,
        "Статистика 📊": cmd_stats,
        "Обновить сейчас 🔄": cmd_update_now,
        "Mock 🛠": cmd_mockupdate,
    }

    for text, handler in button_map.items():
        app.add_handler(MessageHandler(filters.Regex(f"^{text}$"), handler))

    # Планировщик
    app.job_queue.run_repeating(
        hourly_job,
        interval=settings.summary_interval_seconds,
        # first=settings.summary_interval_seconds,
        first=5,
        data={"monitor": monitor},
        name="hourly_update"
    )

    logger.info("Bot started. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main() 