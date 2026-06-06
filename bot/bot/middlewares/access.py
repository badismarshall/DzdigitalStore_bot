"""
Access-control middleware.

Responsibilities, in order:
  1. Ensure a User row exists (capturing referral from /start payload).
  2. Block banned users entirely.
  3. Require BOTH channel and group membership before any feature is usable.
     - The only things allowed through unverified are: the /start command and
       the "check_membership" callback (the verify button), plus admins.
  4. On first successful verification, mark the user verified and reward the
     referrer (granting referral points exactly once).

Verified-state caching: once a user is verified we trust the DB flag and skip
the Telegram API call on every message, re-checking only for unverified users.
This keeps the bot fast while still enforcing the gate for newcomers.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, Message, TelegramObject, User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import config
from ..keyboards.common import membership_keyboard
from ..services import membership_service, notification_service, user_service
from ..services.i18n import t

# Callback data / commands permitted while unverified.
_ALLOWED_UNVERIFIED_CALLBACKS = {"check_membership"}


def _extract_user(event: TelegramObject) -> Optional[TgUser]:
    if isinstance(event, Message):
        return event.from_user
    if isinstance(event, CallbackQuery):
        return event.from_user
    return None


def _extract_referrer_id(event: TelegramObject) -> Optional[int]:
    """Read a referral id from a /start <id> deep-link payload."""
    if isinstance(event, Message) and event.text and event.text.startswith("/start"):
        parts = event.text.split(maxsplit=1)
        if len(parts) == 2:
            payload = parts[1].strip()
            # Support both "/start 12345" and "/start ref_12345"
            payload = payload.removeprefix("ref_")
            if payload.isdigit():
                return int(payload)
    return None


def _is_start_command(event: TelegramObject) -> bool:
    return (
        isinstance(event, Message)
        and event.text is not None
        and event.text.split(maxsplit=1)[0] in {"/start", "/start@"}
    )


def _is_allowed_callback(event: TelegramObject) -> bool:
    return (
        isinstance(event, CallbackQuery)
        and event.data in _ALLOWED_UNVERIFIED_CALLBACKS
    )


async def _prompt_membership(event: TelegramObject, lang: str = "en") -> None:
    """Tell the user to join, with buttons + a verify button."""
    text = (
        t("unverified_warn", lang) +
        f"\n\n• Our Channel: @{config.required_channel}\n"
        f"• Our Group: @{config.required_group}\n\n"
        + t("verify_btn", lang)
    )
    kb = membership_keyboard(lang=lang)
    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb, disable_web_page_preview=True)
    elif isinstance(event, CallbackQuery):
        alert_text = "Please join both the channel and group first."
        if lang == "fr":
            alert_text = "Veuillez d'abord rejoindre le canal et le groupe."
        await event.answer(alert_text, show_alert=True)
        if event.message:
            await event.message.answer(text, reply_markup=kb, disable_web_page_preview=True)


class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        tg_user = _extract_user(event)
        # Non-user events (e.g. channel posts) pass straight through.
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        bot: Bot = data["bot"]
        session: AsyncSession = data["session"]

        # 1. Ensure the user exists, capturing referral on /start.
        referrer_id = _extract_referrer_id(event)
        user = await user_service.get_or_create_user(
            session,
            user_id=tg_user.id,
            username=tg_user.username,
            full_name=tg_user.full_name,
            referrer_id=referrer_id,
        )
        data["user"] = user

        # Admins bypass the membership gate and bans entirely.
        is_admin = config.is_admin(tg_user.id)
        data["is_admin"] = is_admin
        if is_admin:
            return await handler(event, data)

        # 2. Banned users are blocked.
        if user.is_banned:
            msg = "⛔ You are banned from using this bot."
            if user.language_code == "fr":
                msg = "⛔ Vous êtes banni de l'utilisation de ce bot."
            if isinstance(event, Message):
                await event.answer(msg)
            elif isinstance(event, CallbackQuery):
                await event.answer(msg, show_alert=True)
            return None

        # 3. Membership gate.
        # Trust the cached verified flag to avoid an API call on every message.
        if not user.verified:
            verified_now = await membership_service.is_fully_verified(bot, tg_user.id)
            if not verified_now:
                # Allow only /start and the verify button through to handlers,
                # so users can see the prompt; everything else is blocked here.
                if _is_start_command(event) or _is_allowed_callback(event):
                    return await handler(event, data)
                await _prompt_membership(event, lang=user.language_code)
                return None

            # 4. Just became verified — mark and reward referrer once.
            rewarded = await user_service.mark_verified_and_reward_referrer(session, user)
            if rewarded and user.referrer_id:
                try:
                    await bot.send_message(
                        chat_id=user.referrer_id,
                        text=(
                            "🎉 One of your referrals just verified!\n"
                            f"You earned <b>{config.referral_points}</b> points."
                        ),
                    )
                except Exception:  # noqa: BLE001 - never let a notify failure break flow
                    pass

        return await handler(event, data)
