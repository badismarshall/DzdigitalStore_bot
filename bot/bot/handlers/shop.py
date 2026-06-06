"""
Shop handlers for both the money shop and the points shop.

The same code path serves both shops; the `points` flag in ShopCB decides which
catalog (points-shop categories vs money categories) and which price applies.
"""

from __future__ import annotations

import os

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, FSInputFile, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..keyboards.callbacks import NavCB, ShopCB
from ..keyboards.common import back_keyboard
from ..keyboards.shop import (
    categories_keyboard,
    product_detail_keyboard,
    products_keyboard,
)
from ..models import User
from ..services import catalog_service, notification_service, order_service
from ..services.i18n import t
from ..services.order_service import PurchaseError
from ..services.utils import clean, money

router = Router(name="shop")


# --------------------------------------------------------------------------- #
# Entry points from the main menu
# --------------------------------------------------------------------------- #
@router.callback_query(NavCB.filter(F.to == "shop"))
async def open_money_shop(callback: CallbackQuery, session: AsyncSession, user: User) -> None:
    await _show_categories(callback, session, points=False, lang=user.language_code)


@router.callback_query(NavCB.filter(F.to == "points_shop"))
async def open_points_shop(callback: CallbackQuery, session: AsyncSession, user: User) -> None:
    await _show_categories(callback, session, points=True, lang=user.language_code)


@router.callback_query(ShopCB.filter(F.action == "categories"))
async def back_to_categories(
    callback: CallbackQuery, callback_data: ShopCB, session: AsyncSession, user: User
) -> None:
    await _show_categories(callback, session, points=callback_data.points, lang=user.language_code)


async def _answer_shop(
    callback: CallbackQuery, text: str, reply_markup=None, image_path: str = None
) -> None:
    """
    Helper to send or edit a shop message. 
    Handles the transition from text-only messages to photo messages and vice-versa.
    """
    if callback.message is None:
        return

    # If an image is provided, we must send it as a media message.
    if image_path and os.path.exists(image_path):
        # We can't edit a text message into a media message. 
        # Always delete the old one and send a new media message.
        await callback.message.delete()
        
        # Telegram sendPhoto does not support .ico files and throws IMAGE_PROCESS_FAILED.
        # Send .ico files as a document instead.
        if image_path.lower().endswith(".ico"):
            await callback.message.answer_document(
                FSInputFile(image_path), caption=text, reply_markup=reply_markup
            )
        else:
            await callback.message.answer_photo(
                FSInputFile(image_path), caption=text, reply_markup=reply_markup
            )
        return

    # If NO image is provided, we want to send a text message.
    # If the current message IS a photo, we must delete it and send a new text message.
    if callback.message.photo or callback.message.document:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=reply_markup)
    else:
        # Standard text-to-text transition.
        await callback.message.edit_text(text, reply_markup=reply_markup)


async def _show_categories(
    callback: CallbackQuery, session: AsyncSession, points: bool, lang: str = "en"
) -> None:
    await callback.answer()
    categories = await catalog_service.list_categories(session, is_points_shop=points)
    title = t("points_shop", lang) if points else t("shop", lang)
    if not categories:
        text = t("no_cats", lang, title=title)
        await _answer_shop(callback, text, reply_markup=back_keyboard(lang))
        return
    text = t("choose_cat", lang, title=title)
    await _answer_shop(
        callback, text, reply_markup=categories_keyboard(categories, points=points, lang=lang)
    )


# --------------------------------------------------------------------------- #
# Category -> product list
# --------------------------------------------------------------------------- #
@router.callback_query(ShopCB.filter(F.action == "category"))
async def show_products(
    callback: CallbackQuery, callback_data: ShopCB, session: AsyncSession, user: User
) -> None:
    await callback.answer()
    lang = user.language_code
    category = await catalog_service.get_category(session, callback_data.category_id)
    if category is None or category.hidden:
        await callback.answer(t("cat_unavailable", lang), show_alert=True)
        return

    products = await catalog_service.list_products(session, category.id)
    title = "🎁" if callback_data.points else "🛍"
    if not products:
        text = t("no_products", lang, title=title, name=clean(category.name))
        await _answer_shop(
            callback,
            text,
            reply_markup=products_keyboard([], category.id, callback_data.points, lang=lang),
        )
        return

    text = t("choose_product", lang, title=title, name=clean(category.name))
    await _answer_shop(
        callback,
        text,
        reply_markup=products_keyboard(products, category.id, callback_data.points, lang=lang),
    )


# --------------------------------------------------------------------------- #
# Product detail
# --------------------------------------------------------------------------- #
@router.callback_query(ShopCB.filter(F.action == "product"))
async def show_product(
    callback: CallbackQuery, callback_data: ShopCB, session: AsyncSession, user: User
) -> None:
    await callback.answer()
    lang = user.language_code
    product = await catalog_service.get_product(session, callback_data.product_id)
    if product is None:
        await callback.answer(t("product_not_found", lang), show_alert=True)
        return

    if callback_data.points:
        price_line = t("price_points", lang, price=product.points_price)
    else:
        price_line = t("price_money", lang, price=money(product.price_cents))

    status = t("status_avail", lang) if product.available else t("status_unavail", lang)
    desc = clean(product.description) if product.description else "—"

    text = t(
        "product_details", 
        lang, 
        name=clean(product.name), 
        id=product.public_id, 
        desc=desc, 
        price_line=price_line, 
        stock_line=t('stock_qty', lang, qty=product.quantity), 
        status=status
    )

    if lang == "ar":
        # Prepend the Right-to-Left Mark (\u200F) to each line to force RTL alignment
        text = "\n".join("\u200F" + line if line.strip() else line for line in text.split("\n"))

    await _answer_shop(
        callback,
        text,
        reply_markup=product_detail_keyboard(product, points=callback_data.points, lang=lang),
        image_path=product.image_path
    )


# --------------------------------------------------------------------------- #
# Buy / redeem
# --------------------------------------------------------------------------- #
@router.callback_query(ShopCB.filter(F.action == "buy"))
async def buy_product(
    callback: CallbackQuery,
    callback_data: ShopCB,
    session: AsyncSession,
    user: User,
    bot: Bot,
) -> None:
    lang = user.language_code
    product = await catalog_service.get_product(session, callback_data.product_id)
    if product is None:
        await callback.answer(t("product_not_found", lang), show_alert=True)
        return

    try:
        if callback_data.points:
            result = await order_service.purchase_with_points(session, user, product)
        else:
            result = await order_service.purchase_with_balance(session, user, product)
    except PurchaseError as exc:
        # PurchaseError messages are usually hardcoded in service, but we can try to translate
        err_msg = str(exc)
        if "balance" in err_msg.lower():
            err_msg = "Insufficient balance." if lang == "en" else "Solde insuffisant."
        elif "stock" in err_msg.lower():
            err_msg = "Out of stock." if lang == "en" else "Rupture de stock."
            
        await callback.answer(err_msg, show_alert=True)
        return

    await callback.answer(t("purchase_success", lang))

    # Build the delivery message.
    if callback_data.points:
        paid_line = t("paid_points", lang, amount=result.order.amount)
        remaining_line = t("rem_points", lang, amount=user.points)
    else:
        paid_line = t("paid_money", lang, amount=money(result.order.amount))
        remaining_line = t("rem_balance", lang, amount=money(user.balance_cents))

    content_line = ""
    if result.delivered_content:
        # Do not clean or wrap in <code> so admins can use HTML in stock items
        content_line = f"{t('your_item', lang)}\n{result.delivered_content}"
    else:
        content_line = t("order_recorded", lang)

    summary = t("purchase_complete", lang,
        name=clean(product.name),
        paid_line=paid_line,
        remaining_line=remaining_line,
        content_line=content_line
    )

    await _answer_shop(callback, summary, reply_markup=back_keyboard(lang))

    # Notifications (generic, no customer identity).
    await notification_service.notify_new_order(
        bot, product_name=product.name, paid_with_points=callback_data.points
    )
    if result.stock_depleted:
        await notification_service.notify_stock_depleted(bot, product_name=product.name)
