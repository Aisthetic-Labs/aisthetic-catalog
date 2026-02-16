"""
Create any new tables that don't exist yet, without dropping existing ones.

Usage:
    python -m scripts.sync_schema --merchant-id <uuid>
"""

import argparse
import asyncio
from uuid import UUID

from app.core.db_control import ControlBase, control_engine
from app.control.models_control import Merchant, MerchantDBConnection  # noqa: F401

# Import tenant models so TenantBase.metadata knows about all tables
from app.catalog.models_tenant import TenantBase  # noqa: F401
from app.stylist.models_user import UserProfile, UserPreferences  # noqa: F401
from app.core.tenant_db import get_tenant_engine


async def sync_tenant_schema(merchant_id: str):
    try:
        UUID(merchant_id)
    except ValueError:
        raise SystemExit(f"Invalid merchant UUID: {merchant_id}")

    engine = get_tenant_engine(merchant_id)
    async with engine.begin() as conn:
        await conn.run_sync(TenantBase.metadata.create_all)
    await engine.dispose()
    print(f"Tenant schema synced for merchant {merchant_id}")


def main():
    parser = argparse.ArgumentParser(
        description="Create any missing tables (control + tenant) without dropping existing ones"
    )
    parser.add_argument("--merchant-id", required=True, help="Merchant UUID")
    args = parser.parse_args()

    # Sync control tables (idempotent — checkfirst=True is the default)
    ControlBase.metadata.create_all(bind=control_engine)
    print("Control schema synced.")

    asyncio.run(sync_tenant_schema(args.merchant_id))


if __name__ == "__main__":
    main()
