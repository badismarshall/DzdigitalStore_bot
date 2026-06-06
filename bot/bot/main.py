"""
NAZZSHOP entry point.

Initializes logging, the database, the bot/dispatcher, registers middlewares
and routers, then starts long polling.

Run with:  python -m bot.main      (from the project root)
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeDefault

from .config import config
from .database import init_db
from .handlers import setup_routers
from .middlewares.access import AccessMiddleware
from .middlewares.db import DbSessionMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("nazzshop")


async def set_ui_commands(bot: Bot) -> None:
    """Configures the command menu in the Telegram UI."""
    commands = [
        BotCommand(command="start", description="Start or restart the bot"),
    ]
    await bot.set_my_commands(commands=commands, scope=BotCommandScopeDefault())


async def main() -> None:
    # 1. Ensure the database schema exists.
    await init_db()
    logger.info("Database ready.")

    # 2. Bot with HTML parse mode by default so our markup renders.
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # 3. Set UI commands (shows only /start in the menu)
    await set_ui_commands(bot)

    # 3. Dispatcher with in-memory FSM storage.
    #    (For multi-process deployments, swap for Redis storage.)
    dp = Dispatcher(storage=MemoryStorage())

    # 4. Middlewares. Order matters:
    #    - DB session is injected first (outermost) so every later layer/handler
    #      receives `session`.
    #    - Access control runs next and relies on `session` + `bot`.
    for observer in (dp.message, dp.callback_query):
        observer.middleware(DbSessionMiddleware())
        observer.middleware(AccessMiddleware())

    # 5. Routers (feature handlers).
    setup_routers(dp)

    # 6. Drop any pending updates accumulated while the bot was offline, then poll.
    me = await bot.get_me()
    logger.info("Starting NAZZSHOP as @%s (id=%s)", me.username, me.id)
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down NAZZSHOP. Bye!")
