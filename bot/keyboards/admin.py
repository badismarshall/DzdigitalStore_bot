"""
Admin-panel keyboards. Every admin action is reachable via inline keyboards.
"""

from __future__ import annotations

from typing import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..models import Category, Deposit, Product, User, StockItem
from .callbacks import AdminCB
from .common import home_button


def admin_home(pending_deposits: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📂 Categories", callback_data=AdminCB(section="cats").pack()),
        InlineKeyboardButton(text="📦 Products", callback_data=AdminCB(section="products").pack()),
    )
    deposit_label = "💵 Deposits"
    if pending_deposits:
        deposit_label += f" ({pending_deposits})"
    builder.row(
        InlineKeyboardButton(text="🧾 Orders", callback_data=AdminCB(section="orders").pack()),
        InlineKeyboardButton(text=deposit_label, callback_data=AdminCB(section="deposits").pack()),
    )
    builder.row(
        InlineKeyboardButton(text="👤 Users", callback_data=AdminCB(section="users").pack()),
        InlineKeyboardButton(text="📊 Stats", callback_data=AdminCB(section="stats").pack()),
    )
    builder.row(
        InlineKeyboardButton(
            text="📣 Broadcast", callback_data=AdminCB(section="broadcast").pack()
        ),
    )
    builder.row(home_button())
    return builder.as_markup()


# --------------------------------------------------------------------------- #
# Categories
# --------------------------------------------------------------------------- #
def admin_categories(categories: Sequence[Category]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        tag = "🎁" if cat.is_points_shop else "🛍"
        vis = "🙈" if cat.hidden else "👁"
        builder.row(
            InlineKeyboardButton(
                text=f"{tag}{vis} {cat.name}",
                callback_data=AdminCB(section="cats", action="view", id=cat.id).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="➕ New Money Category",
            callback_data=AdminCB(section="cats", action="new", points=False).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="➕ New Points Category",
            callback_data=AdminCB(section="cats", action="new", points=True).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Admin", callback_data=AdminCB(section="home").pack()),
        home_button(),
    )
    return builder.as_markup()


def admin_category_view(category: Category) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✏️ Rename",
            callback_data=AdminCB(section="cats", action="rename", id=category.id).pack(),
        ),
        InlineKeyboardButton(
            text=("👁 Unhide" if category.hidden else "🙈 Hide"),
            callback_data=AdminCB(section="cats", action="toggle", id=category.id).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🗑 Delete",
            callback_data=AdminCB(section="cats", action="delete", id=category.id).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Categories", callback_data=AdminCB(section="cats").pack()),
        home_button(),
    )
    return builder.as_markup()


def confirm_keyboard(section: str, action: str, entity_id: int) -> InlineKeyboardMarkup:
    """A generic yes/no confirmation keyboard for destructive actions."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Confirm",
            callback_data=AdminCB(section=section, action=action, id=entity_id).pack(),
        ),
        InlineKeyboardButton(
            text="❌ Cancel",
            callback_data=AdminCB(section=section).pack(),
        ),
    )
    return builder.as_markup()


# --------------------------------------------------------------------------- #
# Products
# --------------------------------------------------------------------------- #
def admin_products(products: Sequence[Product]) -> InlineKeyboardMarkup:
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

        label = f"{icon_prefix}{p.public_id} · {p.name} (x{p.quantity})"
        if p.hidden:
            label = f"🙈 {label}"
            
        button_kwargs = {
            "text": label,
            "callback_data": AdminCB(section="products", action="view", id=p.id).pack(),
            "style": "primary" if p.available else "danger"
        }
        
        if custom_emoji_id:
             button_kwargs["icon_custom_emoji_id"] = custom_emoji_id

        builder.row(InlineKeyboardButton(**button_kwargs))
        
    builder.row(
        InlineKeyboardButton(
            text="➕ New Product",
            callback_data=AdminCB(section="products", action="new").pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Admin", callback_data=AdminCB(section="home").pack()),
        home_button(),
    )
    return builder.as_markup()


def admin_product_view(product: Product) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✏️ Rename",
            callback_data=AdminCB(section="products", action="edit_name", id=product.id).pack(),
        ),
        InlineKeyboardButton(
            text="🎀 Set Emoji Icon",
            callback_data=AdminCB(section="products", action="edit_icon", id=product.id).pack(),
        ),
        InlineKeyboardButton(
            text="📝 Description",
            callback_data=AdminCB(section="products", action="edit_desc", id=product.id).pack(),
        ),
    )

    builder.row(
        InlineKeyboardButton(
            text="💲 Price",
            callback_data=AdminCB(section="products", action="edit_price", id=product.id).pack(),
        ),
        InlineKeyboardButton(
            text="🎯 Points Price",
            callback_data=AdminCB(section="products", action="edit_points", id=product.id).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="➕ Add Stock Items",
            callback_data=AdminCB(section="products", action="add_stock", id=product.id).pack(),
        ),
        InlineKeyboardButton(
            text="🔢 Set Quantity",
            callback_data=AdminCB(section="products", action="set_qty", id=product.id).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="📦 View Stock Items",
            callback_data=AdminCB(section="stock", action="list", id=product.id).pack(),
        ),
        InlineKeyboardButton(
            text="🖼 Set Image",
            callback_data=AdminCB(section="products", action="edit_image", id=product.id).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=("👁 Unhide" if product.hidden else "🙈 Hide"),
            callback_data=AdminCB(section="products", action="toggle", id=product.id).pack(),
        ),
        InlineKeyboardButton(
            text="🗑 Delete",
            callback_data=AdminCB(section="products", action="delete", id=product.id).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Products", callback_data=AdminCB(section="products").pack()),
        home_button(),
    )
    return builder.as_markup()


def admin_add_stock_mode(product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📝 Bulk Add (Line by Line)",
            callback_data=AdminCB(section="products", action="add_stock_bulk", id=product_id).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="✍️ Manual Add (Single HTML Block)",
            callback_data=AdminCB(section="products", action="add_stock_manual", id=product_id).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Back to Product", callback_data=AdminCB(section="products", action="view", id=product_id).pack()),
        home_button(),
    )
    return builder.as_markup()


def admin_stock_items(product_id: int, items: Sequence[StockItem], page: int = 0, has_next: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in items:
        # Show a preview of the content
        preview = item.content[:20] + "..." if len(item.content) > 20 else item.content
        status = "🔴 Sold" if item.sold else "🟢 Available"
        builder.row(
            InlineKeyboardButton(
                text=f"{status} | #{item.id} {preview}",
                callback_data=AdminCB(section="stock", action="view", id=item.id).pack(),
            )
        )
    
    nav_row = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(
                text="⬅️ Prev",
                callback_data=AdminCB(section="stock", action="page", id=product_id, page=page - 1).pack(),
            )
        )
    if has_next:
        nav_row.append(
            InlineKeyboardButton(
                text="Next ➡️",
                callback_data=AdminCB(section="stock", action="page", id=product_id, page=page + 1).pack(),
            )
        )
    if nav_row:
        builder.row(*nav_row)

    builder.row(
        InlineKeyboardButton(text="⬅️ Back to Product", callback_data=AdminCB(section="products", action="view", id=product_id).pack()),
        home_button(),
    )
    return builder.as_markup()

def admin_stock_item_view(item: StockItem) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🗑 Delete Item",
            callback_data=AdminCB(section="stock", action="delete", id=item.id).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Back to Stock List", callback_data=AdminCB(section="stock", action="list", id=item.product_id).pack()),
        home_button(),
    )
    return builder.as_markup()


def admin_pick_category(categories: Sequence[Category]) -> InlineKeyboardMarkup:
    """Used when creating a product: choose the destination category."""
    builder = InlineKeyboardBuilder()
    for cat in categories:
        tag = "🎁" if cat.is_points_shop else "🛍"
        builder.row(
            InlineKeyboardButton(
                text=f"{tag} {cat.name}",
                callback_data=AdminCB(
                    section="products", action="new_in", id=cat.id
                ).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(text="⬅️ Products", callback_data=AdminCB(section="products").pack()),
        home_button(),
    )
    return builder.as_markup()


# --------------------------------------------------------------------------- #
# Deposits
# --------------------------------------------------------------------------- #
def admin_deposits(deposits: Sequence[Deposit]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for d in deposits:
        builder.row(
            InlineKeyboardButton(
                text=f"#{d.id} · {d.status.value} · {d.amount_cents / 100:.2f}",
                callback_data=AdminCB(section="deposits", action="view", id=d.id).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(text="⬅️ Admin", callback_data=AdminCB(section="home").pack()),
        home_button(),
    )
    return builder.as_markup()


def admin_deposit_view(deposit: Deposit) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    # Approve/reject only make sense while pending.
    if deposit.status.value == "pending":
        builder.row(
            InlineKeyboardButton(
                text="✅ Approve",
                callback_data=AdminCB(section="deposits", action="approve", id=deposit.id).pack(),
            ),
            InlineKeyboardButton(
                text="❌ Reject",
                callback_data=AdminCB(section="deposits", action="reject", id=deposit.id).pack(),
            ),
        )
    builder.row(
        InlineKeyboardButton(text="⬅️ Deposits", callback_data=AdminCB(section="deposits").pack()),
        home_button(),
    )
    return builder.as_markup()


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #
def admin_users(users: Sequence[User], page: int, has_next: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🔍 Search User",
            callback_data=AdminCB(section="users", action="search").pack(),
        )
    )
    for u in users:
        display_name = u.full_name or (f"@{u.username}" if u.username else str(u.id))
        builder.row(
            InlineKeyboardButton(
                text=f"👤 {display_name} · bal {u.balance:.2f} · {u.points}pts",
                callback_data=AdminCB(section="users", action="view", id=u.id).pack(),
            )
        )
    nav_row = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(
                text="⬅️ Prev",
                callback_data=AdminCB(section="users", action="page", page=page - 1).pack(),
            )
        )
    if has_next:
        nav_row.append(
            InlineKeyboardButton(
                text="Next ➡️",
                callback_data=AdminCB(section="users", action="page", page=page + 1).pack(),
            )
        )
    if nav_row:
        builder.row(*nav_row)
    builder.row(
        InlineKeyboardButton(text="⬅️ Admin", callback_data=AdminCB(section="home").pack()),
        home_button(),
    )
    return builder.as_markup()


def admin_user_view(user: User) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="💰 Set Balance",
            callback_data=AdminCB(section="users", action="set_balance", id=user.id).pack(),
        ),
        InlineKeyboardButton(
            text="🎯 Set Points",
            callback_data=AdminCB(section="users", action="set_points", id=user.id).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="➕ Add Balance",
            callback_data=AdminCB(section="users", action="add_balance", id=user.id).pack(),
        ),
        InlineKeyboardButton(
            text="➕ Add Points",
            callback_data=AdminCB(section="users", action="add_points", id=user.id).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=("✅ Unban" if user.is_banned else "🚫 Ban"),
            callback_data=AdminCB(section="users", action="toggle_ban", id=user.id).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Users", callback_data=AdminCB(section="users").pack()),
        home_button(),
    )
    return builder.as_markup()


# --------------------------------------------------------------------------- #
# Broadcast
# --------------------------------------------------------------------------- #
def admin_broadcast_targets() -> InlineKeyboardMarkup:
    """Pick where an announcement should be sent."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📢 Channel",
            callback_data=AdminCB(section="broadcast", action="to", id=0).pack(),
        ),
        InlineKeyboardButton(
            text="👥 Group",
            callback_data=AdminCB(section="broadcast", action="to", id=1).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🤖 All Bot Users",
            callback_data=AdminCB(section="broadcast", action="to", id=2).pack(),
        ),
        InlineKeyboardButton(
            text="📢👥🤖 ALL Targets",
            callback_data=AdminCB(section="broadcast", action="to", id=3).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Admin", callback_data=AdminCB(section="home").pack()),
        home_button(),
    )
    return builder.as_markup()


def admin_broadcast_confirm() -> InlineKeyboardMarkup:
    """Confirm or cancel sending the previewed announcement."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Send",
            callback_data=AdminCB(section="broadcast", action="send").pack(),
        ),
        InlineKeyboardButton(
            text="❌ Cancel",
            callback_data=AdminCB(section="broadcast").pack(),
        ),
    )
    return builder.as_markup()


def admin_stats_back() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⬅️ Admin", callback_data=AdminCB(section="home").pack()),
        home_button(),
    )
    return builder.as_markup()


def admin_orders_back() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⬅️ Admin", callback_data=AdminCB(section="home").pack()),
        home_button(),
    )
    return builder.as_markup()
