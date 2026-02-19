from typing import List
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.dto import CatalogFilter, CatalogSearchRequest
from app.catalog.models_tenant import Product
from app.catalog.search import search_products
from app.logger import logger
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
    return CatalogFilter(
        category=cq.garment_types if cq.garment_types else None,
        color=cq.colors if cq.colors else None,
        gender=cq.gender,
        price_min=cq.price_min,
        price_max=cq.price_max,
        sizes=cq.sizes if cq.sizes else None,
    )


async def _search_and_load_products(
    *,
    merchant_id: str,
    db_session: AsyncSession,
    completed_query: CompletedStylistQuery,
    query_text: str,
    search_iteration: int,
    user_persona: dict | None,
    excluded_product_ids: list[UUID] | None = None,
    limit: int = 20,
) -> list[dict]:
    filters = _filters_from_completed_query(completed_query)

    if search_iteration > 0:
        filters.color = None
        filters.category = None

    search_req = CatalogSearchRequest(
        query_text=query_text,
        filters=filters,
        limit=limit,
        user_persona=user_persona,
        excluded_product_ids=[str(eid) for eid in excluded_product_ids] if excluded_product_ids else None,
    )
    logger.info(f"[AgentFlow] Search request: {search_req}")
    hits = await search_products(merchant_id, search_req)

    ids = [UUID(h["product_id"]) for h in hits]

    sizes_by_id = {h["product_id"]: h.get("available_sizes", []) for h in hits}
    image_by_id = {h["product_id"]: h.get("image_url") for h in hits}
    products = await _load_products_by_ids(db_session, ids)
    serialized = []
    for p in products:
        s = _serialize_product_for_prompt(p, available_sizes=sizes_by_id.get(str(p.id)))
        s["image_url"] = image_by_id.get(str(p.id))
        serialized.append(s)
    return serialized
