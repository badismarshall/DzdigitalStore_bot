# NAZZSHOP — Telegram Digital Products Store Bot

A production-ready Telegram bot for running a digital-products store. Built with
**aiogram 3.x**, **SQLAlchemy 2.x (async)**, and **Turso/SQLite**. It handles membership
gating, a category/product catalog with per-item stock, crypto-only purchases,
manual deposit approvals, a referral points system with its own shop, generic
group/channel notifications, and a full inline-keyboard admin panel.

---

## Features

- **Membership gate** — users must join a required channel **and** group (configured
  by username) before any feature unlocks. Verification is cached in the DB.
- **Catalog** — products grouped into categories, each with a unique public ID
  (`NZ-0001`, `NZ-0002`, …) and a visual stock indicator: 🟢 available / 🔴 unavailable.
- **Stock** — add unique deliverable items (keys/accounts) one per line, or set a
  plain quantity for non-unique products. Sales consume the oldest item first (FIFO).
- **Crypto-only purchases** — users deposit, an admin approves, balance is credited,
  then users buy. Stock is deducted atomically; sold-out products can't be purchased.
- **Manual deposits** — users submit a TxID, stored as *pending*. Duplicate TxIDs are
  rejected (checked in code and enforced by a DB unique constraint). Admins approve
  (credits balance) or reject (no change).
- **Referral points** — inviting a user who then verifies grants points (once per
  invitee). Points are fully separate from money and can be redeemed in the **Points Shop**,
  which browses exactly like the main shop.
- **Notifications** — order placed, deposit submitted, product added, stock depleted,
  and product hidden are announced to a linked chat. **Wording is always generic — no
  customer username, name, or ID is ever revealed.**
- **Admin panel** — inline keyboards for categories, products, stock, orders, deposits
  (approve/reject), users, balance/points edits, and hide/unhide.

---

## Project structure

```
nazzshop/
├── .env.example            # Copy to .env and fill in
├── .gitignore
├── requirements.txt
├── README.md
├── data/                   # SQLite DB lives here (auto-created)
│   └── .gitkeep
└── bot/
    ├── __init__.py
    ├── config.py           # Env-var loading + validation
    ├── database.py         # Async engine, session factory, init_db()
    ├── models.py           # SQLAlchemy ORM models + enums
    ├── main.py             # Entry point (python -m bot.main)
    ├── handlers/
    │   ├── __init__.py     # setup_routers()
    │   ├── states.py       # FSM states
    │   ├── common.py       # /start, verification, main menu, balance
    │   ├── shop.py         # Browse & buy (money + points shops)
    │   ├── deposit.py      # Submit TxID deposits
    │   ├── referral.py     # Referral link & stats
    │   └── admin.py        # /admin panel
    ├── keyboards/
    │   ├── __init__.py
    │   ├── callbacks.py    # Typed callback-data factories
    │   ├── common.py
    │   ├── shop.py
    │   └── admin.py
    ├── services/
    │   ├── __init__.py
    │   ├── utils.py
    │   ├── user_service.py
    │   ├── catalog_service.py
    │   ├── order_service.py
    │   ├── deposit_service.py
    │   ├── membership_service.py
    │   └── notification_service.py
    └── middlewares/
        ├── __init__.py
        ├── db.py           # Injects an AsyncSession per update
        └── access.py       # User bootstrap, ban check, membership gate
```

---

## Prerequisites

- Python 3.10+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- A Telegram **channel** and **group** for the membership gate
- A chat for notifications (can be the same group)

---

## Setup

### 1. Create the bot

1. Message **@BotFather**, send `/newbot`, and follow the prompts.
2. Copy the **token** it gives you.
3. Send `/setprivacy` → select your bot → **Disable**, so it can read group messages.

### 2. Make the bot an admin of your channel and group

The bot can only check membership and post notifications if it is an **administrator**
in both the required channel and the required group. Add it to each and grant admin
rights (posting messages is enough; no need for ban/delete permissions).

### 3. Find your admin Telegram ID

Message [@userinfobot](https://t.me/userinfobot) to get your numeric user ID. This is
what goes in `ADMIN_IDS`.

### 4. Install dependencies

```bash
cd nazzshop
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 5. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

| Variable           | Required | Description                                                                 |
|--------------------|----------|-----------------------------------------------------------------------------|
| `BOT_TOKEN`        | ✅       | Token from BotFather.                                                       |
| `ADMIN_IDS`        | ✅       | Comma-separated numeric admin IDs, e.g. `111111111,222222222`.              |
| `REQUIRED_CHANNEL` | ✅       | Channel username **without** `@`, e.g. `nazzshop_channel`.                  |
| `REQUIRED_GROUP`   | ✅       | Group username **without** `@`, e.g. `nazzshop_group`.                      |
| `NOTIFY_CHAT`      | ✅       | Username (no `@`) **or** numeric `-100…` ID where notifications are posted. |
| `CRYPTO_WALLETS`   | ✅       | `LABEL\|ADDRESS` pairs separated by `;`, e.g. `USDT (TRC20)\|TXXXX;BTC\|bc1qXXXX`. |
| `REFERRAL_POINTS`  | ➖       | Points granted per verified referral (default `10`).                        |
| `DATABASE_URL`     | ➖       | Defaults to `sqlite+aiosqlite:///data/nazzshop.db`.                          |
| `TURSO_DATABASE_URL` | ➖       | (Optional) Turso DB URL, e.g. `libsql://your-db.turso.io`.                 |
| `TURSO_AUTH_TOKEN` | ➖       | (Optional) Turso Auth Token. If provided, overrides `DATABASE_URL`.        |
| `CURRENCY_SYMBOL`  | ➖       | Display symbol for balances (default `$`).                                  |

> **Note on `NOTIFY_CHAT`:** a public username works for channels/groups. For a
> private group, use its numeric ID (looks like `-1001234567890`). You can get it by
> temporarily forwarding a group message to [@userinfobot](https://t.me/userinfobot).

### 6. Run

```bash
python -m bot.main
```

The database tables are created automatically on first launch. You should see a log
line confirming the bot has started polling.

---

## Using the bot

### As a user

1. Send `/start`. If you haven't joined the channel and group, you'll get join buttons
   and a **"I've joined"** check. Nothing else works until both are verified.
2. After verifying, the main menu appears: **Shop**, **Points Shop**, **Deposit**,
   **Balance**, **Referrals**.
3. **Deposit:** pick a wallet, send crypto to the shown address, then submit your
   **TxID**. It enters the pending queue for an admin to approve.
4. **Shop:** browse categories → products → buy. Your balance is charged and the
   digital item (if it's a unique-item product) is delivered in chat.
5. **Referrals:** share your personal link. When someone joins through it and verifies,
   you earn points to spend in the Points Shop.

### As an admin

Send `/admin` to open the panel. Everything is inline-keyboard driven:

- **Categories** — create, rename, hide/unhide, delete. Categories can belong to either
  the money shop or the points shop.
- **Products** — create (name, description, price, optional points price), edit any
  field, hide/unhide, delete.
- **Stock** — add unique items (one deliverable per line) or set a plain quantity for
  non-unique products.
- **Deposits** — review the pending queue; approve (optionally overriding the amount) to
  credit the user, or reject with a note.
- **Orders** — view recent orders.
- **Users** — list users, edit balance (set or add/subtract), edit points, ban/unban.

Admins bypass the membership gate and bans automatically.

---

## How money and points are stored

- **Money** is stored as integer **cents** to avoid floating-point rounding bugs;
  `.balance` / `.price` helper properties expose the decimal value for display.
- **Points** are plain integers and are completely independent of money — they can only
  be earned via referrals and spent in the Points Shop.

---

## Notifications & privacy

Notifications are intentionally generic. Examples of what the linked chat sees:

- *"🛒 A customer just purchased a product."*
- *"💰 A new deposit was submitted and is awaiting review."*
- *"📦 A new product was added to the store."*
- *"⚠️ A product just went out of stock."*
- *"🙈 A product was hidden from the store."*

No username, display name, or user ID is ever included. Notification send failures are
swallowed so a misconfigured `NOTIFY_CHAT` never breaks the user-facing flow (a warning
is logged instead).

---

## Deployment notes

- **Single process only.** The bot uses aiogram's in-memory FSM storage, so run exactly
  one instance. To scale horizontally or persist FSM state across restarts, switch the
  dispatcher to `RedisStorage` in `bot/main.py` and run Redis.
- **Polling vs webhooks.** This bot uses long polling, which needs no public URL and is
  ideal for a single VPS or container. For high traffic you can adapt it to webhooks.
- **Backups.** The entire state is the SQLite file under `data/`. Back it up regularly.

### Example: run with systemd

```ini
# /etc/systemd/system/nazzshop.service
[Unit]
Description=NAZZSHOP Telegram bot
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/nazzshop
ExecStart=/opt/nazzshop/.venv/bin/python -m bot.main
Restart=always
RestartSec=5
EnvironmentFile=/opt/nazzshop/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nazzshop
sudo journalctl -u nazzshop -f      # watch logs
```

---

## Troubleshooting

| Symptom                                   | Likely cause / fix                                                                 |
|-------------------------------------------|------------------------------------------------------------------------------------|
| Membership check always fails             | Bot isn't an **admin** in the channel/group, or the username in `.env` is wrong.   |
| Notifications never arrive                | `NOTIFY_CHAT` wrong, or bot isn't a member/admin of that chat. Check the logs.     |
| `Missing required environment variable…`  | A required value in `.env` is blank. Fill it in.                                   |
| Bot doesn't respond to group commands     | Disable privacy mode in BotFather (`/setprivacy` → Disable).                       |
| Deep-link referrals not crediting points  | The invitee must actually **verify** (join both chats) for the referrer to earn.   |

---

## Security notes

- Never commit your real `.env` — it's already in `.gitignore`.
- The admin panel is locked to the IDs in `ADMIN_IDS` via a filter on every admin
  message and callback.
- All purchase and deposit mutations are validated before any balance/stock change and
  committed in a single transaction, so an interrupted operation can't half-apply.

---

## License

Provided as-is for you to adapt to your store.
