"""
Admin broadcast service.

Lets an admin push a message to one of three destinations:
  * the required channel,
  * the required group,
  * every (non-banned) bot user, in their private chat.

Channel/group sends are single calls. The "all users" broadcast iterates over
every user id, sends in small throttled batches to respect Telegram's rate
limits, and counts successes/failures (users who blocked the bot or were never
reachable simply fail silently and are tallied).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Sequence

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter, TelegramAPIError

from ..config import config

logger = logging.getLogger(__name__)

# Telegram tolerates ~30 messages/sec to different chats. We stay well under it.
_BATCH_SIZE = 20
_BATCH_PAUSE = 1.0  # seconds between batches


@dataclass
class BroadcastResult:
    target: str          # "channel" | "group" | "users"
    delivered: int = 0
    failed: int = 0
    ok: bool = True      # for single-target sends (channel/group)
    error: str | None = None


async def send_to_channel(bot: Bot, text: str) -> BroadcastResult:
    """Post a message to the required channel."""
    try:
        await bot.send_message(
            chat_id=config.channel_chat_id, text=text, disable_web_page_preview=True
        )
        return BroadcastResult(target="channel", delivered=1, ok=True)
    except TelegramAPIError as exc:
        logger.warning("Channel broadcast failed: %s", exc)
        return BroadcastResult(target="channel", failed=1, ok=False, error=str(exc))


async def send_to_group(bot: Bot, text: str) -> BroadcastResult:
    """Post a message to the required group."""
    try:
        await bot.send_message(
            chat_id=config.group_chat_id, text=text, disable_web_page_preview=True
        )
        return BroadcastResult(target="group", delivered=1, ok=True)
    except TelegramAPIError as exc:
        logger.warning("Group broadcast failed: %s", exc)
        return BroadcastResult(target="group", failed=1, ok=False, error=str(exc))


async def send_to_users(bot: Bot, user_ids: Sequence[int], text: str) -> BroadcastResult:
    """
    Send a message to every given user id in throttled batches.

    Users who have blocked the bot (TelegramForbiddenError) or are otherwise
    unreachable are counted as failures without aborting the whole run. Honors
    Telegram's flood-control RetryAfter by waiting the requested time.
    """
    result = BroadcastResult(target="users")

    for start in range(0, len(user_ids), _BATCH_SIZE):
        batch = user_ids[start : start + _BATCH_SIZE]
        for uid in batch:
            try:
                await bot.send_message(
                    chat_id=uid, text=text, disable_web_page_preview=True
                )
                result.delivered += 1
            except TelegramRetryAfter as exc:
                # Flood control: wait, then retry this single user once.
                await asyncio.sleep(exc.retry_after)
                try:
                    await bot.send_message(
                        chat_id=uid, text=text, disable_web_page_preview=True
                    )
                    result.delivered += 1
                except TelegramAPIError:
                    result.failed += 1
            except TelegramForbiddenError:
                # User blocked the bot or never started it.
                result.failed += 1
            except TelegramAPIError as exc:
                logger.debug("Broadcast to %s failed: %s", uid, exc)
                result.failed += 1

        # Pause between batches to stay under rate limits.
        if start + _BATCH_SIZE < len(user_ids):
            await asyncio.sleep(_BATCH_PAUSE)

    result.ok = result.failed == 0
    return result


async def send_to_all(bot: Bot, user_ids: Sequence[int], text: str) -> BroadcastResult:
    """
    Send a message to the required channel, group, AND every user.
    Aggregates the total delivery counts into a single result.
    """
    final_result = BroadcastResult(target="all")

    # 1. Channel
    res_channel = await send_to_channel(bot, text)
    final_result.delivered += res_channel.delivered
    final_result.failed += res_channel.failed

    # 2. Group
    res_group = await send_to_group(bot, text)
    final_result.delivered += res_group.delivered
    final_result.failed += res_group.failed

    # 3. Users
    res_users = await send_to_users(bot, user_ids, text)
    final_result.delivered += res_users.delivered
    final_result.failed += res_users.failed

    final_result.ok = res_channel.ok and res_group.ok and res_users.ok
    return final_result
