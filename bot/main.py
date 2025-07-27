import asyncio
import logging
from typing import Callable, Union
import json

from loguru import logger
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
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
    await update.message.reply_text(
        "Привет! Я слежу за ценами в ЖК «Яуза Парк».\n"
        "Команды:\n"
        "/studios — 10 самых дешёвых студий\n"
        "/one — 10 самых дешёвых 1-к. квартир"
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
        flats.append(
            Flat(
                id=item.get("id"),
                rooms=str(item.get("rooms")),
                price=item.get("price", 0),
                status=item.get("status", "unknown"),
                url=item.get("url", ""),
                area=item.get("area"),
                floor=item.get("floor"),
            )
        )

    monitor: MonitorService = context.application.bot_data["monitor"]
    summary = await monitor.update_from_list(flats)
    await _send_long_text(context.bot, update.effective_chat.id, summary)


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


async def hourly_job(context: ContextTypes.DEFAULT_TYPE):
    monitor: MonitorService = context.job.data["monitor"]
    settings = get_settings()
    summary = await monitor.update_from_api()
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

    # сохраняем repo и monitor для хендлеров
    app.bot_data["repo"] = repo
    app.bot_data["monitor"] = monitor

    # Регистрация команд
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("studios", cmd_studios))
    app.add_handler(CommandHandler("one", cmd_one))
    app.add_handler(CommandHandler("mock", cmd_mockupdate))

    # Планировщик
    app.job_queue.run_repeating(
        hourly_job,
        interval=settings.summary_interval_seconds,
        first=settings.summary_interval_seconds,
        # first=5,
        data={"monitor": monitor},
    )

    logger.info("Bot started. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main() 