"""
Safe migration script for Turso (libSQL).
This script imports the bot's own engine to ensure the connection is correct.
Run this on your server: python migrate.py
"""
import asyncio
import os
import sys

# Add the current directory to the search path so we can import 'bot'
sys.path.append(os.getcwd())

try:
    from sqlalchemy import text
    from bot.database import engine
except ImportError:
    print("❌ Error: Could not import bot modules.")
    print("Ensure you are running this from the root folder.")
    exit(1)

def do_migration(conn):
    print("🔍 Checking 'users' table...")
    # PRAGMA is best run in sync context for SQLite/libSQL
    result = conn.execute(text("PRAGMA table_info(users)"))
    columns = [row[1] for row in result.fetchall()]

    if "language_code" not in columns:
        print("➕ Adding 'language_code' column...")
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN language_code VARCHAR(2) DEFAULT 'en' NOT NULL"
        ))
        print("✅ Column added successfully!")
    else:
        print("ℹ️ Column 'language_code' already exists.")

async def migrate():
    print("🔗 Connecting to Turso using bot's engine configuration...")

    try:
        # Use begin() to automatically handle transactions
        async with engine.begin() as conn:
            # run_sync is the standard way to do schema changes in async SQLAlchemy
            await conn.run_sync(do_migration)

    except Exception as e:
        print(f"❌ Error during migration: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(migrate())
