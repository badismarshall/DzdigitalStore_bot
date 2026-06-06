"""
Membership verification.

A user must be a member of BOTH the required channel and the required group
before they can use any bot feature. We verify by calling Telegram's
get_chat_member using public @usernames (never numeric IDs, per requirements).

Important: the bot must itself be an administrator of the channel/group for
these checks to succeed.
"""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError

from ..config import config

logger = logging.getLogger(__name__)

# Statuses that count as "is a member".
_MEMBER_STATUSES = {
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
}


async def _is_member(bot: Bot, chat_id: str, user_id: int) -> bool:
    """Return True if user_id is a member of chat_id; False on any failure."""
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    except TelegramAPIError as exc:
        # Common causes: bot is not admin in the chat, chat username wrong,
        # or the user has never interacted with the chat. Treat as "not member".
        logger.warning("Membership check failed for %s in %s: %s", user_id, chat_id, exc)
        return False
    return member.status in _MEMBER_STATUSES


async def check_membership(bot: Bot, user_id: int) -> tuple[bool, bool]:
    """
    Check both memberships.

    Returns a tuple (in_channel, in_group).
    """
    in_channel = await _is_member(bot, config.channel_chat_id, user_id)
    in_group = await _is_member(bot, config.group_chat_id, user_id)
    return in_channel, in_group


async def is_fully_verified(bot: Bot, user_id: int) -> bool:
    """Convenience: True only if the user is in BOTH the channel and group."""
    in_channel, in_group = await check_membership(bot, user_id)
    return in_channel and in_group
