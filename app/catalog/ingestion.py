from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from opensearchpy import OpenSearch

from app.catalog.dto import MerchantProductIn
from app.catalog.models_tenant import Product, ProductImage, ProductVariant
from app.catalog.normalization import normalize_color, normalize_fit
from app.catalog.embeddings import embed_text, embed_image_from_url
from app.catalog.opensearch_client import (
    get_opensearch_client,
    get_catalog_index_name,
)


def ensure_index_exists(
    client: OpenSearch,
    index_name: str,
    text_dim: int = 1536,   # OpenAI text embeddings
    image_dim: int = 768,   # CLIP embeddings
) -> None:
    if client.indices.exists(index=index_name):
        return

    body = {
        "settings": {
            "index": {
                "knn": True
            }
        },
        "mappings": {
            "properties": {
                "product_id": {"type": "keyword"},
                "merchant_product_id": {"type": "keyword"},
                "title": {"type": "text"},
                "description": {"type": "text"},
                "category": {"type": "keyword"},
                "sub_category": {"type": "keyword"},
                "gender": {"type": "keyword"},
                "color_primary": {"type": "keyword"},
                "color_secondary": {"type": "keyword"},
                "fit": {"type": "keyword"},
                "style_tags": {"type": "keyword"},
                "occasion_tags": {"type": "keyword"},
                "fabric": {"type": "keyword"},
                "price": {"type": "float"},
                "currency": {"type": "keyword"},
                "brand": {"type": "keyword"},
                "pattern": {"type": "keyword"},
                "status": {"type": "keyword"},
                "image_url": {"type": "keyword"},

                "embedding": {
                    "type": "knn_vector",
                    "dimension": text_dim,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "lucene",
                        "parameters": {"ef_construction": 128, "m": 24},
                    },
                },
                "image_embedding": {
                    "type": "knn_vector",
                    "dimension": image_dim,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "lucene",
                        "parameters": {"ef_construction": 128, "m": 24},
                    },
                },
            }
        },
    }

    client.indices.create(index=index_name, body=body)


def build_full_text_for_embedding(product: Product) -> str:
    """
    Concatenate relevant fields into a single text blob for embeddings.
    """
    parts = [
        product.title,
        product.description or "",
        f"Category: {product.category}/{product.sub_category or ''}",
        f"Color: {product.color_primary}",
        f"Fit: {product.fit}",
        f"Style: {', '.join(product.style_tags or [])}",
        f"Occasion: {', '.join(product.occasion_tags or [])}",
        f"Pattern: {product.pattern or ''}",
        f"Fabric: {product.fabric or ''}",
        f"Brand: {product.brand or ''}",
    ]
    return ". ".join([p for p in parts if p])


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

async def build_search_doc(session: AsyncSession, product: Product) -> dict:
    # Consider only the primary image (position=0) for embedding
    img_q = (
        select(ProductImage)
        .where(ProductImage.product_id == product.id)
        .order_by(ProductImage.position.asc())
        .limit(1)
    )
    res = await session.execute(img_q)
    img = res.scalar_one_or_none()

    full_text = build_full_text_for_embedding(product)
    text_embedding = await embed_text(full_text)

    image_embedding = None
    if img and img.image_url:
        image_embedding = await embed_image_from_url(img.image_url)

    doc = {
        "product_id": str(product.id),
        "merchant_product_id": product.merchant_product_id,
        "title": product.title,
        "description": product.description,
        "category": product.category,
        "sub_category": product.sub_category,
        "gender": product.gender,
        "color_primary": product.color_primary,
        "color_secondary": product.color_secondary,
        "fit": product.fit,
        "style_tags": product.style_tags,
        "occasion_tags": product.occasion_tags,
        "fabric": product.fabric,
        "price": float(product.price),
        "currency": product.currency,
        "brand": product.brand,
        "pattern": product.pattern,
        "status": product.status,
        "image_url": img.image_url if img else None,
        "embedding": text_embedding,
    }

    # Only index image_embedding if present
    if image_embedding is not None:
        doc["image_embedding"] = image_embedding

    return doc


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

    for p in products:
        product = await upsert_product(session, p)
        ingested_products.append(product)

    await session.commit()

    client = get_opensearch_client()
    index_name = get_catalog_index_name(merchant_id)
    ensure_index_exists(client, index_name)

    for product in ingested_products:
        doc = await build_search_doc(session, product)
        client.index(
            index=index_name,
            id=doc["product_id"],
            body=doc,
            refresh=True,  # dev mode; optimize later
        )

    return len(ingested_products)