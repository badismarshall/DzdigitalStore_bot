"""
Async database engine and session management for NAZZSHOP.

Uses SQLAlchemy 2.x async. A single engine and sessionmaker are created at
import time; handlers/services receive sessions through the
dependency-injection middleware (see middlewares/db.py).
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import config
from .models import Base


def _ensure_sqlite_dir(database_url: str) -> None:
    """Create the parent directory for a SQLite file DB if it doesn't exist."""
    # libSQL (Turso) URLs don't need a local directory check.
    if "libsql" in database_url:
        return
    
    # Only relevant for file-based sqlite URLs like sqlite+aiosqlite:///data/x.db
    marker = ":///"
    if "sqlite" in database_url and marker in database_url:
        path_part = database_url.split(marker, 1)[1]
        # In-memory databases have no filesystem path.
        if path_part and path_part != ":memory:":
            db_path = Path(path_part)
            if db_path.parent and not db_path.parent.exists():
                os.makedirs(db_path.parent, exist_ok=True)


_ensure_sqlite_dir(config.final_database_url)

# Setup connect_args for Turso if needed.
connect_args = {}
if config.turso_url:
    if not config.turso_token:
        raise RuntimeError(
            "TURSO_DATABASE_URL is set but TURSO_AUTH_TOKEN is missing. "
            "Please check your .env file."
        )
    connect_args["auth_token"] = config.turso_token

# echo=False keeps logs clean; flip to True while debugging SQL.
engine = create_async_engine(
    config.final_database_url,
    echo=False,
    future=True,
    poolclass=NullPool,
    connect_args=connect_args,
)

# expire_on_commit=False lets us keep using ORM objects after commit, which is
# convenient inside handlers that read attributes after saving.
SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create all tables. Safe to call on every startup (idempotent)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
