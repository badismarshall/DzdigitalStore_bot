"""
Deposit handlers: shows wallet addresses and walks the user through submitting
a TxID. Submissions are stored as PENDING and surfaced to admins for review.
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import config
from ..keyboards.callbacks import NavCB
from ..keyboards.common import back_keyboard, home_button
from ..models import User
from ..services import deposit_service, notification_service
from ..services.deposit_service import DepositError
from ..services.i18n import t
from ..services.utils import clean, is_plausible_txid, parse_money_to_cents
from .states import DepositStates

router = Router(name="deposit")


@router.callback_query(NavCB.filter(F.to == "deposit"))
async def open_deposit(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    await state.clear()
    await callback.answer()
    lang = user.language_code

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=t("submit_txid_btn", lang), callback_data="deposit_submit")
    )
    builder.row(home_button(lang))

    text = t("deposit_title", lang)
    if callback.message:
        await callback.message.edit_text(
            text, reply_markup=builder.as_markup(), disable_web_page_preview=True
        )


@router.callback_query(F.data == "deposit_submit")
async def start_submit(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    await callback.answer()
    await state.set_state(DepositStates.waiting_amount)
    lang = user.language_code

    if callback.message:
        await callback.message.edit_text(
            t("send_amount", lang, symbol=config.currency_symbol),
            reply_markup=back_keyboard(lang),
        )


@router.message(DepositStates.waiting_amount)
async def receive_amount(
    message: Message,
    state: FSMContext,
    user: User,
) -> None:
    lang = user.language_code
    amount_cents = parse_money_to_cents(message.text or "")
    if amount_cents is None or amount_cents == 0:
        await message.answer(
            t("invalid_amount", lang),
            reply_markup=back_keyboard(lang),
        )
        return

    await state.update_data(amount_cents=amount_cents)
    
    # Send confirmation keyboard
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=t("confirm_yes", lang), callback_data="deposit_confirm"),
        InlineKeyboardButton(text=t("confirm_no", lang), callback_data=NavCB(to="home").pack())
    )
    
    await state.set_state(DepositStates.waiting_amount_confirm)
    await message.answer(
        t("confirm_deposit", lang, symbol=config.currency_symbol, amount=f"{amount_cents / 100:.2f}"),
        reply_markup=builder.as_markup()
    )


@router.callback_query(DepositStates.waiting_amount_confirm, F.data == "deposit_confirm")
async def confirm_deposit_amount(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
) -> None:
    await callback.answer()
    lang = user.language_code
    data = await state.get_data()
    
    amount_cents = data.get("amount_cents", 0)
    
    import uuid
    # Generate a unique dummy TxID since it's required by the DB
    txid = f"deposit-{uuid.uuid4().hex[:12]}"

    try:
        deposit = await deposit_service.submit_deposit(
            session, user, txid=txid, amount_cents=amount_cents
        )
    except DepositError as exc:
        if callback.message:
            await callback.message.edit_text(f"⚠️ {exc}", reply_markup=back_keyboard(lang))
        await state.clear()
        return

    await state.clear()
    
    text = t("deposit_submitted", lang,
            id=deposit.id,
            symbol=config.currency_symbol,
            amount=f"{amount_cents / 100:.2f}"
    )
    
    if callback.message:
        await callback.message.edit_text(text, reply_markup=back_keyboard(lang))

    # Notify admins about the new deposit requiring confirmation
    display_name = f"@{user.username}" if user.username else (user.full_name or f"ID: {user.id}")
    await notification_service.notify_new_deposit(bot, username_or_name=display_name)

