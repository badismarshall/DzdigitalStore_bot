"""
Catalog management: categories, products and per-item stock.

Stock model
-----------
Each Product has a cached `quantity`. Admins add stock either as individual
StockItems (each delivers unique content) using add_stock_items(), or set a
raw quantity via set_quantity() for products that don't deliver unique items.

When a product is sold, sell_one_item() consumes the oldest unsold StockItem
(if any) and decrements quantity, keeping the cache consistent.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Category, Product, StockItem


# --------------------------------------------------------------------------- #
# Categories
# --------------------------------------------------------------------------- #
async def create_category(
    session: AsyncSession, name: str, is_points_shop: bool = False
) -> Category:
    category = Category(name=name.strip(), is_points_shop=is_points_shop)
    session.add(category)
    await session.commit()
    return category


async def get_category(session: AsyncSession, category_id: int) -> Optional[Category]:
    return await session.get(Category, category_id)


async def list_categories(
    session: AsyncSession, is_points_shop: bool, include_hidden: bool = False
) -> List[Category]:
    """List categories for either the money shop or the points shop."""
    stmt = select(Category).where(Category.is_points_shop == is_points_shop)
    if not include_hidden:
        stmt = stmt.where(Category.hidden.is_(False))
    stmt = stmt.order_by(Category.name.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def rename_category(session: AsyncSession, category: Category, name: str) -> Category:
    category.name = name.strip()
    await session.commit()
    return category


async def delete_category(session: AsyncSession, category: Category) -> None:
    await session.delete(category)
    await session.commit()


async def set_category_hidden(
    session: AsyncSession, category: Category, hidden: bool
) -> Category:
    category.hidden = hidden
    await session.commit()
    return category


# --------------------------------------------------------------------------- #
# Products
# --------------------------------------------------------------------------- #
async def _next_public_id(session: AsyncSession) -> str:
    """Generate the next sequential human-facing product id, e.g. NZ-0007."""
    result = await session.execute(select(func.count()).select_from(Product))
    count = int(result.scalar_one())
    return f"NZ-{count + 1:04d}"


async def create_product(
    session: AsyncSession,
    category: Category,
    name: str,
    description: str,
    price_cents: int,
    points_price: int = 0,
    quantity: int = 0,
    icon_emoji: Optional[str] = None,
) -> Product:
    product = Product(
        public_id=await _next_public_id(session),
        category_id=category.id,
        name=name.strip(),
        description=(description or "").strip() or None,
        price_cents=price_cents,
        points_price=points_price,
        quantity=quantity,
        icon_emoji=icon_emoji.strip() if icon_emoji else None,
    )
    session.add(product)
    await session.commit()
    return product


async def get_product(session: AsyncSession, product_id: int) -> Optional[Product]:
    return await session.get(Product, product_id)


async def get_product_by_public_id(
    session: AsyncSession, public_id: str
) -> Optional[Product]:
    result = await session.execute(
        select(Product).where(Product.public_id == public_id.strip())
    )
    return result.scalar_one_or_none()


async def list_products(
    session: AsyncSession, category_id: int, include_hidden: bool = False
) -> List[Product]:
    stmt = select(Product).where(Product.category_id == category_id)
    if not include_hidden:
        stmt = stmt.where(Product.hidden.is_(False))
    stmt = stmt.order_by(Product.created_at.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_random_available_product(session: AsyncSession) -> Optional[Product]:
    """Fetch a random product that is visible, has stock, and belongs to the money shop."""
    stmt = (
        select(Product)
        .join(Category)
        .where(
            Product.hidden.is_(False), 
            Product.quantity > 0,
            Category.is_points_shop.is_(False)
        )
        .order_by(func.random())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def all_products(session: AsyncSession) -> List[Product]:
    result = await session.execute(select(Product).order_by(Product.id.asc()))
    return list(result.scalars().all())


async def update_product_fields(session: AsyncSession, product: Product, **fields) -> Product:
    """Generic field updater for name/description/price_cents/points_price."""
    for key, value in fields.items():
        setattr(product, key, value)
    await session.commit()
    return product


async def set_product_hidden(
    session: AsyncSession, product: Product, hidden: bool
) -> Product:
    product.hidden = hidden
    await session.commit()
    return product


async def delete_product(session: AsyncSession, product: Product) -> None:
    await session.delete(product)
    await session.commit()


# --------------------------------------------------------------------------- #
# Stock
# --------------------------------------------------------------------------- #
async def add_stock_items(
    session: AsyncSession, product: Product, contents: Sequence[str]
) -> int:
    """
    Add individual digital items (one per delivered content string) and bump
    the cached quantity. Returns how many items were added.
    """
    added = 0
    for raw in contents:
        content = raw.strip()
        if not content:
            continue
        session.add(StockItem(product_id=product.id, content=content))
        added += 1
    if added:
        product.quantity += added
        await session.commit()
    return added


async def set_quantity(session: AsyncSession, product: Product, quantity: int) -> Product:
    """
    Directly set the cached quantity (for products without per-item delivery).
    Quantity is clamped to >= 0.
    """
    product.quantity = max(0, quantity)
    await session.commit()
    return product


async def list_unsold_items(session: AsyncSession, product_id: int) -> List[StockItem]:
    """List all unsold stock items for a product."""
    result = await session.execute(
        select(StockItem)
        .where(StockItem.product_id == product_id, StockItem.sold.is_(False))
        .order_by(StockItem.created_at.asc())
    )
    return list(result.scalars().all())


async def delete_stock_item(session: AsyncSession, stock_item: StockItem) -> None:
    """Delete a stock item and decrement the product quantity."""
    product = await get_product(session, stock_item.product_id)
    if product and product.quantity > 0:
        product.quantity -= 1
    await session.delete(stock_item)
    await session.commit()


async def get_stock_item(session: AsyncSession, item_id: int) -> Optional[StockItem]:
    return await session.get(StockItem, item_id)


async def count_unsold_items(session: AsyncSession, product_id: int) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(StockItem)
        .where(StockItem.product_id == product_id, StockItem.sold.is_(False))
    )
    return int(result.scalar_one())


async def sell_one_item(session: AsyncSession, product: Product) -> Optional[str]:
    """
    Consume one unit of stock for a sale.

    If the product has unsold StockItems, the oldest one is marked sold and its
    content is returned for delivery. Otherwise (quantity-only product) we simply
    decrement quantity and return None (no unique content to deliver).

    NOTE: the caller is responsible for committing the surrounding transaction;
    this function flushes but lets the order/payment commit happen atomically.
    """
    # Try to grab a concrete item first.
    result = await session.execute(
        select(StockItem)
        .where(StockItem.product_id == product.id, StockItem.sold.is_(False))
        .order_by(StockItem.created_at.asc())
        .limit(1)
    )
    item = result.scalar_one_or_none()

    if item is not None:
        item.sold = True
        product.quantity = max(0, product.quantity - 1)
        return item.content

    # No per-item stock; fall back to quantity decrement.
    if product.quantity > 0:
        product.quantity = max(0, product.quantity - 1)
        return None

    # Should not happen if callers check availability first.
    raise ValueError("No stock available to sell.")
