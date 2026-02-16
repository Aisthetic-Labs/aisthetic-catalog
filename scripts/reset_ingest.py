"""
Mark all CSV upload rows as unprocessed (status='pending', attempt_count=0)
so they can be re-ingested via the /process endpoint.

Usage:
    python -m scripts.reset_ingest --merchant-id <uuid>
"""

import argparse
import asyncio
from uuid import UUID

from sqlalchemy import update

from app.catalog.models_tenant import CsvUploadRow
from app.core.tenant_db import get_tenant_sessionmaker


async def reset_rows(merchant_id: str):
    try:
        UUID(merchant_id)
    except ValueError:
        raise SystemExit(f"Invalid merchant UUID: {merchant_id}")

    SessionLocal = get_tenant_sessionmaker(merchant_id)
    async with SessionLocal() as session:
        result = await session.execute(
            update(CsvUploadRow).values(
                status="pending",
                attempt_count=0,
                error_message=None,
                processed_at=None,
            )
        )
        await session.commit()
        print(f"Reset {result.rowcount} rows to 'pending' for merchant {merchant_id}")


def main():
    parser = argparse.ArgumentParser(
        description="Set all CSV upload rows to unprocessed (pending)"
    )
    parser.add_argument("--merchant-id", required=True, help="Merchant UUID")
    args = parser.parse_args()
    asyncio.run(reset_rows(args.merchant_id))


if __name__ == "__main__":
    main()
