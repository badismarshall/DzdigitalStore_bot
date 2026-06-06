import asyncio
import random
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database import SessionLocal, init_db
from bot.models import Category, Product, StockItem

async def create_mock_data():
    await init_db()
    async with SessionLocal() as session:
        # 1. Create Categories
        categories_data = [
            ("Premium Accounts", False),
            ("Game Keys", False),
            ("Gift Cards", False),
            ("Points Rewards", True),
            ("Exclusive Roles", True),
        ]
        
        categories = []
        for name, is_points in categories_data:
            cat = Category(name=name, is_points_shop=is_points)
            session.add(cat)
            categories.append(cat)
        
        await session.flush()  # Get IDs

        # 2. Create Products
        mock_products = [
            # Money Shop
            ("Netflix Premium 1 Month", categories[0], 500, 0),
            ("Spotify Family 3 Months", categories[0], 1200, 0),
            ("Minecraft Java Edition", categories[1], 2500, 0),
            ("Steam $20 Wallet Code", categories[2], 2100, 0),
            
            # Points Shop
            ("Special Badge", categories[3], 0, 100),
            ("Double XP Boost", categories[3], 0, 250),
            ("VIP Member Role", categories[4], 0, 1000),
        ]

        for name, cat, price, points_price in mock_products:
            # Generate a public ID like NZ-XXXX
            public_id = f"NZ-{random.randint(1000, 9999)}"
            product = Product(
                name=name,
                category_id=cat.id,
                public_id=public_id,
                price_cents=price,
                points_price=points_price,
                quantity=0  # Will be updated by stock items
            )
            session.add(product)
            await session.flush()

            # 3. Add Stock Items for some products
            if "Badge" not in name and "Role" not in name:
                num_items = random.randint(3, 10)
                product.quantity = num_items
                for i in range(num_items):
                    stock = StockItem(
                        product_id=product.id,
                        content=f"MOCK-KEY-{random.randint(100000, 999999)}"
                    )
                    session.add(stock)
            else:
                # Service products just have quantity
                product.quantity = 999

        await session.commit()
        print("Mock data created successfully!")

if __name__ == "__main__":
    asyncio.run(create_mock_data())
