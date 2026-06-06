"""
Analytics service for NAZZSHOP.
Provides aggregated metrics for the admin dashboard.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import List, Tuple

from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Order, Deposit, User, Product, DepositStatus, OrderStatus, PaymentMethod


@dataclass
class AnalyticsStats:
    total_revenue_cents: int
    total_deposits_cents: int
    total_orders: int
    orders_24h: int
    total_users: int
    users_24h: int
    top_products: List[Tuple[str, int]]  # (name, count)


async def get_admin_stats(session: AsyncSession) -> AnalyticsStats:
    """Fetch aggregated metrics for the admin dashboard."""
    now = dt.datetime.now(dt.timezone.utc)
    last_24h = now - dt.timedelta(hours=24)

    # 1. Financial Metrics
    revenue_q = select(func.sum(Order.amount)).where(
        Order.method == PaymentMethod.BALANCE,
        Order.status == OrderStatus.COMPLETED
    )
    revenue_res = await session.execute(revenue_q)
    total_revenue = revenue_res.scalar() or 0

    deposits_q = select(func.sum(Deposit.amount_cents)).where(
        Deposit.status == DepositStatus.APPROVED
    )
    deposits_res = await session.execute(deposits_q)
    total_deposits = deposits_res.scalar() or 0

    # 2. Operational Metrics
    total_orders_q = select(func.count(Order.id)).where(
        Order.status == OrderStatus.COMPLETED
    )
    total_orders_res = await session.execute(total_orders_q)
    total_orders = total_orders_res.scalar() or 0

    orders_24h_q = select(func.count(Order.id)).where(
        Order.status == OrderStatus.COMPLETED,
        Order.created_at >= last_24h
    )
    orders_24h_res = await session.execute(orders_24h_q)
    orders_24h = orders_24h_res.scalar() or 0

    # 3. User Metrics
    total_users_q = select(func.count(User.id))
    total_users_res = await session.execute(total_users_q)
    total_users = total_users_res.scalar() or 0

    users_24h_q = select(func.count(User.id)).where(
        User.created_at >= last_24h
    )
    users_24h_res = await session.execute(users_24h_q)
    users_24h = users_24h_res.scalar() or 0

    # 4. Product Metrics (Top 5)
    top_products_q = (
        select(Order.product_name, func.count(Order.id).label("sales_count"))
        .where(Order.status == OrderStatus.COMPLETED)
        .group_by(Order.product_name)
        .order_by(desc("sales_count"))
        .limit(5)
    )
    top_products_res = await session.execute(top_products_q)
    top_products = [(row[0], row[1]) for row in top_products_res.all()]

    return AnalyticsStats(
        total_revenue_cents=total_revenue,
        total_deposits_cents=total_deposits,
        total_orders=total_orders,
        orders_24h=orders_24h,
        total_users=total_users,
        users_24h=users_24h,
        top_products=top_products
    )
