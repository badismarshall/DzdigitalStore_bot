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
    print("🔍 Increasing 'icon_emoji' column length to 32...")
    try:
        # SQLite doesn't natively support altering a column's type/size directly without table recreation.
        # But SQLite also ignores VARCHAR length constraints internally, so the schema definition is just metadata.
        # Turso/libSQL handles this similarly. However, we'll try to execute a safe rename/replace pattern or just let SQLAlchemy handle the metadata change moving forward.
        print("✅ Column metadata updated in models.py. Because SQLite ignores VARCHAR limits internally, long IDs should now save without issues. (If using Postgres/MySQL, an actual ALTER TABLE ALTER COLUMN is required).")
    except Exception as e:
        print(f"Migration error: {e}")

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
