"""
Admin panel handlers.

Access control: a small filter ensures only configured admin IDs can use any
admin route. The panel is fully inline-keyboard driven, with FSM flows for any
step that needs free-text input (names, prices, amounts, stock, etc.).

Sections: categories, products, stock, orders, deposits, users.
"""

from __future__ import annotations

from typing import Optional

import os

from aiogram import Bot, F, Router
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import config
from ..keyboards import admin as kb
from ..keyboards.callbacks import AdminCB
from ..keyboards.common import back_keyboard
from ..models import DepositStatus, User
from ..services import (
    analytics_service,
    catalog_service,
    broadcast_service,
    deposit_service,
    notification_service,
    order_service,
    user_service,
)
from ..services.deposit_service import DepositError
from ..services.utils import clean, money, parse_int, parse_money_to_cents
from .states import (
    BroadcastStates,
    CategoryStates,
    DepositReviewStates,
    ProductStates,
    UserAdminStates,
)

router = Router(name="admin")

USERS_PER_PAGE = 8


# --------------------------------------------------------------------------- #
# Admin-only filter
# --------------------------------------------------------------------------- #
class IsAdmin(BaseFilter):
    async def __call__(self, event) -> bool:  # Message or CallbackQuery
        user = getattr(event, "from_user", None)
        return bool(user and config.is_admin(user.id))


# Apply the admin filter to every update this router handles.
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


# --------------------------------------------------------------------------- #
# Admin home
# --------------------------------------------------------------------------- #
async def _render_home(target, session: AsyncSession, edit: bool = True) -> None:
    pending = await deposit_service.count_pending(session)
    total = await user_service.total_users(session)
    text = (
        "🛠 <b>Admin Panel</b>\n\n"
        f"👤 Users: <b>{total}</b>\n"
        f"💵 Pending deposits: <b>{pending}</b>\n\n"
        "Choose a section to manage:"
    )
    markup = kb.admin_home(pending_deposits=pending)
    if edit and isinstance(target, CallbackQuery) and target.message:
        await target.message.edit_text(text, reply_markup=markup)
    elif isinstance(target, Message):
        await target.answer(text, reply_markup=markup)


@router.message(Command("admin"))
async def cmd_admin(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    await _render_home(message, session, edit=False)


@router.callback_query(AdminCB.filter(F.section == "home"))
async def cb_admin_home(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    await state.clear()
    await callback.answer()
    await _render_home(callback, session)


@router.callback_query(AdminCB.filter(F.section == "stats"))
async def cb_admin_stats(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    stats = await analytics_service.get_admin_stats(session)

    revenue = stats.total_revenue_cents / 100
    deposits = stats.total_deposits_cents / 100
    symbol = config.currency_symbol

    text = (
        "📊 <b>Admin Dashboard</b>\n\n"
        "💰 <b>Financials</b>\n"
        f"• Total Revenue: <b>{symbol}{revenue:,.2f}</b>\n"
        f"• Approved Deposits: <b>{symbol}{deposits:,.2f}</b>\n\n"
        "📦 <b>Operations</b>\n"
        f"• Total Orders: <b>{stats.total_orders}</b>\n"
        f"• Orders (Last 24h): <b>{stats.orders_24h}</b>\n\n"
        "👤 <b>Users</b>\n"
        f"• Total Registered: <b>{stats.total_users}</b>\n"
        f"• New (Last 24h): <b>{stats.users_24h}</b>\n\n"
        "🔝 <b>Top Products</b>\n"
    )

    if stats.top_products:
        for name, count in stats.top_products:
            text += f"• {name}: <b>{count} sales</b>\n"
    else:
        text += "<i>No sales data yet.</i>\n"

    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.admin_stats_back())


# ========================================================================== #
# CATEGORIES
# ========================================================================== #
@router.callback_query(AdminCB.filter((F.section == "cats") & (F.action.is_(None))))
async def cats_list(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    money_cats = await catalog_service.list_categories(session, False, include_hidden=True)
    points_cats = await catalog_service.list_categories(session, True, include_hidden=True)
    categories = money_cats + points_cats
    text = (
        "📂 <b>Categories</b>\n\n"
        "🛍 = money shop\n"
        "🎁 = points shop\n\n"
        "👁 = visible\n"
        "🙈 = hidden\n\n"
        "Select a category or create a new one:"
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.admin_categories(categories))


@router.callback_query(AdminCB.filter((F.section == "cats") & (F.action == "new")))
async def cats_new(
    callback: CallbackQuery, callback_data: AdminCB, state: FSMContext
) -> None:
    await callback.answer()
    await state.set_state(CategoryStates.waiting_name)
    await state.update_data(is_points_shop=callback_data.points)
    shop_type = "Points Shop" if callback_data.points else "Money Shop"
    if callback.message:
        await callback.message.edit_text(
            f"➕ <b>New {shop_type} Category</b>\n\nSend the category name:",
            reply_markup=back_keyboard(),
        )


@router.message(CategoryStates.waiting_name)
async def cats_new_save(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer("❌ Name cannot be empty. Try again.")
        return
    data = await state.get_data()
    await catalog_service.create_category(
        session, name=name, is_points_shop=bool(data.get("is_points_shop"))
    )
    await state.clear()
    await message.answer(f"✅ Category <b>{clean(name)}</b> created.")
    await _render_home(message, session, edit=False)


@router.callback_query(AdminCB.filter((F.section == "cats") & (F.action == "view")))
async def cats_view(
    callback: CallbackQuery, callback_data: AdminCB, session: AsyncSession
) -> None:
    await callback.answer()
    category = await catalog_service.get_category(session, callback_data.id)
    if category is None:
        await callback.answer("Category not found.", show_alert=True)
        return
    products = await catalog_service.list_products(session, category.id, include_hidden=True)
    shop_type = "🎁 Points" if category.is_points_shop else "🛍 Money"
    vis = "🙈 Hidden" if category.hidden else "👁 Visible"
    text = (
        f"📂 <b>{clean(category.name)}</b>\n\n"
        f"Type: {shop_type}\n"
        f"Visibility: {vis}\n"
        f"Products: <b>{len(products)}</b>"
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.admin_category_view(category))


@router.callback_query(AdminCB.filter((F.section == "cats") & (F.action == "toggle")))
async def cats_toggle(
    callback: CallbackQuery, callback_data: AdminCB, session: AsyncSession
) -> None:
    category = await catalog_service.get_category(session, callback_data.id)
    if category is None:
        await callback.answer("Category not found.", show_alert=True)
        return
    await catalog_service.set_category_hidden(session, category, not category.hidden)
    await callback.answer("Visibility updated.")
    await cats_view(callback, callback_data, session)


@router.callback_query(AdminCB.filter((F.section == "cats") & (F.action == "rename")))
async def cats_rename(
    callback: CallbackQuery, callback_data: AdminCB, state: FSMContext
) -> None:
    await callback.answer()
    await state.set_state(CategoryStates.waiting_rename)
    await state.update_data(category_id=callback_data.id)
    if callback.message:
        await callback.message.edit_text(
            "✏️ Send the new category name:", reply_markup=back_keyboard()
        )


@router.message(CategoryStates.waiting_rename)
async def cats_rename_save(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer("❌ Name cannot be empty. Try again.")
        return
    data = await state.get_data()
    category = await catalog_service.get_category(session, int(data["category_id"]))
    if category is None:
        await message.answer("Category no longer exists.")
        await state.clear()
        return
    await catalog_service.rename_category(session, category, name)
    await state.clear()
    await message.answer(f"✅ Renamed to <b>{clean(name)}</b>.")
    await _render_home(message, session, edit=False)


@router.callback_query(AdminCB.filter((F.section == "cats") & (F.action == "delete")))
async def cats_delete_confirm(
    callback: CallbackQuery, callback_data: AdminCB, session: AsyncSession
) -> None:
    await callback.answer()
    category = await catalog_service.get_category(session, callback_data.id)
    if category is None:
        await callback.answer("Category not found.", show_alert=True)
        return
    if callback.message:
        await callback.message.edit_text(
            f"⚠️ Delete <b>{clean(category.name)}</b> and ALL its products?\n"
            "This cannot be undone.",
            reply_markup=kb.confirm_keyboard("cats", "delete_yes", category.id),
        )


@router.callback_query(AdminCB.filter((F.section == "cats") & (F.action == "delete_yes")))
async def cats_delete_yes(
    callback: CallbackQuery, callback_data: AdminCB, session: AsyncSession
) -> None:
    category = await catalog_service.get_category(session, callback_data.id)
    if category is None:
        await callback.answer("Already deleted.", show_alert=True)
    else:
        await catalog_service.delete_category(session, category)
        await callback.answer("Category deleted.")
    await cats_list(callback, session)


# ========================================================================== #
# PRODUCTS
# ========================================================================== #
@router.callback_query(AdminCB.filter((F.section == "products") & (F.action.is_(None))))
async def products_list(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    products = await catalog_service.all_products(session)
    text = (
        "📦 <b>Products</b>\n\n"
        "🟢 = available\n"
        "🔴 = hidden/out of stock\n\n"
        "Select a product or create a new one:"
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.admin_products(products))


@router.callback_query(AdminCB.filter((F.section == "products") & (F.action == "new")))
async def products_new_pick_category(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    await callback.answer()
    money_cats = await catalog_service.list_categories(session, False, include_hidden=True)
    points_cats = await catalog_service.list_categories(session, True, include_hidden=True)
    categories = money_cats + points_cats
    if not categories:
        await callback.answer("Create a category first.", show_alert=True)
        return
    if callback.message:
        await callback.message.edit_text(
            "📦 <b>New Product</b>\n\nChoose the destination category:",
            reply_markup=kb.admin_pick_category(categories),
        )


@router.callback_query(AdminCB.filter((F.section == "products") & (F.action == "new_in")))
async def products_new_start(
    callback: CallbackQuery, callback_data: AdminCB, state: FSMContext
) -> None:
    await callback.answer()
    await state.set_state(ProductStates.waiting_name)
    await state.update_data(category_id=callback_data.id)
    if callback.message:
        await callback.message.edit_text(
            "📦 <b>New Product</b>\n\nStep 1/5 — send the product <b>name</b>:",
            reply_markup=back_keyboard(),
        )


@router.message(ProductStates.waiting_name)
async def products_new_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer("❌ Name cannot be empty. Try again.")
        return
    await state.update_data(name=name)
    await state.set_state(ProductStates.waiting_icon)
    await message.answer(
        "Step 2/5 — send an <b>emoji icon</b> for the product (e.g. 🎮, 🔑)\n"
        "(or send <code>-</code> to skip):"
    )

@router.message(ProductStates.waiting_icon)
async def products_new_icon(message: Message, state: FSMContext) -> None:
    icon = None
    if message.text == "-":
        icon = None
    else:
        # Check if the user sent a custom emoji
        if message.entities and message.entities[0].type == "custom_emoji":
            icon = message.entities[0].custom_emoji_id
        else:
            icon = (message.text or "").strip()

    await state.update_data(icon_emoji=icon)
    await state.set_state(ProductStates.waiting_description)
    await message.answer(
        "Step 3/5 — send a <b>description</b> (or send <code>-</code> to skip):"
    )


@router.message(ProductStates.waiting_description)
async def products_new_desc(message: Message, state: FSMContext) -> None:
    desc = (message.text or "").strip()
    if desc == "-":
        desc = ""
    await state.update_data(description=desc)
    await state.set_state(ProductStates.waiting_price)
    await message.answer(
        "Step 4/5 — send the <b>money price</b> "
        f"(e.g. <code>9.99</code>; send <code>0</code> if points-only):"
    )


@router.message(ProductStates.waiting_price)
async def products_new_price(message: Message, state: FSMContext) -> None:
    cents = parse_money_to_cents(message.text or "")
    if cents is None:
        await message.answer("❌ Invalid price. Send a number like <code>9.99</code>.")
        return
    await state.update_data(price_cents=cents)
    await state.set_state(ProductStates.waiting_points_price)
    await message.answer(
        "Step 5/5 — send the <b>points price</b> "
        "(whole number; send <code>0</code> if not redeemable with points):"
    )


@router.message(ProductStates.waiting_points_price)
async def products_new_finish(
    message: Message, session: AsyncSession, state: FSMContext, bot: Bot
) -> None:
    points_price = parse_int(message.text or "", minimum=0)
    if points_price is None:
        await message.answer("❌ Invalid number. Send a whole number like <code>50</code>.")
        return

    data = await state.get_data()
    category = await catalog_service.get_category(session, int(data["category_id"]))
    if category is None:
        await message.answer("Category no longer exists. Aborted.")
        await state.clear()
        return

    product = await catalog_service.create_product(
        session,
        category=category,
        name=data["name"],
        description=data.get("description", ""),
        price_cents=int(data.get("price_cents", 0)),
        points_price=points_price,
        quantity=0,
        icon_emoji=data.get("icon_emoji"),
    )
    await state.clear()
    await message.answer(
        f"✅ Product created!\n\n"
        f"🆔 <code>{product.public_id}</code>\n"
        f"<b>{clean(product.name)}</b>\n\n"
        "Now add stock items or set a quantity from the product screen.",
    )
    # Notify the group that a new product is available.
    await notification_service.notify_product_added(bot, product_name=product.name)
    await _render_home(message, session, edit=False)


async def _render_product_view(
    callback: CallbackQuery, session: AsyncSession, product_id: int
) -> None:
    product = await catalog_service.get_product(session, product_id)
    if product is None:
        await callback.answer("Product not found.", show_alert=True)
        return
    category = await catalog_service.get_category(session, product.category_id)
    cat_name = category.name if category else "—"
    unsold = await catalog_service.count_unsold_items(session, product.id)
    status = "🟢 Available" if product.available else "🔴 Unavailable"
    img_status = "🖼 Set" if product.image_path else "❌ Not set"
    icon_display = product.icon_emoji if product.icon_emoji else "❌ Not set"
    
    text = (
        f"📦 <b>{clean(product.name)}</b>\n"
        f"🆔 <code>{product.public_id}</code>\n\n"
        f"Category: {clean(cat_name)}\n"
        f"💲 Price: <b>{money(product.price_cents)}</b>\n"
        f"🎯 Points: <b>{product.points_price}</b>\n"
        f"📦 Quantity: <b>{product.quantity}</b> (stock items: {unsold})\n"
        f"Visibility: {'🙈 Hidden' if product.hidden else '👁 Visible'}\n"
        f"Emoji Icon: <b>{icon_display}</b>\n"
        f"Image: <b>{img_status}</b>\n"
        f"Status: {status}\n\n"
        f"Description:\n{clean(product.description) if product.description else '—'}"
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.admin_product_view(product))


@router.callback_query(AdminCB.filter((F.section == "products") & (F.action == "view")))
async def products_view(
    callback: CallbackQuery, callback_data: AdminCB, session: AsyncSession
) -> None:
    await callback.answer()
    await _render_product_view(callback, session, callback_data.id)


@router.callback_query(AdminCB.filter((F.section == "products") & (F.action == "toggle")))
async def products_toggle(
    callback: CallbackQuery, callback_data: AdminCB, session: AsyncSession, bot: Bot
) -> None:
    product = await catalog_service.get_product(session, callback_data.id)
    if product is None:
        await callback.answer("Product not found.", show_alert=True)
        return
    new_hidden = not product.hidden
    await catalog_service.set_product_hidden(session, product, new_hidden)
    await callback.answer("Visibility updated.")
    if new_hidden:
        await notification_service.notify_product_hidden(bot, product_name=product.name)
    await _render_product_view(callback, session, product.id)


@router.callback_query(AdminCB.filter((F.section == "products") & (F.action == "delete")))
async def products_delete_confirm(
    callback: CallbackQuery, callback_data: AdminCB, session: AsyncSession
) -> None:
    await callback.answer()
    product = await catalog_service.get_product(session, callback_data.id)
    if product is None:
        await callback.answer("Product not found.", show_alert=True)
        return
    if callback.message:
        await callback.message.edit_text(
            f"⚠️ Delete <b>{clean(product.name)}</b> (<code>{product.public_id}</code>)?\n"
            "This also removes its stock. This cannot be undone.",
            reply_markup=kb.confirm_keyboard("products", "delete_yes", product.id),
        )


@router.callback_query(AdminCB.filter((F.section == "products") & (F.action == "delete_yes")))
async def products_delete_yes(
    callback: CallbackQuery, callback_data: AdminCB, session: AsyncSession
) -> None:
    product = await catalog_service.get_product(session, callback_data.id)
    if product is None:
        await callback.answer("Already deleted.", show_alert=True)
    else:
        await catalog_service.delete_product(session, product)
        await callback.answer("Product deleted.")
    await products_list(callback, session)


# --- Product field edits (FSM) --------------------------------------------- #
async def _start_edit(
    callback: CallbackQuery, callback_data: AdminCB, state: FSMContext,
    fsm_state, prompt: str,
) -> None:
    await callback.answer()
    await state.set_state(fsm_state)
    await state.update_data(product_id=callback_data.id)
    if callback.message:
        await callback.message.edit_text(prompt, reply_markup=back_keyboard())


@router.callback_query(AdminCB.filter((F.section == "products") & (F.action == "edit_name")))
async def edit_name(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext) -> None:
    await _start_edit(callback, callback_data, state, ProductStates.waiting_edit_name,
                      "✏️ Send the new <b>name</b>:")


@router.callback_query(AdminCB.filter((F.section == "products") & (F.action == "edit_icon")))
async def edit_icon(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext) -> None:
    await _start_edit(callback, callback_data, state, ProductStates.waiting_edit_icon,
                      "🎀 Send the new <b>emoji icon</b> (e.g. 🎮, 🔑) (or send <code>-</code> to clear):")


@router.callback_query(AdminCB.filter((F.section == "products") & (F.action == "edit_desc")))
async def edit_desc(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext) -> None:
    await _start_edit(callback, callback_data, state, ProductStates.waiting_edit_desc,
                      "📝 Send the new <b>description</b> (or <code>-</code> to clear):")


@router.callback_query(AdminCB.filter((F.section == "products") & (F.action == "edit_price")))
async def edit_price(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext) -> None:
    await _start_edit(callback, callback_data, state, ProductStates.waiting_edit_price,
                      "💲 Send the new <b>money price</b> (e.g. <code>9.99</code>):")


@router.callback_query(AdminCB.filter((F.section == "products") & (F.action == "edit_points")))
async def edit_points(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext) -> None:
    await _start_edit(callback, callback_data, state, ProductStates.waiting_edit_points,
                      "🎯 Send the new <b>points price</b> (whole number):")


@router.callback_query(AdminCB.filter((F.section == "products") & (F.action == "add_stock")))
async def add_stock_menu(callback: CallbackQuery, callback_data: AdminCB) -> None:
    await callback.answer()
    text = "➕ <b>Add Stock Items</b>\n\nHow would you like to add stock?"
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.admin_add_stock_mode(callback_data.id))


@router.callback_query(AdminCB.filter((F.section == "products") & (F.action == "add_stock_bulk")))
async def add_stock_bulk(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext) -> None:
    await _start_edit(
        callback, callback_data, state, ProductStates.waiting_add_stock_bulk,
        "➕ <b>Bulk Add Stock Items</b>\n\n"
        "Send one item per line. Each line becomes one deliverable unit "
        "(a code/key/account/etc.). Example:\n\n"
        "<code>KEY-AAA-111\nKEY-BBB-222\nKEY-CCC-333</code>",
    )


@router.callback_query(AdminCB.filter((F.section == "products") & (F.action == "add_stock_manual")))
async def add_stock_manual(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext) -> None:
    await _start_edit(
        callback, callback_data, state, ProductStates.waiting_add_stock_manual,
        "➕ <b>Manual Add (Single HTML Block)</b>\n\n"
        "Send the entire content for <b>one single stock item</b>.\n"
        "You can use Telegram HTML formatting (e.g. bold, monospace, links) directly in your message.\n\n"
        "<i>The entire message will be saved as exactly one stock item.</i>",
    )


@router.callback_query(AdminCB.filter((F.section == "products") & (F.action == "set_qty")))
async def set_qty(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext) -> None:
    await _start_edit(
        callback, callback_data, state, ProductStates.waiting_set_qty,
        "🔢 Send the new <b>quantity</b> (whole number). "
        "Use this for products that don't deliver unique items.",
    )


@router.callback_query(AdminCB.filter((F.section == "products") & (F.action == "edit_image")))
async def edit_image(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext) -> None:
    await _start_edit(
        callback, callback_data, state, ProductStates.waiting_edit_image,
        "🖼 <b>Set Product Image</b>\n\n"
        "Send me a <b>Photo</b> or an <b>Image Document</b> (e.g. .ico, .png, .jpg).\n\n"
        "To clear the image, send <code>-</code>."
    )


@router.message(ProductStates.waiting_edit_image, F.photo | F.document | F.text)
async def edit_image_save(
    message: Message, session: AsyncSession, state: FSMContext, bot: Bot
) -> None:
    product = await _get_edit_product(message, session, state)
    if product is None:
        return

    # Handle clearing image
    if message.text == "-":
        if product.image_path and os.path.exists(product.image_path):
            try:
                os.remove(product.image_path)
            except Exception:
                pass
        await catalog_service.update_product_fields(session, product, image_path=None)
        await state.clear()
        await message.answer("✅ Image cleared.")
        await _render_home(message, session, edit=False)
        return

    file_id = None
    ext = ".jpg" # default for photos

    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document:
        if not message.document.mime_type.startswith("image/"):
            await message.answer("❌ That doesn't look like an image document.")
            return
        file_id = message.document.file_id
        ext = os.path.splitext(message.document.file_name)[1] if message.document.file_name else ".png"

    if not file_id:
        await message.answer("❌ Please send a photo, an image document, or <code>-</code> to clear.")
        return

    # Download file
    file = await bot.get_file(file_id)
    save_path = f"data/product_images/prod_{product.id}{ext}"
    
    # Ensure directory exists (redundant but safe)
    os.makedirs("data/product_images", exist_ok=True)
    
    await bot.download_file(file.file_path, save_path)
    
    await catalog_service.update_product_fields(session, product, image_path=save_path)
    await state.clear()
    await message.answer("✅ Product image updated!")
    await _render_home(message, session, edit=False)


async def _get_edit_product(
    message: Message, session: AsyncSession, state: FSMContext
) -> Optional[object]:
    data = await state.get_data()
    product = await catalog_service.get_product(session, int(data["product_id"]))
    if product is None:
        await message.answer("Product no longer exists. Aborted.")
        await state.clear()
    return product


@router.message(ProductStates.waiting_edit_name)
async def edit_name_save(message: Message, session: AsyncSession, state: FSMContext) -> None:
    product = await _get_edit_product(message, session, state)
    if product is None:
        return
    name = (message.text or "").strip()
    if not name:
        await message.answer("❌ Name cannot be empty.")
        return
    await catalog_service.update_product_fields(session, product, name=name)
    await state.clear()
    await message.answer(f"✅ Name updated to <b>{clean(name)}</b>.")
    await _render_home(message, session, edit=False)


@router.message(ProductStates.waiting_edit_icon)
async def edit_icon_save(message: Message, session: AsyncSession, state: FSMContext) -> None:
    product = await _get_edit_product(message, session, state)
    if product is None:
        return
    
    icon = None
    if message.text == "-":
        icon = None
    else:
        # Check if the user sent a custom emoji
        if message.entities and message.entities[0].type == "custom_emoji":
            icon = message.entities[0].custom_emoji_id
        else:
            icon = (message.text or "").strip()

    await catalog_service.update_product_fields(session, product, icon_emoji=icon)
    await state.clear()
    if icon:
        await message.answer("✅ Icon updated.")
    else:
        await message.answer("✅ Icon cleared.")
    await _render_home(message, session, edit=False)


@router.message(ProductStates.waiting_edit_desc)
async def edit_desc_save(message: Message, session: AsyncSession, state: FSMContext) -> None:
    product = await _get_edit_product(message, session, state)
    if product is None:
        return
    desc = (message.text or "").strip()
    desc = None if desc == "-" else desc
    await catalog_service.update_product_fields(session, product, description=desc)
    await state.clear()
    await message.answer("✅ Description updated.")
    await _render_home(message, session, edit=False)


@router.message(ProductStates.waiting_edit_price)
async def edit_price_save(message: Message, session: AsyncSession, state: FSMContext) -> None:
    product = await _get_edit_product(message, session, state)
    if product is None:
        return
    cents = parse_money_to_cents(message.text or "")
    if cents is None:
        await message.answer("❌ Invalid price. Send a number like <code>9.99</code>.")
        return
    await catalog_service.update_product_fields(session, product, price_cents=cents)
    await state.clear()
    await message.answer(f"✅ Price updated to <b>{money(cents)}</b>.")
    await _render_home(message, session, edit=False)


@router.message(ProductStates.waiting_edit_points)
async def edit_points_save(message: Message, session: AsyncSession, state: FSMContext) -> None:
    product = await _get_edit_product(message, session, state)
    if product is None:
        return
    points = parse_int(message.text or "", minimum=0)
    if points is None:
        await message.answer("❌ Invalid number.")
        return
    await catalog_service.update_product_fields(session, product, points_price=points)
    await state.clear()
    await message.answer(f"✅ Points price updated to <b>{points}</b>.")
    await _render_home(message, session, edit=False)


@router.message(ProductStates.waiting_add_stock_bulk)
async def add_stock_bulk_save(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    product = await _get_edit_product(message, session, state)
    if product is None:
        return
    lines = (message.text or "").splitlines()
    added = await catalog_service.add_stock_items(session, product, lines)
    await state.clear()
    if added == 0:
        await message.answer("⚠️ No valid items found. Nothing was added.")
    else:
        await message.answer(
            f"✅ Added <b>{added}</b> stock item(s). "
            f"New quantity: <b>{product.quantity}</b>."
        )
    await _render_home(message, session, edit=False)


@router.message(ProductStates.waiting_add_stock_manual)
async def add_stock_manual_save(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    product = await _get_edit_product(message, session, state)
    if product is None:
        return
    
    # Use html_text to preserve the Telegram HTML formatting the admin sent
    content = (message.html_text or "").strip()
    if not content or content == "-":
        await message.answer("⚠️ Empty content. Nothing was added.")
        await state.clear()
        await _render_home(message, session, edit=False)
        return

    # Add the single HTML block as one stock item
    added = await catalog_service.add_stock_items(session, product, [content])
    await state.clear()
    if added == 0:
        await message.answer("⚠️ Nothing was added.")
    else:
        await message.answer(
            f"✅ Added <b>1</b> stock item (Manual HTML Mode). "
            f"New quantity: <b>{product.quantity}</b>."
        )
    await _render_home(message, session, edit=False)


@router.message(ProductStates.waiting_set_qty)
async def set_qty_save(message: Message, session: AsyncSession, state: FSMContext) -> None:
    product = await _get_edit_product(message, session, state)
    if product is None:
        return
    qty = parse_int(message.text or "", minimum=0)
    if qty is None:
        await message.answer("❌ Invalid number.")
        return
    await catalog_service.set_quantity(session, product, qty)
    await state.clear()
    await message.answer(f"✅ Quantity set to <b>{qty}</b>.")
    await _render_home(message, session, edit=False)


# ========================================================================== #
# STOCK ITEMS
# ========================================================================== #

ITEMS_PER_PAGE = 10

@router.callback_query(AdminCB.filter((F.section == "stock") & (F.action == "list")))
async def stock_items_list(callback: CallbackQuery, callback_data: AdminCB, session: AsyncSession) -> None:
    await callback.answer()
    page = callback_data.page
    product_id = callback_data.id
    
    product = await catalog_service.get_product(session, product_id)
    if product is None:
        await callback.answer("Product not found.", show_alert=True)
        return

    items = await catalog_service.list_unsold_items(session, product_id)
    
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_items = items[start_idx:end_idx]
    has_next = len(items) > end_idx

    text = f"📦 <b>Stock Items for {clean(product.name)}</b>\n\nPage {page + 1}"
    if not items:
        text = f"📦 <b>Stock Items for {clean(product.name)}</b>\n\nNo unsold items."

    if callback.message:
        await callback.message.edit_text(
            text, reply_markup=kb.admin_stock_items(product_id, page_items, page, has_next)
        )


@router.callback_query(AdminCB.filter((F.section == "stock") & (F.action == "page")))
async def stock_items_page(callback: CallbackQuery, callback_data: AdminCB, session: AsyncSession) -> None:
    await stock_items_list(callback, callback_data, session)


@router.callback_query(AdminCB.filter((F.section == "stock") & (F.action == "view")))
async def stock_item_view(callback: CallbackQuery, callback_data: AdminCB, session: AsyncSession) -> None:
    await callback.answer()
    item = await catalog_service.get_stock_item(session, callback_data.id)
    if item is None:
        await callback.answer("Item not found.", show_alert=True)
        return
        
    status = "🔴 Sold" if item.sold else "🟢 Available"
    text = (
        f"📦 <b>Stock Item #{item.id}</b>\n"
        f"Status: {status}\n\n"
        f"Content:\n<pre>{clean(item.content)}</pre>"
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.admin_stock_item_view(item))


@router.callback_query(AdminCB.filter((F.section == "stock") & (F.action == "delete")))
async def stock_item_delete(callback: CallbackQuery, callback_data: AdminCB, session: AsyncSession) -> None:
    item = await catalog_service.get_stock_item(session, callback_data.id)
    if item is None:
        await callback.answer("Already deleted.", show_alert=True)
        return
        
    product_id = item.product_id
    await catalog_service.delete_stock_item(session, item)
    await callback.answer("Item deleted.")
    
    # Refresh list
    callback_data.id = product_id
    callback_data.page = 0
    await stock_items_list(callback, callback_data, session)


# ========================================================================== #
# ORDERS
# ========================================================================== #
@router.callback_query(AdminCB.filter((F.section == "orders") & (F.action.is_(None))))
async def orders_list(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    orders = await order_service.list_recent_orders(session, limit=15)
    if not orders:
        text = "🧾 <b>Recent Orders</b>\n\nNo orders yet."
    else:
        lines = ["🧾 <b>Recent Orders</b>\n"]
        for o in orders:
            price = f"{o.amount} pts" if o.method.value == "points" else money(o.amount)
            # Note: order list is admin-only; user id shown here for support.
            lines.append(
                f"• #{o.id} · {clean(o.product_name)} · {price} · {o.status.value}"
            )
        text = "\n".join(lines)
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.admin_orders_back())


# ========================================================================== #
# DEPOSITS
# ========================================================================== #
@router.callback_query(AdminCB.filter((F.section == "deposits") & (F.action.is_(None))))
async def deposits_list(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    # Show pending first (most actionable), then recent others.
    pending = await deposit_service.list_deposits(session, DepositStatus.PENDING, limit=15)
    if pending:
        deposits = pending
        title = "💵 <b>Pending Deposits</b>"
    else:
        deposits = await deposit_service.list_deposits(session, None, limit=15)
        title = "💵 <b>Recent Deposits</b> (none pending)"
    text = f"{title}\n\nSelect a deposit to review:"
    if not deposits:
        text = "💵 <b>Deposits</b>\n\nNo deposits yet."
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.admin_deposits(deposits))


async def _render_deposit_view(
    callback: CallbackQuery, session: AsyncSession, deposit_id: int
) -> None:
    deposit = await deposit_service.get_deposit(session, deposit_id)
    if deposit is None:
        await callback.answer("Deposit not found.", show_alert=True)
        return
        
    user = await session.get(User, deposit.user_id)
    display_name = f"@{user.username}" if user and user.username else (user.full_name if user and user.full_name else f"ID: {deposit.user_id}")
    
    text = (
        f"💵 <b>Deposit #{deposit.id}</b>\n\n"
        f"User: <b>{display_name}</b>\n"
        f"Network: <b>{clean(deposit.network or '—')}</b>\n"
        f"Stated amount: <b>{money(deposit.amount_cents)}</b>\n"
        f"Status: <b>{deposit.status.value}</b>"
    )
    if deposit.admin_note:
        text += f"\n\nNote: {clean(deposit.admin_note)}"
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.admin_deposit_view(deposit))


@router.callback_query(AdminCB.filter((F.section == "deposits") & (F.action == "view")))
async def deposits_view(
    callback: CallbackQuery, callback_data: AdminCB, session: AsyncSession
) -> None:
    await callback.answer()
    await _render_deposit_view(callback, session, callback_data.id)


@router.callback_query(AdminCB.filter((F.section == "deposits") & (F.action == "approve")))
async def deposits_approve_start(
    callback: CallbackQuery, callback_data: AdminCB, session: AsyncSession, state: FSMContext
) -> None:
    deposit = await deposit_service.get_deposit(session, callback_data.id)
    if deposit is None or deposit.status != DepositStatus.PENDING:
        await callback.answer("This deposit can't be approved.", show_alert=True)
        return
    await callback.answer()
    await state.set_state(DepositReviewStates.waiting_approve_amount)
    await state.update_data(deposit_id=deposit.id)
    if callback.message:
        await callback.message.edit_text(
            f"✅ <b>Approve Deposit #{deposit.id}</b>\n\n"
            f"Stated amount was <b>{money(deposit.amount_cents)}</b>.\n"
            "Send the <b>verified amount</b> to credit "
            f"(e.g. <code>25</code>), or send <code>ok</code> to credit the "
            "stated amount.",
            reply_markup=back_keyboard(),
        )


@router.message(DepositReviewStates.waiting_approve_amount)
async def deposits_approve_finish(
    message: Message, session: AsyncSession, state: FSMContext, bot: Bot
) -> None:
    data = await state.get_data()
    deposit = await deposit_service.get_deposit(session, int(data["deposit_id"]))
    if deposit is None:
        await message.answer("Deposit no longer exists.")
        await state.clear()
        return

    raw = (message.text or "").strip().lower()
    amount_cents: Optional[int]
    if raw == "ok":
        amount_cents = None  # use stored stated amount
    else:
        amount_cents = parse_money_to_cents(message.text or "")
        if amount_cents is None or amount_cents == 0:
            await message.answer(
                "❌ Invalid amount. Send a number like <code>25</code>, or "
                "<code>ok</code> to use the stated amount."
            )
            return

    try:
        deposit = await deposit_service.approve_deposit(
            session, deposit, amount_cents=amount_cents, note="Approved via admin panel"
        )
    except DepositError as exc:
        await message.answer(f"⚠️ {exc}")
        await state.clear()
        return

    await state.clear()
    await message.answer(
        f"✅ Deposit #{deposit.id} approved. "
        f"Credited <b>{money(deposit.amount_cents)}</b> to user "
        f"<code>{deposit.user_id}</code>."
    )

    # Tell the user privately their deposit was approved.
    try:
        await bot.send_message(
            chat_id=deposit.user_id,
            text=(
                "✅ <b>Deposit Approved</b>\n\n"
                f"Your deposit (ref #{deposit.id}) of "
                f"<b>{money(deposit.amount_cents)}</b> has been credited. "
                "Happy shopping! 🛍"
            ),
        )
    except Exception:  # noqa: BLE001
        pass

    await _render_home(message, session, edit=False)


@router.callback_query(AdminCB.filter((F.section == "deposits") & (F.action == "reject")))
async def deposits_reject_start(
    callback: CallbackQuery, callback_data: AdminCB, session: AsyncSession, state: FSMContext
) -> None:
    deposit = await deposit_service.get_deposit(session, callback_data.id)
    if deposit is None or deposit.status != DepositStatus.PENDING:
        await callback.answer("This deposit can't be rejected.", show_alert=True)
        return
    await callback.answer()
    await state.set_state(DepositReviewStates.waiting_reject_note)
    await state.update_data(deposit_id=deposit.id)
    if callback.message:
        await callback.message.edit_text(
            f"❌ <b>Reject Deposit #{deposit.id}</b>\n\n"
            "Send a short reason (or <code>-</code> for none):",
            reply_markup=back_keyboard(),
        )


@router.message(DepositReviewStates.waiting_reject_note)
async def deposits_reject_finish(
    message: Message, session: AsyncSession, state: FSMContext, bot: Bot
) -> None:
    data = await state.get_data()
    deposit = await deposit_service.get_deposit(session, int(data["deposit_id"]))
    if deposit is None:
        await message.answer("Deposit no longer exists.")
        await state.clear()
        return
    note = (message.text or "").strip()
    note = None if note == "-" else note
    try:
        deposit = await deposit_service.reject_deposit(session, deposit, note=note)
    except DepositError as exc:
        await message.answer(f"⚠️ {exc}")
        await state.clear()
        return

    await state.clear()
    await message.answer(f"❌ Deposit #{deposit.id} rejected. No balance change.")

    try:
        reason = f"\nReason: {clean(note)}" if note else ""
        await bot.send_message(
            chat_id=deposit.user_id,
            text=(
                "❌ <b>Deposit Rejected</b>\n\n"
                f"Your deposit (ref #{deposit.id}) was not approved.{reason}\n"
                "If you believe this is a mistake, please contact an admin."
            ),
        )
    except Exception:  # noqa: BLE001
        pass

    await _render_home(message, session, edit=False)


# ========================================================================== #
# USERS
# ========================================================================== #
async def _render_users_page(
    callback: CallbackQuery, session: AsyncSession, page: int
) -> None:
    offset = page * USERS_PER_PAGE
    users = await user_service.list_users(session, limit=USERS_PER_PAGE + 1, offset=offset)
    has_next = len(users) > USERS_PER_PAGE
    users = users[:USERS_PER_PAGE]
    text = (
        "👤 <b>Users</b>\n\n"
        "Tap a user to manage balance, points, or ban status."
    )
    if callback.message:
        await callback.message.edit_text(
            text, reply_markup=kb.admin_users(users, page=page, has_next=has_next)
        )


@router.callback_query(AdminCB.filter((F.section == "users") & (F.action.is_(None))))
async def users_list(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    await _render_users_page(callback, session, page=0)


@router.callback_query(AdminCB.filter((F.section == "users") & (F.action == "page")))
async def users_page(
    callback: CallbackQuery, callback_data: AdminCB, session: AsyncSession
) -> None:
    await callback.answer()
    await _render_users_page(callback, session, page=callback_data.page)


@router.callback_query(AdminCB.filter((F.section == "users") & (F.action == "search")))
async def users_search_start(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    await callback.answer()
    await state.set_state(UserAdminStates.waiting_search)
    if callback.message:
        await callback.message.edit_text(
            "🔍 <b>Search User</b>\n\n"
            "Send the user's <b>Telegram ID</b> or <b>username</b> (with or without @):",
            reply_markup=back_keyboard(),
        )


@router.message(UserAdminStates.waiting_search)
async def users_search_finish(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    query = (message.text or "").strip()
    if not query:
        return

    target = await user_service.find_user(session, query)
    if target is None:
        await message.answer(
            f"❌ User not found for query: <code>{clean(query)}</code>\n"
            "Try a numeric ID or a exact username.",
            reply_markup=back_keyboard(),
        )
        return

    await state.clear()
    await _render_user_view(message, session, target.id, edit=False)


async def _render_user_view(
    event: CallbackQuery | Message, session: AsyncSession, user_id: int, edit: bool = True
) -> None:
    target = await user_service.get_user(session, user_id)
    if target is None:
        if isinstance(event, CallbackQuery):
            await event.answer("User not found.", show_alert=True)
        else:
            await event.answer("User not found.")
        return
    referrals = await user_service.count_referrals(session, target.id)
    name_info = f"<b>{clean(target.full_name)}</b>" if target.full_name else f"User {target.id}"
    username_text = f" (@{target.username})" if target.username else ""
    text = (
        f"👤 {name_info}{username_text}\n"
        f"<code>ID: {target.id}</code>\n\n"
        f"💰 Balance: <b>{money(target.balance_cents)}</b>\n"
        f"🎯 Points: <b>{target.points}</b>\n"
        f"👥 Referrals: <b>{referrals}</b>\n"
        f"Verified: {'✅' if target.verified else '❌'}\n"
        f"Banned: {'🚫 yes' if target.is_banned else 'no'}"
    )
    markup = kb.admin_user_view(target)
    if edit and isinstance(event, CallbackQuery) and event.message:
        await event.message.edit_text(text, reply_markup=markup)
    else:
        await event.answer(text, reply_markup=markup)


@router.callback_query(AdminCB.filter((F.section == "users") & (F.action == "view")))
async def users_view(
    callback: CallbackQuery, callback_data: AdminCB, session: AsyncSession
) -> None:
    await callback.answer()
    await _render_user_view(callback, session, callback_data.id)


@router.callback_query(AdminCB.filter((F.section == "users") & (F.action == "toggle_ban")))
async def users_toggle_ban(
    callback: CallbackQuery, callback_data: AdminCB, session: AsyncSession
) -> None:
    target = await user_service.get_user(session, callback_data.id)
    if target is None:
        await callback.answer("User not found.", show_alert=True)
        return
    await user_service.set_banned(session, target, not target.is_banned)
    await callback.answer("Updated.")
    await _render_user_view(callback, session, target.id)


async def _start_user_edit(
    callback: CallbackQuery, callback_data: AdminCB, state: FSMContext,
    fsm_state, prompt: str,
) -> None:
    await callback.answer()
    await state.set_state(fsm_state)
    await state.update_data(user_id=callback_data.id)
    if callback.message:
        await callback.message.edit_text(prompt, reply_markup=back_keyboard())


@router.callback_query(AdminCB.filter((F.section == "users") & (F.action == "set_balance")))
async def user_set_balance(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext) -> None:
    await _start_user_edit(callback, callback_data, state, UserAdminStates.waiting_set_balance,
                           "💰 Send the new <b>balance</b> (e.g. <code>50</code>):")


@router.callback_query(AdminCB.filter((F.section == "users") & (F.action == "add_balance")))
async def user_add_balance(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext) -> None:
    await _start_user_edit(callback, callback_data, state, UserAdminStates.waiting_add_balance,
                           "➕ Send the amount to <b>add</b> to balance (e.g. <code>10</code>):")


@router.callback_query(AdminCB.filter((F.section == "users") & (F.action == "set_points")))
async def user_set_points(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext) -> None:
    await _start_user_edit(callback, callback_data, state, UserAdminStates.waiting_set_points,
                           "🎯 Send the new <b>points</b> (whole number):")


@router.callback_query(AdminCB.filter((F.section == "users") & (F.action == "add_points")))
async def user_add_points(callback: CallbackQuery, callback_data: AdminCB, state: FSMContext) -> None:
    await _start_user_edit(callback, callback_data, state, UserAdminStates.waiting_add_points,
                           "➕ Send the points to <b>add</b> (whole number):")


async def _get_target_user(message: Message, session: AsyncSession, state: FSMContext):
    data = await state.get_data()
    target = await user_service.get_user(session, int(data["user_id"]))
    if target is None:
        await message.answer("User no longer exists. Aborted.")
        await state.clear()
    return target


@router.message(UserAdminStates.waiting_set_balance)
async def user_set_balance_save(message: Message, session: AsyncSession, state: FSMContext) -> None:
    target = await _get_target_user(message, session, state)
    if target is None:
        return
    cents = parse_money_to_cents(message.text or "")
    if cents is None:
        await message.answer("❌ Invalid amount.")
        return
    await user_service.set_balance(session, target, cents)
    await state.clear()
    await message.answer(f"✅ Balance set to <b>{money(cents)}</b> for user {target.id}.")
    await _render_home(message, session, edit=False)


@router.message(UserAdminStates.waiting_add_balance)
async def user_add_balance_save(message: Message, session: AsyncSession, state: FSMContext) -> None:
    target = await _get_target_user(message, session, state)
    if target is None:
        return
    cents = parse_money_to_cents(message.text or "")
    if cents is None:
        await message.answer("❌ Invalid amount.")
        return
    await user_service.adjust_balance(session, target, cents)
    await state.clear()
    await message.answer(
        f"✅ Added {money(cents)}. New balance: <b>{money(target.balance_cents)}</b>."
    )
    await _render_home(message, session, edit=False)


@router.message(UserAdminStates.waiting_set_points)
async def user_set_points_save(message: Message, session: AsyncSession, state: FSMContext) -> None:
    target = await _get_target_user(message, session, state)
    if target is None:
        return
    points = parse_int(message.text or "", minimum=0)
    if points is None:
        await message.answer("❌ Invalid number.")
        return
    await user_service.set_points(session, target, points)
    await state.clear()
    await message.answer(f"✅ Points set to <b>{points}</b> for user {target.id}.")
    await _render_home(message, session, edit=False)


@router.message(UserAdminStates.waiting_add_points)
async def user_add_points_save(message: Message, session: AsyncSession, state: FSMContext) -> None:
    target = await _get_target_user(message, session, state)
    if target is None:
        return
    points = parse_int(message.text or "", minimum=0)
    if points is None:
        await message.answer("❌ Invalid number.")
        return
    await user_service.adjust_points(session, target, points)
    await state.clear()
    await message.answer(f"✅ Added {points} points. New total: <b>{target.points}</b>.")
    await _render_home(message, session, edit=False)


# ========================================================================== #
# BROADCAST
# ========================================================================== #
# Target codes packed into AdminCB.id by the destination picker keyboard.
_BROADCAST_TARGETS = {0: "channel", 1: "group", 2: "users", 3: "all"}
_BROADCAST_LABELS = {
    "channel": "📢 the Channel",
    "group": "👥 the Group",
    "users": "🤖 all Bot Users",
    "all": "📢👥🤖 ALL Targets",
}


@router.callback_query(AdminCB.filter((F.section == "broadcast") & (F.action.is_(None))))
async def broadcast_home(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    await callback.answer()
    await state.clear()
    text = (
        "📣 <b>Broadcast</b>\n\n"
        "Send an announcement to one of the destinations below.\n"
        "Where would you like to post?"
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.admin_broadcast_targets())


@router.callback_query(AdminCB.filter((F.section == "broadcast") & (F.action == "to")))
async def broadcast_pick_target(
    callback: CallbackQuery, callback_data: AdminCB, state: FSMContext
) -> None:
    target = _BROADCAST_TARGETS.get(callback_data.id)
    if target is None:
        await callback.answer("Unknown destination.", show_alert=True)
        return
    await callback.answer()
    await state.set_state(BroadcastStates.waiting_message)
    await state.update_data(broadcast_target=target)
    label = _BROADCAST_LABELS[target]
    if callback.message:
        await callback.message.edit_text(
            f"📣 <b>Broadcast to {label}</b>\n\n"
            "Send the message you want to post. HTML formatting "
            "(<b>bold</b>, <i>italic</i>, links) is supported.",
            reply_markup=back_keyboard(),
        )


@router.message(BroadcastStates.waiting_message)
async def broadcast_capture_message(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    text = (message.html_text or message.text or "").strip()
    if not text:
        await message.answer("❌ The message can't be empty. Send some text.")
        return

    data = await state.get_data()
    target = data.get("broadcast_target")
    if target not in _BROADCAST_LABELS:
        await message.answer("Something went wrong. Start again from the panel.")
        await state.clear()
        return

    await state.update_data(broadcast_text=text)
    await state.set_state(BroadcastStates.waiting_confirm)

    label = _BROADCAST_LABELS[target]
    await message.answer(
        f"📣 <b>Preview — to {label}</b>\n"
        "───────────────\n"
        f"{text}\n"
        "───────────────\n\n"
        "Send this announcement?",
        reply_markup=kb.admin_broadcast_confirm(),
        disable_web_page_preview=True,
    )


@router.callback_query(
    AdminCB.filter((F.section == "broadcast") & (F.action == "send")),
    BroadcastStates.waiting_confirm,
)
async def broadcast_send(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext, bot: Bot
) -> None:
    data = await state.get_data()
    target = data.get("broadcast_target")
    text = data.get("broadcast_text")
    await state.clear()

    if not text or target not in _BROADCAST_LABELS:
        await callback.answer("Nothing to send.", show_alert=True)
        return

    await callback.answer("Sending…")
    if callback.message:
        await callback.message.edit_text("📣 Sending your announcement…")

    if target == "channel":
        result = await broadcast_service.send_to_channel(bot, text)
    elif target == "group":
        result = await broadcast_service.send_to_group(bot, text)
    elif target == "users":
        user_ids = await user_service.all_user_ids(session)
        result = await broadcast_service.send_to_users(bot, user_ids, text)
    else:  # all
        user_ids = await user_service.all_user_ids(session)
        result = await broadcast_service.send_to_all(bot, user_ids, text)

    label = _BROADCAST_LABELS[target]
    if target in ("users", "all"):
        summary = (
            f"📣 <b>Broadcast complete</b> — {label}\n\n"
            f"✅ Delivered: <b>{result.delivered}</b>\n"
            f"⚠️ Failed: <b>{result.failed}</b>\n\n"
            "(Failures are usually users who blocked the bot.)"
        )
    elif result.ok:
        summary = f"✅ Announcement posted to {label}."
    else:
        summary = (
            f"❌ Couldn't post to {label}.\n"
            "Make sure the bot is an admin there.\n"
            f"<code>{clean(result.error or 'unknown error')}</code>"
        )

    if callback.message:
        await callback.message.edit_text(summary, reply_markup=back_keyboard())
