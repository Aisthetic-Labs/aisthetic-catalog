from typing import List
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.dto import CatalogFilter
from app.catalog.models_tenant import Product
from app.stylist.query_completion import CompletedStylistQuery

async def _load_products_by_ids(
        session: AsyncSession,
        product_ids: List[UUID],
) -> List[Product]:
    if not product_ids:
        return []
    q = select(Product).where(Product.id.in_(product_ids))
    res = await session.execute(q)
    return res.scalars().all()


def _serialize_product_for_prompt(p: Product, available_sizes: list[str] | None = None) -> dict:
    result = {
        "id": str(p.id),
        "title": p.title,
        "description": p.description,
        "category": p.category,
        "sub_category": p.sub_category,
        "gender": p.gender,
        "color": p.color_primary,
        "fit": p.fit,
        "style_tags": p.style_tags,
        "occasion_tags": p.occasion_tags,
        "fabric": p.fabric,
        "price": float(p.price),
        "currency": p.currency,
        "brand": p.brand,
        "pattern": p.pattern,
    }
    if available_sizes is not None:
        result["available_sizes"] = available_sizes
    return result


def _filters_from_completed_query(cq: CompletedStylistQuery) -> CatalogFilter:
    price_min = cq.price_min
    price_max = cq.price_max

    color = cq.colors[0] if cq.colors else None
    gender = cq.gender
    category = cq.garment_types[0] if cq.garment_types else None

    sizes = cq.sizes if cq.sizes else None

    return CatalogFilter(
        category=category,
        color=[color] if color else None,
        gender=gender,
        price_min=price_min,
        price_max=price_max,
        sizes=sizes,
    )
