"""
Create catalog tables (product, product_variant, product_image) in a merchant's DB.

Usage:
    python -m scripts.create_tenant_schema --merchant-id <merchant_uuid>
"""

import argparse
import asyncio
from uuid import UUID

from app.core.tenant_db import get_tenant_engine
from app.catalog.models_tenant import TenantBase


async def create_schema_for_merchant(merchant_id: str):
    # Validate UUID format early
    try:
        UUID(merchant_id)
    except ValueError:
        raise SystemExit(f"❌ Invalid merchant UUID: {merchant_id}")

    engine = get_tenant_engine(merchant_id)

    async with engine.begin() as conn:
        # This will create all tables defined in TenantBase metadata
        await conn.run_sync(TenantBase.metadata.create_all)

    await engine.dispose()
    print(f"✅ Created tenant catalog schema for merchant {merchant_id}")


def main():
    parser = argparse.ArgumentParser(
        description="Create tenant catalog schema (product, variants, images) for a merchant DB"
    )
    parser.add_argument(
        "--merchant-id",
        required=True,
        help="Merchant UUID (must exist in control-plane, with DB connection configured)",
    )
    args = parser.parse_args()

    asyncio.run(create_schema_for_merchant(args.merchant_id))


if __name__ == "__main__":
    main()