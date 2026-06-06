"""
Shop keyboards used by BOTH the money shop and the points shop. The `points`
flag toggles wording and which price is shown.
"""

from __future__ import annotations

from typing import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..models import Category, Product
from ..services.i18n import t
from .callbacks import NavCB, ShopCB
from .common import home_button


def categories_keyboard(
    categories: Sequence[Category], points: bool, lang: str = "en"
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.row(
            InlineKeyboardButton(
                text=f"📂 {cat.name}",
                callback_data=ShopCB(
                    action="category", points=points, category_id=cat.id
                ).pack(),
            )
        )
    builder.row(home_button(lang))
    return builder.as_markup()


def products_keyboard(
    products: Sequence[Product], category_id: int, points: bool, lang: str = "en"
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in products:
        icon_prefix = ""
        custom_emoji_id = None

        if p.icon_emoji:
            if p.icon_emoji.isdigit():
                # It's a custom emoji ID
                custom_emoji_id = p.icon_emoji
            else:
                # It's a standard unicode emoji
                icon_prefix = f"{p.icon_emoji} "

        # Style: [Emoji] Product Name | 📦 Qty | $Price
        if points:
            label = f"{icon_prefix}{p.name} | 📦 {p.quantity} | 🎯 {p.points_price} pts"
        else:
            label = f"{icon_prefix}{p.name} | 📦 {p.quantity} | ${p.price:.2f}"
        
        button_kwargs = {
            "text": label,
            "callback_data": ShopCB(action="product", points=points, product_id=p.id).pack()
        }

        # In aiogram 3.28.2+, icon_custom_emoji_id is an optional parameter for InlineKeyboardButton
        if custom_emoji_id:
             button_kwargs["icon_custom_emoji_id"] = custom_emoji_id
             
        # Telegram API 9.4 supports three styles: "primary" (blue), "secondary" (gray), and "danger" (red).
        button_kwargs["style"] = "primary" if p.available else "danger"

        builder.row(InlineKeyboardButton(**button_kwargs))

    # Back to category list.
    builder.row(
        InlineKeyboardButton(
            text=t("back_btn", lang),
            callback_data=ShopCB(action="categories", points=points).pack(),
        ),
        home_button(lang),
    )
    return builder.as_markup()


def product_detail_keyboard(product: Product, points: bool, lang: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    # Buy button only appears when the product is actually purchasable.
    can_buy = product.available and (not points or product.points_price > 0)
    if can_buy:
        label = t("redeem_btn", lang) if points else t("buy_btn", lang)
        builder.row(
            InlineKeyboardButton(
                text=label,
                callback_data=ShopCB(
                    action="buy", points=points, product_id=product.id
                ).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=t("back_btn", lang),
            callback_data=ShopCB(
                action="category", points=points, category_id=product.category_id
            ).pack(),
        ),
        home_button(lang),
    )
    return builder.as_markup()
