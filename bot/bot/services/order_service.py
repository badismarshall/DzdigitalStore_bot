"""
Purchase logic for both the money shop and the points shop.

Both flows are atomic: stock is only deducted if payment succeeds, and payment
is only taken if stock is available. Everything commits together so a crash
mid-purchase cannot leave the DB half-updated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Order, OrderStatus, PaymentMethod, Product, User
from . import catalog_service


class PurchaseError(Exception):
    """Raised when a purchase cannot be completed (validation/funds/stock)."""


@dataclass
class PurchaseResult:
    order: Order
    delivered_content: Optional[str]
    stock_depleted: bool  # True if this sale brought stock to zero


async def purchase_with_balance(
    session: AsyncSession, user: User, product: Product
) -> PurchaseResult:
    """Buy a product using the user's money balance."""
    if product.hidden:
        raise PurchaseError("This product is currently unavailable.")
    if product.quantity <= 0:
        raise PurchaseError("This product is out of stock.")
    if user.balance_cents < product.price_cents:
        raise PurchaseError("Insufficient balance. Please make a deposit first.")

    # Deduct stock (consumes a StockItem if present).
    delivered = await catalog_service.sell_one_item(session, product)

    # Take payment.
    user.balance_cents -= product.price_cents

    order = Order(
        user_id=user.id,
        product_id=product.id,
        product_name=product.name,
        amount=product.price_cents,
        method=PaymentMethod.BALANCE,
        status=OrderStatus.COMPLETED,
        delivered_content=delivered,
    )
    session.add(order)

    # Single atomic commit for stock + payment + order.
    await session.commit()

    return PurchaseResult(
        order=order,
        delivered_content=delivered,
        stock_depleted=(product.quantity == 0),
    )


async def purchase_with_points(
    session: AsyncSession, user: User, product: Product
) -> PurchaseResult:
    """Redeem a product from the points shop using referral points."""
    if product.hidden:
        raise PurchaseError("This reward is currently unavailable.")
    if product.points_price <= 0:
        raise PurchaseError("This item is not redeemable with points.")
    if product.quantity <= 0:
        raise PurchaseError("This reward is out of stock.")
    if user.points < product.points_price:
        raise PurchaseError("You don't have enough points for this reward.")

    delivered = await catalog_service.sell_one_item(session, product)

    user.points -= product.points_price

    order = Order(
        user_id=user.id,
        product_id=product.id,
        product_name=product.name,
        amount=product.points_price,
        method=PaymentMethod.POINTS,
        status=OrderStatus.COMPLETED,
        delivered_content=delivered,
    )
    session.add(order)

    await session.commit()

    return PurchaseResult(
        order=order,
        delivered_content=delivered,
        stock_depleted=(product.quantity == 0),
    )


async def list_user_orders(
    session: AsyncSession, user_id: int, limit: int = 10
) -> list[Order]:
    result = await session.execute(
        select(Order)
        .where(Order.user_id == user_id)
        .order_by(desc(Order.created_at))
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_recent_orders(session: AsyncSession, limit: int = 15) -> list[Order]:
    result = await session.execute(
        select(Order).order_by(desc(Order.created_at)).limit(limit)
    )
    return list(result.scalars().all())
