"""
Handler routers for NAZZSHOP.

`setup_routers` wires every feature router into the main dispatcher in a sane
order: common (start/menu), shop, points shop, deposit, referral, then admin.
"""

from __future__ import annotations

from aiogram import Dispatcher

from . import admin, common, deposit, referral, shop


def setup_routers(dp: Dispatcher) -> None:
    dp.include_router(common.router)
    dp.include_router(shop.router)
    dp.include_router(deposit.router)
    dp.include_router(referral.router)
    dp.include_router(admin.router)
