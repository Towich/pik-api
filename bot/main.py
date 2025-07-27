import asyncio
import logging
from typing import Callable

from loguru import logger
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from bot.config import get_settings
from bot.repository import FlatRepository
from bot.services import MonitorService

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
    lines = [
        f"#{idx + 1}: {flat.price / 1_000_000:.2f} млн · этаж {flat.floor} · {flat.url}"
        for idx, flat in enumerate(flats)
    ]
    await update.message.reply_text("Самые дешёвые студии:\n" + "\n".join(lines))


async def cmd_one(update: Update, context: ContextTypes.DEFAULT_TYPE):
    repo: FlatRepository = context.application.bot_data["repo"]
    flats = await repo.select_cheapest(["1"], limit=10)
    if not flats:
        await update.message.reply_text("Нет данных. Попробуйте позже.")
        return
    lines = [
        f"#{idx + 1}: {flat.price / 1_000_000:.2f} млн · этаж {flat.floor} · {flat.url}"
        for idx, flat in enumerate(flats)
    ]
    await update.message.reply_text("Самые дешёвые 1-к.:\n" + "\n".join(lines))


# --------------------------- jobs --------------------------------------


async def hourly_job(context: ContextTypes.DEFAULT_TYPE):
    monitor: MonitorService = context.job.data["monitor"]
    settings = get_settings()
    summary = await monitor.refresh_and_diff()
    await context.bot.send_message(chat_id=settings.telegram_chat_id, text=summary)


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

    # сохраняем repo для хендлеров
    app.bot_data["repo"] = repo

    # Регистрация команд
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("studios", cmd_studios))
    app.add_handler(CommandHandler("one", cmd_one))

    # Планировщик
    app.job_queue.run_repeating(
        hourly_job,
        interval=settings.summary_interval_seconds,
        first=5,
        data={"monitor": monitor},
    )

    logger.info("Bot started. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main() 