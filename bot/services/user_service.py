"""
User-related business logic: get-or-create, balance & points adjustments,
referral attribution and verification bookkeeping.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import config
from ..models import User


async def get_user(session: AsyncSession, user_id: int) -> Optional[User]:
    """Fetch a single user by Telegram id, or None."""
    return await session.get(User, user_id)


async def find_user(session: AsyncSession, query: str) -> Optional[User]:
    """
    Find a user by Telegram ID (if numeric) or username (if it starts with @ or
    is a plain string). Returns None if not found or ambiguous.
    """
    query = query.strip().lstrip("@")
    if not query:
        return None

    # 1. Try numeric ID
    if query.isdigit():
        user = await session.get(User, int(query))
        if user:
            return user

    # 2. Try username
    stmt = select(User).where(func.lower(User.username) == query.lower())
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_or_create_user(
    session: AsyncSession,
    user_id: int,
    username: Optional[str] = None,
    full_name: Optional[str] = None,
    referrer_id: Optional[int] = None,
) -> User:
    """
    Return the existing user or create a new one. If a (valid) referrer_id is
    supplied for a brand-new user, it is recorded but the referral reward is
    only granted later, once the new user is verified (see reward_referrer).
    """
    user = await session.get(User, user_id)
    if user is not None:
        # Keep the profile fields fresh.
        changed = False
        if username is not None and user.username != username:
            user.username = username
            changed = True
        if full_name is not None and user.full_name != full_name:
            user.full_name = full_name
            changed = True
        if changed:
            await session.commit()
        return user

    # New user. Validate the referrer: must exist and not be the user itself.
    valid_referrer: Optional[int] = None
    if referrer_id and referrer_id != user_id:
        ref = await session.get(User, referrer_id)
        if ref is not None:
            valid_referrer = referrer_id

    user = User(
        id=user_id,
        username=username,
        full_name=full_name,
        referrer_id=valid_referrer,
    )
    session.add(user)
    await session.commit()
    return user


async def mark_verified_and_reward_referrer(session: AsyncSession, user: User) -> bool:
    """
    Mark a user as verified the first time they pass membership checks, and
    grant referral points to their referrer exactly once.

    Returns True if a referral reward was just granted (so the caller can
    notify the referrer), False otherwise.
    """
    if user.verified:
        return False

    user.verified = True
    rewarded = False

    if user.referrer_id:
        referrer = await session.get(User, user.referrer_id)
        if referrer is not None and not referrer.is_banned:
            referrer.points += config.referral_points
            rewarded = True

    await session.commit()
    return rewarded


async def adjust_balance(session: AsyncSession, user: User, delta_cents: int) -> User:
    """Add (or subtract) money cents from a user's balance. Never goes below 0."""
    user.balance_cents = max(0, user.balance_cents + delta_cents)
    await session.commit()
    return user


async def set_balance(session: AsyncSession, user: User, cents: int) -> User:
    """Set the absolute money balance (in cents)."""
    user.balance_cents = max(0, cents)
    await session.commit()
    return user


async def adjust_points(session: AsyncSession, user: User, delta: int) -> User:
    """Add (or subtract) referral points. Never goes below 0."""
    user.points = max(0, user.points + delta)
    await session.commit()
    return user


async def set_points(session: AsyncSession, user: User, points: int) -> User:
    """Set the absolute points balance."""
    user.points = max(0, points)
    await session.commit()
    return user


async def set_banned(session: AsyncSession, user: User, banned: bool) -> User:
    """Ban or unban a user."""
    user.is_banned = banned
    await session.commit()
    return user


async def set_language(session: AsyncSession, user: User, language_code: str) -> User:
    """Update user's language preference."""
    user.language_code = language_code
    await session.commit()
    return user


async def count_referrals(session: AsyncSession, user_id: int) -> int:
    """Count how many users were referred by this user."""
    result = await session.execute(
        select(func.count()).select_from(User).where(User.referrer_id == user_id)
    )
    return int(result.scalar_one())


async def list_users(
    session: AsyncSession, limit: int = 20, offset: int = 0
) -> List[User]:
    """List users newest-first for the admin panel."""
    result = await session.execute(
        select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all())


async def total_users(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(User))
    return int(result.scalar_one())


async def all_user_ids(
    session: AsyncSession, include_banned: bool = False
) -> List[int]:
    """
    Return every user's Telegram id, for broadcasting. Banned users are excluded
    by default so they don't receive announcements.
    """
    stmt = select(User.id)
    if not include_banned:
        stmt = stmt.where(User.is_banned.is_(False))
    result = await session.execute(stmt)
    return [int(row) for row in result.scalars().all()]
