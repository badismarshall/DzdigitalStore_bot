"""
Central configuration loader for NAZZSHOP.

Loads every setting from environment variables (via a .env file) and exposes
them through a single, validated `config` object. Importing this module early
guarantees the bot fails fast with a clear message if something is misconfigured.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Tuple

from dotenv import load_dotenv

# Load variables from a local .env file if present. Real environment variables
# always take precedence over .env values.
load_dotenv()


def _get(name: str, default: str | None = None, required: bool = False) -> str:
    """Read a string environment variable with optional requirement check."""
    value = os.getenv(name, default)
    if required and (value is None or value.strip() == ""):
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Did you copy .env.example to .env and fill it in?"
        )
    return value if value is not None else ""


def _parse_admin_ids(raw: str) -> List[int]:
    """Parse a comma-separated list of admin Telegram user IDs into ints."""
    ids: List[int] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            ids.append(int(chunk))
        except ValueError:
            raise RuntimeError(f"ADMIN_IDS contains a non-numeric value: {chunk!r}")
    if not ids:
        raise RuntimeError("ADMIN_IDS must contain at least one numeric Telegram ID.")
    return ids


def _parse_wallets(raw: str) -> List[Tuple[str, str]]:
    """
    Parse crypto wallets from the form:
        LABEL|ADDRESS;LABEL|ADDRESS
    Returns a list of (label, address) tuples.
    """
    wallets: List[Tuple[str, str]] = []
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry:
            continue
        if "|" not in entry:
            raise RuntimeError(
                f"CRYPTO_WALLETS entry is malformed (expected LABEL|ADDRESS): {entry!r}"
            )
        label, address = entry.split("|", 1)
        wallets.append((label.strip(), address.strip()))
    return wallets


def _normalize_username(raw: str) -> str:
    """Strip a leading @ and surrounding whitespace from a username."""
    return raw.strip().lstrip("@")


@dataclass(frozen=True)
class Config:
    """Immutable, validated configuration for the whole application."""

    bot_token: str
    admin_ids: List[int]
    required_channel: str          # username without @
    required_group: str            # username without @
    notify_chat: str               # username (no @) OR numeric id as string
    crypto_wallets: List[Tuple[str, str]] = field(default_factory=list)
    referral_points: int = 10
    database_url: str = "sqlite+aiosqlite:///data/nazzshop.db"
    currency_symbol: str = "$"

    # Turso Database settings
    turso_url: str | None = None
    turso_token: str | None = None

    # ---- Convenience helpers -------------------------------------------------

    @property
    def final_database_url(self) -> str:
        """
        Construct the SQLAlchemy database URL.
        If turso_url is provided, uses sqlite+aiolibsql://
        Otherwise, falls back to the configured database_url.
        """
        if self.turso_url:
            # Clean URL: strip protocol and ensure sqlite+aiolibsql scheme
            url = self.turso_url.replace("libsql://", "").replace("https://", "").strip("/")
            return f"sqlite+aiolibsql://{url}?secure=true"
        return self.database_url

    def is_admin(self, user_id: int) -> bool:
        """Return True if the given Telegram user ID is configured as an admin."""
        return user_id in self.admin_ids

    @property
    def channel_link(self) -> str:
        """Public t.me link for the required channel."""
        return f"https://t.me/{self.required_channel}"

    @property
    def group_link(self) -> str:
        """Public t.me link for the required group."""
        return f"https://t.me/{self.required_group}"

    @property
    def channel_chat_id(self) -> str:
        """Chat identifier Telegram accepts for the channel (@username)."""
        return f"@{self.required_channel}"

    @property
    def group_chat_id(self) -> str:
        """Chat identifier Telegram accepts for the group (@username)."""
        return f"@{self.required_group}"

    @property
    def notify_chat_id(self) -> str:
        """
        Chat identifier for notifications. Numeric IDs (possibly negative) are
        passed through as-is; usernames get an @ prefix.
        """
        raw = self.notify_chat
        if raw.lstrip("-").isdigit():
            return raw
        return f"@{raw}"


def load_config() -> Config:
    """Build and validate a Config instance from the environment."""
    return Config(
        bot_token=_get("BOT_TOKEN", required=True),
        admin_ids=_parse_admin_ids(_get("ADMIN_IDS", required=True)),
        required_channel=_normalize_username(_get("REQUIRED_CHANNEL", required=True)),
        required_group=_normalize_username(_get("REQUIRED_GROUP", required=True)),
        notify_chat=_normalize_username(_get("NOTIFY_CHAT", required=True)),
        crypto_wallets=_parse_wallets(_get("CRYPTO_WALLETS", default="")),
        referral_points=int(_get("REFERRAL_POINTS", default="10") or "10"),
        database_url=_get("DATABASE_URL", default="sqlite+aiosqlite:///data/nazzshop.db"),
        currency_symbol=_get("CURRENCY_SYMBOL", default="$") or "$",
        turso_url=_get("TURSO_DATABASE_URL"),
        turso_token=_get("TURSO_AUTH_TOKEN"),
    )


# A single shared, validated instance used across the project.
config = load_config()
