"""
Typed callback-data factories (aiogram 3.x CallbackData).

Using CallbackData keeps button payloads structured and parseable instead of
fragile string concatenation. Each factory below defines a namespaced payload.
"""

from __future__ import annotations

from typing import Optional

from aiogram.filters.callback_data import CallbackData


# --- Shop navigation (shared by money shop and points shop) ----------------- #
class ShopCB(CallbackData, prefix="shop"):
    # action: "categories" | "category" | "product" | "buy"
    action: str
    points: bool = False          # True => points shop, False => money shop
    category_id: int = 0
    product_id: int = 0


# --- Generic navigation ----------------------------------------------------- #
class NavCB(CallbackData, prefix="nav"):
    # to: "home" | "shop" | "points_shop" | "deposit" | "balance" |
    #     "referral" | "orders" | "settings"
    to: str


class SettingsCB(CallbackData, prefix="set"):
    # action: "language"
    action: str


class LangCB(CallbackData, prefix="lang"):
    code: str  # "en", "fr"


# --- Admin panel ------------------------------------------------------------ #
class AdminCB(CallbackData, prefix="adm"):
    # section: "home" | "cats" | "products" | "orders" | "deposits" |
    #          "users" | "stock"
    section: str
    # action is context-specific. It MUST be Optional[str] (not a plain str with
    # an "" default): aiogram serializes an empty string to an empty field, and
    # when that is unpacked it comes back as None. A non-optional `str` field
    # then fails Pydantic validation, the unpack raises, and the callback
    # silently matches no handler — which is why section buttons did nothing.
    action: Optional[str] = None  # context-specific action
    id: int = 0                   # entity id (category/product/user/deposit)
    page: int = 0
    points: bool = False          # for category creation: points-shop category
