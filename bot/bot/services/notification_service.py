"""
Real-time notifications to the linked group/channel.

CRITICAL PRIVACY RULE: notifications must NEVER reveal the customer's username,
name, or Telegram id. All wording is intentionally generic ("A customer ...").
"""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from ..config import config
from .utils import money

logger = logging.getLogger(__name__)


async def _send(bot: Bot, text: str) -> None:
    """Send a notification, swallowing errors so the user flow never breaks."""
    try:
        await bot.send_message(
            chat_id=config.notify_chat_id,
            text=text,
            disable_web_page_preview=True,
        )
    except TelegramAPIError as exc:
        logger.warning("Failed to send notification: %s", exc)

async def _broadcast_admins(bot: Bot, text: str) -> None:
    """Send a direct message to all configured admins."""
    for admin_id in config.admin_ids:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=text,
                disable_web_page_preview=True,
            )
        except TelegramAPIError as exc:
            logger.warning(f"Failed to send admin notification to {admin_id}: {exc}")

async def notify_new_order(bot: Bot, product_name: str, paid_with_points: bool) -> None:
    method = "points" if paid_with_points else "balance"
    await _send(
        bot,
        "🛒 <b>New Order</b>\n"
        f"A customer just purchased <b>{product_name}</b> using their {method}.",
    )

async def notify_new_deposit(bot: Bot, username_or_name: str) -> None:
    await _broadcast_admins(
        bot,
        "⚠️ <b>Action Required: New Deposit</b>\n\n"
        f"User <b>{username_or_name}</b> has submitted a new crypto deposit for review.\n"
        "Please check the <b>Admin Panel ➡️ Deposits</b> to review it.",
    )


async def notify_product_added(bot: Bot, product_name: str) -> None:
    await _send(
        bot,
        "✨ <b>New Product Available</b>\n"
        f"<b>{product_name}</b> has just been added to the shop!",
    )


async def notify_stock_depleted(bot: Bot, product_name: str) -> None:
    await _send(
        bot,
        "🔴 <b>Out of Stock</b>\n"
        f"<b>{product_name}</b> is now sold out.",
    )


async def notify_product_hidden(bot: Bot, product_name: str) -> None:
    await _send(
        bot,
        "🙈 <b>Product Hidden</b>\n"
        f"<b>{product_name}</b> is temporarily unavailable.",
    )
