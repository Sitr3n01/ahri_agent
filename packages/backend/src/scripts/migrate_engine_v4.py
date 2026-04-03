"""
Migration script for V4 Engine tables.
Run: python -m src.scripts.migrate_engine_v4
"""
import asyncio
from sqlalchemy import text
from ..models.database import engine, Base

async def migrate():
    async with engine.begin() as conn:
        # Create new tables
        await conn.run_sync(Base.metadata.create_all)
        print("V4 Engine tables created successfully")

if __name__ == "__main__":
    asyncio.run(migrate())
