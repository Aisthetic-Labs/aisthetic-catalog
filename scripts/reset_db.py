"""
Drop all tables, recreate from scratch, and bootstrap a merchant.

Usage:
    python -m scripts.reset_db
"""

import asyncio

from sqlalchemy import text

from app.core.db_control import ControlBase, ControlSessionLocal, control_engine
from app.control.models_control import Merchant, MerchantDBConnection, MerchantStatus

# Import tenant models so TenantBase.metadata knows about all tables
from app.catalog.models_tenant import TenantBase  # noqa: F401 (Product, CsvUploadRow, etc.)
from app.stylist.models_user import UserProfile, UserPreferences  # noqa: F401
from app.core.tenant_db import get_tenant_engine


def _reset_control_db():
    """Drop and recreate control-plane tables, then bootstrap a merchant."""
    ControlBase.metadata.drop_all(bind=control_engine)
    ControlBase.metadata.create_all(bind=control_engine)

    session = ControlSessionLocal()
    try:
        m = Merchant(
            name="Demo Merchant",
            slug="demo-merchant",
            status=MerchantStatus.active,
            plan="starter",
        )
        session.add(m)
        session.flush()

        conn = MerchantDBConnection(
            merchant_id=m.id,
            db_type="postgres",
            db_host="db",
            db_port=5432,
            db_name="aisthetic_merchant_1",
            db_user="airbender",
            db_password="password",
        )
        session.add(conn)
        session.commit()
        return str(m.id)
    finally:
        session.close()


async def _reset_tenant_db(merchant_id: str):
    """Drop and recreate all tenant tables (catalog + user)."""
    engine = get_tenant_engine(merchant_id)
    async with engine.begin() as conn:
        # Use CASCADE to handle leftover tables / FK deps not in current models
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(TenantBase.metadata.create_all)
    await engine.dispose()


def main():
    print("Resetting control DB...")
    merchant_id = _reset_control_db()
    print(f"Control DB reset. Merchant ID: {merchant_id}")

    print("Resetting tenant DB...")
    asyncio.run(_reset_tenant_db(merchant_id))
    print("Tenant DB reset.")

    print(f"\n{merchant_id}")


if __name__ == "__main__":
    main()
