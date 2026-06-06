"""
Shared keyboards: membership prompt, main menu, and navigation helpers.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..config import config
from ..services.i18n import t
from ..models import Product
from .callbacks import NavCB, SettingsCB, LangCB, ShopCB


def membership_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """Join buttons for the channel & group plus a verify button."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=t("join_channel", lang), url=config.channel_link)
    )
    builder.row(
        InlineKeyboardButton(text=t("join_group", lang), url=config.group_link)
    )
    builder.row(
        InlineKeyboardButton(text=t("verify_btn", lang), callback_data="check_membership")
    )
    return builder.as_markup()


def main_menu(is_admin: bool = False, lang: str = "en", promo_product: Product = None) -> InlineKeyboardMarkup:
    """The primary user menu shown after verification."""
    builder = InlineKeyboardBuilder()

    # Optional promo shortcut at the top
    if promo_product:
        # Determine if it's from points shop or money shop based on category
        is_points = promo_product.category.is_points_shop if promo_product.category else False
        
        custom_emoji_id = None
        product_display_name = promo_product.name
        
        if promo_product.icon_emoji:
            if promo_product.icon_emoji.isdigit():
                custom_emoji_id = promo_product.icon_emoji
            else:
                product_display_name = f"{promo_product.icon_emoji} {promo_product.name}"

        label = t("discover_btn", lang, name=product_display_name)
        
        button_kwargs = {
            "text": label,
            "callback_data": ShopCB(
                action="product", 
                points=is_points, 
                product_id=promo_product.id
            ).pack(),
            "style": "primary"
        }
        if custom_emoji_id:
             button_kwargs["icon_custom_emoji_id"] = custom_emoji_id
             
        builder.row(InlineKeyboardButton(**button_kwargs))

    builder.row(
        InlineKeyboardButton(text=t("shop", lang), callback_data=NavCB(to="shop").pack()),
        InlineKeyboardButton(text=t("points_shop", lang), callback_data=NavCB(to="points_shop").pack()),
    )
    builder.row(
        InlineKeyboardButton(text=t("deposits", lang), callback_data=NavCB(to="deposit").pack()),
        InlineKeyboardButton(text=t("profile", lang), callback_data=NavCB(to="balance").pack()),
    )
    builder.row(
        InlineKeyboardButton(text=t("referral", lang), callback_data=NavCB(to="referral").pack()),
        InlineKeyboardButton(text=t("language", lang), callback_data=SettingsCB(action="language").pack()),
    )
    if is_admin:
        from .callbacks import AdminCB  # local import to avoid cycle at import time
        builder.row(
            InlineKeyboardButton(
                text="🛠 Admin Panel",
                callback_data=AdminCB(section="home").pack(),
            )
        )
    return builder.as_markup()


def settings_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """Settings menu: language selection."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=t("language", lang),
            callback_data=SettingsCB(action="language").pack(),
        )
    )
    builder.row(home_button(lang))
    return builder.as_markup()


def language_selection_keyboard() -> InlineKeyboardMarkup:
    """Pick between English, French, and Arabic."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🇺🇸 English", callback_data=LangCB(code="en").pack()),
        InlineKeyboardButton(text="🇫🇷 Français", callback_data=LangCB(code="fr").pack()),
        InlineKeyboardButton(text="🇩🇿 العربية", callback_data=LangCB(code="ar").pack()),
    )
    builder.row(InlineKeyboardButton(text="⬅️", callback_data=NavCB(to="home").pack()))
    return builder.as_markup()


def home_button(lang: str = "en") -> InlineKeyboardButton:
    """A reusable 'back to main menu' button."""
    return InlineKeyboardButton(text=t("home_btn", lang), callback_data=NavCB(to="home").pack())


def back_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """A single 'main menu' button as a full keyboard."""
    builder = InlineKeyboardBuilder()
    builder.row(home_button(lang))
    return builder.as_markup()
