"""
Finite-state-machine state groups for multi-step flows.

aiogram's FSM lets us collect multi-step input (e.g. creating a product or
submitting a deposit) without losing track of which step a user is on.
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class DepositStates(StatesGroup):
    waiting_amount = State()
    waiting_amount_confirm = State()


class CategoryStates(StatesGroup):
    waiting_name = State()       # creating a new category
    waiting_rename = State()     # renaming an existing category
class ProductStates(StatesGroup):
    # Creation flow:
    waiting_name = State()
    waiting_icon = State()
    waiting_description = State()
    waiting_price = State()
    waiting_points_price = State()

    # Editing a single field of an existing product:
    waiting_edit_name = State()
    waiting_edit_icon = State()
    waiting_edit_desc = State()

    waiting_edit_price = State()
    waiting_edit_points = State()
    waiting_edit_image = State()
    waiting_add_stock_bulk = State()
    waiting_add_stock_manual = State()
    waiting_set_qty = State()


class DepositReviewStates(StatesGroup):
    waiting_approve_amount = State()
    waiting_reject_note = State()


class UserAdminStates(StatesGroup):
    waiting_search = State()
    waiting_set_balance = State()
    waiting_set_points = State()
    waiting_add_balance = State()
    waiting_add_points = State()


class BroadcastStates(StatesGroup):
    waiting_message = State()    # admin is typing the announcement
    waiting_confirm = State()    # showing a preview, awaiting confirm/cancel
