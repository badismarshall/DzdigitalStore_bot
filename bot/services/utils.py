"""
Small, dependency-free helpers shared across services and handlers.
"""

from __future__ import annotations

import html
import re
from typing import Optional

from ..config import config


def money(cents: int) -> str:
    """Format integer cents as a currency string, e.g. 1299 -> '$12.99'."""
    return f"{config.currency_symbol}{cents / 100:.2f}"


def parse_money_to_cents(text: str) -> Optional[int]:
    """
    Parse a user/admin supplied money string (e.g. "12.99", "$5", "10") into
    integer cents. Returns None if the value is invalid or negative.
    """
    if text is None:
        return None
    cleaned = text.strip().replace(config.currency_symbol, "").replace(",", "")
    if cleaned == "":
        return None
    try:
        value = round(float(cleaned) * 100)
    except ValueError:
        return None
    if value < 0:
        return None
    return value


def parse_int(text: str, minimum: Optional[int] = None) -> Optional[int]:
    """Parse a plain integer with an optional minimum bound."""
    try:
        value = int(text.strip())
    except (ValueError, AttributeError):
        return None
    if minimum is not None and value < minimum:
        return None
    return value


def clean(text: str) -> str:
    """HTML-escape user-provided text so it is safe in HTML parse mode."""
    return html.escape(text or "", quote=False)


_TXID_RE = re.compile(r"^[A-Za-z0-9:_\-]{8,256}$")


def is_plausible_txid(txid: str) -> bool:
    """
    Light sanity check for a blockchain transaction id. Different chains use
    different formats, so we only enforce a reasonable length and a safe
    character set rather than chain-specific validation.
    """
    if not txid:
        return False
    return bool(_TXID_RE.match(txid.strip()))
