"""
Common handlers: /start, membership verification, the main menu, balance view,
and order history.

The AccessMiddleware has already created the User row and (for non-admins)
enforced membership before these handlers run. The "check_membership" callback
is allowed through unverified so users can trigger re-verification.
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import config
from ..keyboards.callbacks import NavCB, SettingsCB, LangCB
from ..keyboards.common import back_keyboard, main_menu, membership_keyboard, settings_keyboard, language_selection_keyboard
from ..models import User
from ..services import membership_service, order_service, user_service, catalog_service
from ..services.i18n import t
from ..services.utils import money


from typing import Union

router = Router(name="common")


async def _show_main_menu(
    target: Union[Message, CallbackQuery], user: User, is_admin: bool, session: AsyncSession
) -> None:
    lang = user.language_code

    # Fetch a random product for the "Quick Discovery" shortcut button
    promo = await catalog_service.get_random_available_product(session)

    # Personalized welcome message
    display_name = user.full_name or f"@{user.username}" if user.username else "Customer"
    welcome_text = t("welcome_user", lang, name=display_name)
    # Extra \n for space between welcome and description
    description = "\n" + t("shop_tagline", lang)
    
    text = (
        welcome_text
        + description
        + f"\n\n💼 {t('profile', lang)}: <b>{money(user.balance_cents)}</b>"
        + f"\n🎯 Points: <b>{user.points}</b>"
        + t("choose_option", lang)
    )

    markup = main_menu(is_admin=is_admin, lang=lang, promo_product=promo)

    if isinstance(target, Message):
        await target.answer(text, reply_markup=markup)
    elif isinstance(target, CallbackQuery) and target.message:
        if target.message.photo or target.message.document:
            await target.message.delete()
            await target.message.answer(text, reply_markup=markup)
        else:
            await target.message.edit_text(text, reply_markup=markup)


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    user: User,
    is_admin: bool,
    state: FSMContext,
) -> None:
    await state.clear()
    lang = user.language_code

    # Admins skip the gate.
    if is_admin:
        await _show_main_menu(message, user, is_admin, session)
        return

    # If already verified (flag set by middleware), show the menu.
    if user.verified:
        await _show_main_menu(message, user, is_admin, session)
        return


    # Otherwise prompt to join.
    await message.answer(
        t("unverified_warn", lang) +
        f"\n\n• Channel: @{config.required_channel}\n"
        f"• Group: @{config.required_group}\n\n"
        + t("verify_btn", lang),
        reply_markup=membership_keyboard(lang=lang),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data == "check_membership")
async def cb_check_membership(
    callback: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    is_admin: bool,
) -> None:
    lang = user.language_code
    in_channel, in_group = await membership_service.check_membership(bot, user.id)

    if not (in_channel and in_group):
        missing = []
        if not in_channel:
            missing.append(f"channel (@{config.required_channel})")
        if not in_group:
            missing.append(f"group (@{config.required_group})")
        
        await callback.answer(
            t("missing_membership", lang, missing=", ".join(missing)),
            show_alert=True,
        )
        return

    # Verified — reward referrer once.
    rewarded = await user_service.mark_verified_and_reward_referrer(session, user)
    if rewarded and user.referrer_id:
        try:
            # Referral notification (defaulting to referrer's lang if we had it, 
            # but for now simple English is often used in logs/notifications)
            await bot.send_message(
                chat_id=user.referrer_id,
                text=(
                    "🎉 One of your referrals just verified!\n"
                    f"You earned <b>{config.referral_points}</b> points."
                ),
            )
        except Exception:  # noqa: BLE001
            pass

    await callback.answer("✅ Verified!" if lang == "en" else "✅ Vérifié !")
    await _show_main_menu(callback, user, is_admin, session)


@router.callback_query(NavCB.filter(F.to == "home"))
async def cb_home(
    callback: CallbackQuery, user: User, is_admin: bool, session: AsyncSession, state: FSMContext
) -> None:
    await state.clear()
    await callback.answer()
    await _show_main_menu(callback, user, is_admin, session)


@router.callback_query(SettingsCB.filter(F.action == "language"))
async def cb_settings_language(callback: CallbackQuery, user: User) -> None:
    await callback.answer()
    lang = user.language_code
    if callback.message:
        await callback.message.edit_text(
            t("select_language", lang),
            reply_markup=language_selection_keyboard(),
        )


@router.callback_query(LangCB.filter())
async def cb_set_language(
    callback: CallbackQuery,
    callback_data: LangCB,
    session: AsyncSession,
    user: User,
    is_admin: bool,
) -> None:
    await user_service.set_language(session, user, callback_data.code)
    await callback.answer(t("lang_updated", user.language_code))
    # Refresh back to the main menu
    await _show_main_menu(callback, user, is_admin, session)


@router.callback_query(NavCB.filter(F.to == "balance"))
async def cb_balance(callback: CallbackQuery, user: User) -> None:
    await callback.answer()
    lang = user.language_code
    # Note: In a full production bot, all these strings would be in _STRINGS.
    # For now, I'll translate the core labels.
    text = (
        f"💼 <b>{t('profile', lang)}</b>\n\n"
        f"Money balance: <b>{money(user.balance_cents)}</b>\n"
        f"Referral points: <b>{user.points}</b>\n\n"
        "Top up your balance from the Deposit menu, or earn points by inviting friends."
    )
    if lang == "fr":
        text = (
            f"💼 <b>{t('profile', lang)}</b>\n\n"
            f"Solde : <b>{money(user.balance_cents)}</b>\n"
            f"Points de parrainage : <b>{user.points}</b>\n\n"
            "Rechargez votre solde via le menu Dépôt, ou gagnez des points en invitant des amis."
        )

    if callback.message:
        await callback.message.edit_text(text, reply_markup=back_keyboard(lang))


@router.callback_query(NavCB.filter(F.to == "orders"))
async def cb_orders(callback: CallbackQuery, session: AsyncSession, user: User) -> None:
    await callback.answer()
    lang = user.language_code
    orders = await order_service.list_user_orders(session, user.id, limit=10)
    
    title = "📦 <b>My Orders</b>" if lang == "en" else "📦 <b>Mes Commandes</b>"
    no_orders = "You have no orders yet." if lang == "en" else "Vous n'avez pas encore de commandes."

    if not orders:
        text = f"{title}\n\n{no_orders}"
    else:
        lines = [f"{title}\n"]
        for o in orders:
            if o.method.value == "points":
                price = f"{o.amount} pts"
            else:
                price = money(o.amount)
            lines.append(f"• #{o.id} — {o.product_name} ({price})")
            if o.delivered_content:
                lines.append(f"   🔑 <code>{o.delivered_content}</code>")
        text = "\n".join(lines)
    if callback.message:
        await callback.message.edit_text(text, reply_markup=back_keyboard(lang))


@router.message(Command("menu"))
async def cmd_menu(
    message: Message, user: User, is_admin: bool, session: AsyncSession, state: FSMContext
) -> None:
    await state.clear()
    await _show_main_menu(message, user, is_admin, session)
