"""
Reindex OpenSearch for a merchant.

Deletes the existing index and rebuilds it from all products
linked to successfully ingested CSV rows (status='processed').

Usage:
    python -m scripts.reindex_opensearch --merchant-id <uuid>
"""

import argparse
import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.catalog.indexing_service import ensure_index_exists, index_product_to_opensearch
from app.catalog.models_tenant import CsvUploadRow, Product, ProductImage, ProductVariant
from app.catalog.opensearch_client import get_catalog_index_name, get_opensearch_client
from app.core.tenant_db import get_tenant_sessionmaker
from app.logger import logger


async def reindex(merchant_id: str) -> None:
    client = get_opensearch_client()
    index_name = get_catalog_index_name(merchant_id)

    # Delete existing index
    if client.indices.exists(index=index_name):
        client.indices.delete(index=index_name)
        logger.info("Deleted existing index: %s", index_name)
    else:
        logger.info("No existing index found: %s", index_name)

    # Create fresh index
    ensure_index_exists(client, index_name)
    logger.info("Created index: %s", index_name)

    # Open DB session and query processed products
    SessionLocal = get_tenant_sessionmaker(merchant_id)

    async with SessionLocal() as session:
        # Get distinct merchant_product_ids that were successfully processed
        processed_ids_q = (
            select(CsvUploadRow.merchant_product_id)
            .where(CsvUploadRow.status == "processed")
            .distinct()
        )

        # Join with Product to get actual product rows
        products_q = (
            select(Product)
            .where(Product.merchant_product_id.in_(processed_ids_q))
        )
        result = await session.execute(products_q)
        products = result.scalars().all()

    total = len(products)
    indexed = 0
    failed = 0

    logger.info("Found %d products to index", total)

    for i, product in enumerate(products, 1):
        try:
            async with SessionLocal() as session:
                # Fetch primary image (lowest position)
                img_q = (
                    select(ProductImage)
                    .where(ProductImage.product_id == product.id)
                    .order_by(ProductImage.position.asc())
                    .limit(1)
                )
                img_result = await session.execute(img_q)
                primary_image = img_result.scalar_one_or_none()
                image_url = primary_image.image_url if primary_image else None

                # Fetch variants
                var_q = select(ProductVariant).where(
                    ProductVariant.product_id == product.id
                )
                var_result = await session.execute(var_q)
                variants = var_result.scalars().all()

            await index_product_to_opensearch(
                client, index_name, product, image_url, variants
            )
            indexed += 1
            logger.info("[%d/%d] Indexed product %s", i, total, product.merchant_product_id)
        except Exception:
            failed += 1
            logger.exception(
                "[%d/%d] Failed to index product %s", i, total, product.merchant_product_id
            )

    logger.info(
        "Reindex complete: %d indexed, %d failed out of %d total",
        indexed, failed, total,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Reindex OpenSearch for a merchant")
    parser.add_argument(
        "--merchant-id",
        required=True,
        help="Merchant UUID",
    )
    args = parser.parse_args()

    # Validate UUID
    try:
        uuid.UUID(args.merchant_id)
    except ValueError:
        parser.error(f"Invalid UUID: {args.merchant_id}")

    asyncio.run(reindex(args.merchant_id))


if __name__ == "__main__":
    main()
