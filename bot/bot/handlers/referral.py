"""
Referral handler: shows the user's personal invite link, current points, and
how many people they've referred. Points are awarded by the access middleware
(or the verify callback) when an invited user becomes verified.
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import config
from ..keyboards.callbacks import NavCB
from ..keyboards.common import back_keyboard
from ..models import User
from ..services import user_service
from ..services.i18n import t

router = Router(name="referral")


@router.callback_query(NavCB.filter(F.to == "referral"))
async def show_referral(
    callback: CallbackQuery, session: AsyncSession, user: User, bot: Bot
) -> None:
    await callback.answer()
    lang = user.language_code

    me = await bot.get_me()
    invite_link = f"https://t.me/{me.username}?start={user.id}"
    referral_count = await user_service.count_referrals(session, user.id)

    text = t("referral_title", lang,
        points=config.referral_points,
        link=invite_link,
        total_points=user.points,
        count=referral_count
    )
    if callback.message:
        await callback.message.edit_text(
            text, reply_markup=back_keyboard(lang), disable_web_page_preview=True
        )
