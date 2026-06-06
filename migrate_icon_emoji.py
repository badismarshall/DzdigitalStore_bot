import asyncio
import os
import sys
from sqlalchemy import text

sys.path.append(os.getcwd())

try:
    from bot.database import engine
except ImportError:
    print("❌ Error: Could not import bot modules.")
    exit(1)

def do_migration(conn):
    print("🔍 Checking 'products' table...")
    result = conn.execute(text("PRAGMA table_info(products)"))
    columns = [row[1] for row in result.fetchall()]

    if "icon_emoji" not in columns:
        print("➕ Adding 'icon_emoji' column...")
        conn.execute(text(
            "ALTER TABLE products ADD COLUMN icon_emoji VARCHAR(16)"
        ))
        print("✅ Column added successfully!")
    else:
        print("ℹ️ Column 'icon_emoji' already exists.")

async def migrate():
    print("🔗 Connecting to database...")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(do_migration)
    except Exception as e:
        print(f"❌ Error during migration: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(migrate())
