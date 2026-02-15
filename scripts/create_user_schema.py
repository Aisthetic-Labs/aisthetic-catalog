# scripts/create_user_schema.py
"""
Create UserProfile and UserPreferences tables in a merchant's tenant DB.

Usage:
    python -m scripts.create_user_schema --merchant-id <merchant_uuid>
"""

import argparse
import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine

# This should already exist in your project (similar to get_tenant_sessionmaker)
from app.core.tenant_db import get_tenant_engine

# Import models so their tables are registered
from app.stylist.models_user import UserProfile, UserPreferences


async def create_user_schema_for_merchant(merchant_id: str) -> None:
    # Validate UUID early
    try:
        UUID(merchant_id)
    except ValueError:
        raise SystemExit(f"❌ Invalid merchant UUID: {merchant_id}")

    engine: AsyncEngine = get_tenant_engine(merchant_id)

    async with engine.begin() as conn:
        # Create each table individually, and safely
        await conn.run_sync(UserProfile.__table__.create, checkfirst=True)
        await conn.run_sync(UserPreferences.__table__.create, checkfirst=True)

    await engine.dispose()
    print(f"✅ Created/verified user_profile & user_preferences tables for merchant {merchant_id}")


def main():
    parser = argparse.ArgumentParser(
        description="Create user profile/event schema for a merchant tenant DB"
    )
    parser.add_argument(
        "--merchant-id",
        required=True,
        help="Merchant UUID (must exist in control-plane, with DB connection configured)",
    )
    args = parser.parse_args()

    asyncio.run(create_user_schema_for_merchant(args.merchant_id))


if __name__ == "__main__":
    main()