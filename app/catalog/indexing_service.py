from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from opensearchpy import OpenSearch

from app.catalog.models_tenant import Product, ProductImage, ProductVariant
from app.catalog.embeddings import embed_text, embed_image_from_url
from app.catalog.opensearch_client import get_opensearch_client, get_catalog_index_name
from app.logger import logger

def ensure_index_exists(
    client: OpenSearch,
    index_name: str,
    text_dim: int = 1536,
    image_dim: int = 768,
) -> None:
    if client.indices.exists(index=index_name):
        return

    body = {
        "settings": {"index": {"knn": True}},
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
                "available_sizes": {"type": "keyword"},
                "has_stock": {"type": "boolean"},
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
    desc = ""
    if product.meta_data:
        meta_parts = [f"{k}: {v}" for k, v in product.meta_data.items()]
        meta_text = ". ".join(meta_parts)
        desc = f"{product.description or ''}. {meta_text}"
    parts = [
        product.title,
        desc,
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

async def index_product_to_opensearch(
    client: OpenSearch,
    index_name: str,
    product: Product,
    primary_image_url: str | None,
    variants: list[ProductVariant] | None = None,
):
    full_text = build_full_text_for_embedding(product)
    text_embedding = await embed_text(full_text)
    
    image_embedding = None
    if primary_image_url:
        image_embedding = await embed_image_from_url(primary_image_url)

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
        "image_url": primary_image_url,
        "embedding": text_embedding,
    }

    # Derive size/stock fields from variants
    if variants:
        available_sizes = [v.size for v in variants if v.in_stock and v.size]
        has_stock = any(v.in_stock for v in variants)
    else:
        # No variant data — assume product is available
        available_sizes = []
        has_stock = True

    doc["available_sizes"] = available_sizes
    doc["has_stock"] = has_stock

    if image_embedding is not None:
        doc["image_embedding"] = image_embedding

    client.index(
        index=index_name,
        id=doc["product_id"],
        body=doc,
        refresh=True,
    )
