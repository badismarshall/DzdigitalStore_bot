# NAZZSHOP - Telegram Store Bot

## Core Purpose
NAZZSHOP is a production-ready Telegram bot for managing digital product sales. It features membership gating, crypto payments, a referral system, and a full admin panel.

## Technical Stack
- **Language:** Python 3.10+
- **Framework:** aiogram 3.13.1 (Async)
- **Database:** SQLAlchemy 2.0.35 (Async) with SQLite (local) or Turso (remote libSQL).
- **Environment:** `python-dotenv` for configuration management.

## Key Components

### 1. Database Models (`bot/models.py`)
- **User**: Handles balance, points, referrals, and membership status.
- **Category**: Groups products for Money and Points shops.
- **Product**: Base product info (name, price, points_price, quantity).
- **StockItem**: Individual deliverable items (keys/codes) for a product.
- **Order**: Transaction history for purchases.
- **Deposit**: Pending and processed crypto deposit records.

### 2. Services (`bot/services/`)
- `user_service.py`: User lifecycle and balance/points management.
- `catalog_service.py`: CRUD operations for categories, products, and stock.
- `order_service.py`: Purchase logic and item delivery.
- `deposit_service.py`: TxID submission and manual approval flow.
- `membership_service.py`: Group/channel membership verification logic.
- `notification_service.py`: Generic updates to the notification channel.
- `broadcast_service.py`: Throttled message delivery to all users or specific chats.
- `analytics_service.py`: Aggregated shop metrics for the admin dashboard.

### 3. Middleware (`bot/middlewares/`)
- `db.py`: Injects `AsyncSession` into every update handler.
- `access.py`: Bootstraps user records and enforces the membership gate.

### 4. Handler Structure (`bot/handlers/`)
- `common.py`: Start command, main menu, and verification checks.
- `shop.py`: The browsing and buying experience (money + points shops).
- `admin.py`: Inline-driven administrative interface (/admin), including product management, broadcast features, and an analytics dashboard.

## Operational Guide

### Starting the Bot
Run the following command from the project root:
```bash
python -m bot.main
```

### Configuration
Configuration is managed via the `.env` file. Key variables include:
- `BOT_TOKEN`: Your Telegram bot token.
- `ADMIN_IDS`: Comma-separated Telegram user IDs of administrators.
- `REQUIRED_CHANNEL`/`REQUIRED_GROUP`: Usernames (no @) of required chats.
- `NOTIFY_CHAT`: Username or ID for where notifications are sent.
- `CRYPTO_WALLETS`: `LABEL|ADDRESS` pairs for deposit options.

### Migrations
Schema updates are handled by standalone scripts:
- `migrate.py`: Adds the `language_code` column to the `users` table.

## Development Conventions
- **Markup**: Always use **HTML parse mode** for Telegram messages.
- **Architecture**: Keep business logic in **Services**, and keep Handlers thin.
- **UX**: Prioritize **Inline Keyboards** for a responsive, app-like feel.
- **Privacy**: Never include customer usernames or IDs in notifications or public logs.
- **Currency**: Money is stored as integer **cents** to prevent rounding errors.
