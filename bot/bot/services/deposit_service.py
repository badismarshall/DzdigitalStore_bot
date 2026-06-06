"""
Manual crypto deposit workflow.

Users submit a blockchain TxID; it is stored as PENDING. Admins later approve
(crediting the user's balance) or reject (no balance change). Duplicate TxIDs
are rejected at submission time and enforced by a DB unique constraint as a
final safety net.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Deposit, DepositStatus, User


class DepositError(Exception):
    """Raised for invalid or duplicate deposit submissions."""


async def txid_exists(session: AsyncSession, txid: str) -> bool:
    result = await session.execute(
        select(func.count()).select_from(Deposit).where(Deposit.txid == txid.strip())
    )
    return int(result.scalar_one()) > 0


async def submit_deposit(
    session: AsyncSession,
    user: User,
    txid: str,
    network: Optional[str] = None,
    amount_cents: int = 0,
) -> Deposit:
    """
    Create a pending deposit for a submitted TxID. Raises DepositError if the
    TxID was already submitted (by anyone).
    """
    txid = txid.strip()

    if await txid_exists(session, txid):
        raise DepositError("This transaction ID has already been submitted.")

    deposit = Deposit(
        user_id=user.id,
        txid=txid,
        network=network,
        amount_cents=amount_cents,
        status=DepositStatus.PENDING,
    )
    session.add(deposit)
    try:
        await session.commit()
    except IntegrityError:
        # Race condition: the unique constraint caught a duplicate.
        await session.rollback()
        raise DepositError("This transaction ID has already been submitted.")
    return deposit


async def get_deposit(session: AsyncSession, deposit_id: int) -> Optional[Deposit]:
    return await session.get(Deposit, deposit_id)


async def list_deposits(
    session: AsyncSession,
    status: Optional[DepositStatus] = None,
    limit: int = 20,
) -> List[Deposit]:
    stmt = select(Deposit)
    if status is not None:
        stmt = stmt.where(Deposit.status == status)
    stmt = stmt.order_by(desc(Deposit.created_at)).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def approve_deposit(
    session: AsyncSession,
    deposit: Deposit,
    amount_cents: Optional[int] = None,
    note: Optional[str] = None,
) -> Deposit:
    """
    Approve a pending deposit and credit the user's balance. If amount_cents is
    given it overrides the stored amount (admins usually set the verified amount
    here). Only PENDING deposits can be approved.
    """
    if deposit.status != DepositStatus.PENDING:
        raise DepositError("This deposit has already been reviewed.")

    if amount_cents is not None:
        deposit.amount_cents = max(0, amount_cents)

    if deposit.amount_cents <= 0:
        raise DepositError("Set a positive amount before approving.")

    user = await session.get(User, deposit.user_id)
    if user is None:
        raise DepositError("Depositing user no longer exists.")

    user.balance_cents += deposit.amount_cents
    deposit.status = DepositStatus.APPROVED
    deposit.admin_note = note
    deposit.reviewed_at = datetime.now(timezone.utc)

    await session.commit()
    return deposit


async def reject_deposit(
    session: AsyncSession, deposit: Deposit, note: Optional[str] = None
) -> Deposit:
    """Reject a pending deposit. No balance change occurs."""
    if deposit.status != DepositStatus.PENDING:
        raise DepositError("This deposit has already been reviewed.")

    deposit.status = DepositStatus.REJECTED
    deposit.admin_note = note
    deposit.reviewed_at = datetime.now(timezone.utc)

    await session.commit()
    return deposit


async def count_pending(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(Deposit)
        .where(Deposit.status == DepositStatus.PENDING)
    )
    return int(result.scalar_one())
