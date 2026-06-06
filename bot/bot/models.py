"""
SQLAlchemy ORM models for NAZZSHOP.

Schema overview
---------------
User      : a Telegram user, their money balance, referral points, referrer.
Category  : a grouping of products.
Product   : a sellable digital product. Holds price, points price, quantity,
            and visibility flags. Stock status is derived from quantity + flags.
StockItem : an individual digital item (code/key/text) belonging to a Product.
            Buying a product consumes one StockItem and delivers its content.
Order     : a record of a purchase (money OR points), with the delivered content.
Deposit   : a manual crypto deposit submission (TxID) awaiting admin review.

Money amounts and prices are stored as integer "cents" to avoid float rounding
errors. Helper properties expose human-friendly decimal values.
"""

from __future__ import annotations

import datetime as dt
import enum
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    """Declarative base for all models."""


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class DepositStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class OrderStatus(str, enum.Enum):
    COMPLETED = "completed"
    REFUNDED = "refunded"


class PaymentMethod(str, enum.Enum):
    BALANCE = "balance"   # paid from money balance
    POINTS = "points"     # redeemed using referral points


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class User(Base):
    __tablename__ = "users"

    # Telegram user id is the primary key (BigInteger to be safe).
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # Money balance stored in integer cents.
    balance_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Referral points (kept entirely separate from money).
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Referral graph: who invited this user.
    referrer_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    # Set True once the user passed membership verification at least once.
    # Used so a referrer is only rewarded for genuinely verified invitees.
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Language preference: "en" or "fr"
    language_code: Mapped[str] = mapped_column(String(2), default="en", nullable=False)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    orders: Mapped[List["Order"]] = relationship(back_populates="user")
    deposits: Mapped[List["Deposit"]] = relationship(back_populates="user")
    referrals: Mapped[List["User"]] = relationship(
        "User", backref="referrer", remote_side=[id]
    )

    @property
    def balance(self) -> float:
        """Money balance as a decimal value."""
        return self.balance_cents / 100

    @property
    def display(self) -> str:
        """A non-identifying short label for logs/admin lists."""
        return f"user#{self.id}"


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    # Points-shop categories are flagged so the two shops stay separate.
    is_points_shop: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    products: Mapped[List["Product"]] = relationship(
        back_populates="category", cascade="all, delete-orphan"
    )


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("public_id", name="uq_product_public_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Human-facing unique product ID, e.g. "NZ-0007". Always unique.
    public_id: Mapped[str] = mapped_column(String(32), nullable=False)

    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Money price in cents (used in the main shop).
    price_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Points price (used in the points shop). 0 means "not redeemable by points".
    points_price: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Cached available quantity. Kept in sync with unsold StockItems for products
    # that use per-item delivery; for "service" products without stock items it
    # is managed directly by admins.
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Optional emoji icon to display before the product name
    icon_emoji: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    # Local path to an icon or image file (.ico, .png, .jpg)
    image_path: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    category: Mapped["Category"] = relationship(back_populates="products")
    stock_items: Mapped[List["StockItem"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )

    # ---- Derived helpers ----------------------------------------------------
    @property
    def price(self) -> float:
        return self.price_cents / 100

    @property
    def available(self) -> bool:
        """A product is buyable only if visible and has quantity > 0."""
        return (not self.hidden) and self.quantity > 0

    @property
    def status_icon(self) -> str:
        """🟢 if available to buy, 🔴 otherwise (hidden or out of stock)."""
        return "🟢" if self.available else "🔴"


class StockItem(Base):
    """
    An individual digital item delivered to the buyer (a code, key, account, etc.).
    Selling a product hands over the oldest unsold item and marks it sold.
    """

    __tablename__ = "stock_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sold: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    product: Mapped["Product"] = relationship(back_populates="stock_items")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))

    product_name: Mapped[str] = mapped_column(String(128), nullable=False)
    # Amount in cents (for balance orders) or points (for points orders).
    amount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod), default=PaymentMethod.BALANCE, nullable=False
    )
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus), default=OrderStatus.COMPLETED, nullable=False
    )
    # The delivered digital content (snapshot, so it survives product edits).
    delivered_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="orders")


class Deposit(Base):
    __tablename__ = "deposits"
    __table_args__ = (
        # Prevent the same TxID being submitted twice, ever.
        UniqueConstraint("txid", name="uq_deposit_txid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))

    txid: Mapped[str] = mapped_column(String(256), nullable=False)
    # Amount the admin credits on approval, in cents. Filled by admin or by the
    # user's stated amount; defaults to 0 until set.
    amount_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    network: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    status: Mapped[DepositStatus] = mapped_column(
        Enum(DepositStatus), default=DepositStatus.PENDING, nullable=False
    )
    admin_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reviewed_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="deposits")

    @property
    def amount(self) -> float:
        return self.amount_cents / 100
