from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.catalog.dto import MerchantProductIn
from app.catalog.models_tenant import Product, ProductImage, ProductVariant
from app.catalog.normalization import normalize_color, normalize_fit
from app.catalog.opensearch_client import (
    get_opensearch_client,
    get_catalog_index_name,
)
from app.catalog.indexing_service import ensure_index_exists, index_product_to_opensearch
from app.logger import logger


async def upsert_product(session: AsyncSession, data: MerchantProductIn) -> Product:
    """
    Insert/update product, its images and variants in tenant Postgres DB.
    """
    q = select(Product).where(Product.merchant_product_id == data.merchant_product_id)
    res = await session.execute(q)
    product = res.scalar_one_or_none()

    if not product:
        product = Product(merchant_product_id=data.merchant_product_id)

    product.title = data.title
    product.description = data.description
    product.category = data.category
    product.sub_category = data.sub_category
    product.gender = data.gender
    product.color_primary = normalize_color(data.color)
    product.color_secondary = data.secondary_colors
    product.fit = normalize_fit(data.fit)
    product.style_tags = data.style_tags
    product.occasion_tags = data.occasion_tags
    product.fabric = data.fabric
    product.price = data.price
    product.currency = data.currency
    product.brand = data.brand
    product.pattern = data.pattern
    product.status = "active"

    session.add(product)
    await session.flush()  # ensure product.id is available

    # Replace images
    await session.execute(
        ProductImage.__table__.delete().where(ProductImage.product_id == product.id)
    )
    # Add primary image
    if not data.primary_image:
        raise ValueError("Primary image is required")

    img = ProductImage(
        product_id=product.id,
        image_url=str(data.primary_image),
        position=0,
    )
    session.add(img)

    for idx, img_url in enumerate(data.images, start=1):
        img = ProductImage(
            product_id=product.id,
            image_url=str(img_url),
            position=idx,
        )
        session.add(img)

    # Replace variants if any
    if data.variants:
        await session.execute(
            ProductVariant.__table__.delete().where(
                ProductVariant.product_id == product.id
            )
        )
        for v in data.variants:
            variant = ProductVariant(
                product_id=product.id,
                size=v.get("size"),
                sku=v.get("sku"),
                in_stock=v.get("in_stock", True),
                extra=v,
            )
            session.add(variant)

    return product



async def ingest_products(
    session: AsyncSession,
    merchant_id: str,
    products: List[MerchantProductIn],
) -> int:
    """
    Main ingestion entrypoint:
    - Upsert products into tenant Postgres
    - Generate embeddings
    - Index docs into OpenSearch
    """
    ingested_products: List[Product] = []

    logger.info(f"Ingesting {len(products)} products for merchant {merchant_id}")

    for p in products:
        product = await upsert_product(session, p)
        ingested_products.append(product)

    await session.commit()

    logger.info(f"Upserted {len(ingested_products)} products into Postgres for merchant {merchant_id}")
    logger.info(f"Indexing {len(ingested_products)} products into OpenSearch")

    client = get_opensearch_client()
    index_name = get_catalog_index_name(merchant_id)
    ensure_index_exists(client, index_name)

    for product in ingested_products:
        # Get primary image for indexing
        img_q = (
            select(ProductImage)
            .where(ProductImage.product_id == product.id)
            .order_by(ProductImage.position.asc())
            .limit(1)
        )
        img_res = await session.execute(img_q)
        img = img_res.scalar_one_or_none()
        primary_image_url = img.image_url if img else None

        # This call could be moved to a background worker
        await index_product_to_opensearch(
            client=client,
            index_name=index_name,
            product=product,
            primary_image_url=primary_image_url
        )
    logger.info(f"Indexed {len(ingested_products)} products into OpenSearch")

    return len(ingested_products)