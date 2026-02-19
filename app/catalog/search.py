from typing import List, Dict, Any

from app.catalog.dto import CatalogSearchRequest, ImageSearchRequest
from app.catalog.opensearch_client import get_opensearch_client, get_catalog_index_name
from app.catalog.embeddings import embed_text, embed_image_from_url
from app.logger import logger


def _build_filter_clauses(filters) -> List[Dict[str, Any]]:
    """Build hard filter clauses from explicit user filters only (no persona)."""
    clauses = []

    # 1) Category (explicit)
    if filters.category:
        clauses.append({"terms": {"category": filters.category}})

    # 2) Color (explicit from user query only)
    if filters.color:
        clauses.append({"terms": {"color_primary": filters.color}})

    # 3) Gender
    if filters.gender:
        clauses.append({"term": {"gender": filters.gender}})

    # 4) Price
    if filters.price_min is not None or filters.price_max is not None:
        price_range: Dict[str, Any] = {}
        if filters.price_min is not None:
            price_range["gte"] = filters.price_min
        if filters.price_max is not None:
            price_range["lte"] = filters.price_max
        clauses.append({"range": {"price": price_range}})

    # 5) Stock filter — default to in-stock only
    if not filters.include_out_of_stock:
        clauses.append({"term": {"has_stock": True}})

    # 6) Size filter (explicit from user query only)
    if filters.sizes:
        clauses.append({"terms": {"available_sizes": filters.sizes}})

    return clauses


def _build_persona_query_boost(user_persona: dict | None) -> str:
    """Build a text suffix from persona preferences for semantic ranking."""
    if not user_persona:
        return ""
    parts = []
    if user_persona.get("preferred_colors"):
        parts.append(f"preferred colors: {', '.join(user_persona['preferred_colors'])}")
    if user_persona.get("preferred_fits"):
        parts.append(f"preferred fit: {', '.join(user_persona['preferred_fits'])}")
    if user_persona.get("style_vibes"):
        parts.append(f"style: {', '.join(user_persona['style_vibes'])}")
    if user_persona.get("preferred_sizes"):
        parts.append(f"sizes: {', '.join(user_persona['preferred_sizes'])}")
    return "; ".join(parts)


def _build_search_body(
    filter_clauses: List[Dict[str, Any]],
    limit: int,
    query_vector: List[float] | None = None,
    must_not_clauses: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Build an OpenSearch request body for either kNN or filter-only search."""
    if query_vector is not None:
        knn_field_obj: Dict[str, Any] = {"vector": query_vector, "k": limit}
        if filter_clauses or must_not_clauses:
            bool_filter: Dict[str, Any] = {}
            if filter_clauses:
                bool_filter["filter"] = filter_clauses
            if must_not_clauses:
                bool_filter["must_not"] = must_not_clauses
            knn_field_obj["filter"] = {"bool": bool_filter}
        return {
            "size": limit,
            "query": {"knn": {"embedding": knn_field_obj}},
        }
    bool_query: Dict[str, Any] = {"filter": filter_clauses or [{"match_all": {}}]}
    if must_not_clauses:
        bool_query["must_not"] = must_not_clauses
    return {
        "size": limit,
        "sort": [{"_id": "desc"}],
        "query": {"bool": bool_query},
    }


def _hit_count(res: Dict[str, Any]) -> int:
    return res.get("hits", {}).get("total", {}).get("value", 0)


async def search_products(
    merchant_id: str,
    req: CatalogSearchRequest,
) -> List[Dict[str, Any]]:
    client = get_opensearch_client()
    index_name = get_catalog_index_name(merchant_id)

    if not client.indices.exists(index=index_name):
        return []

    # Enrich query with persona preferences for soft semantic ranking
    query_text = req.query_text
    persona_boost = _build_persona_query_boost(req.user_persona)
    enriched_query = f"{query_text} — {persona_boost}" if query_text and persona_boost else query_text
    query_vector = await embed_text(enriched_query) if enriched_query else None

    # Build must_not for excluded product IDs + avoid_colors
    must_not_clauses: List[Dict[str, Any]] = []
    if req.excluded_product_ids:
        must_not_clauses.append({"ids": {"values": req.excluded_product_ids}})
    if req.user_persona and req.user_persona.get("avoid_colors"):
        must_not_clauses.append({"terms": {"color_primary": req.user_persona["avoid_colors"]}})

    effective_must_not = must_not_clauses or None

    # Primary search with hard filters only (persona is in query embedding)
    filter_clauses = _build_filter_clauses(req.filters)
    logger.info(f"[Search] Built filters: {filter_clauses}")
    body = _build_search_body(filter_clauses, req.limit, query_vector, effective_must_not)
    res = client.search(index=index_name, body=body)

    # Fallback 1: drop size filter
    if _hit_count(res) == 0 and req.filters.sizes:
        logger.info("[Search] No results with size filter, falling back without size constraint")
        relaxed_filters = req.filters.model_copy(update={"sizes": None})
        size_relaxed_clauses = _build_filter_clauses(relaxed_filters)
        body = _build_search_body(size_relaxed_clauses, req.limit, query_vector, effective_must_not)
        res = client.search(index=index_name, body=body)

    # Fallback 2: also drop category filter
    if _hit_count(res) == 0 and req.filters.category:
        logger.info("[Search] No results with category filter, falling back without category")
        relaxed_filters = req.filters.model_copy(update={"sizes": None, "category": None})
        cat_relaxed_clauses = _build_filter_clauses(relaxed_filters)
        body = _build_search_body(cat_relaxed_clauses, req.limit, query_vector, effective_must_not)
        res = client.search(index=index_name, body=body)

    hits = res.get("hits", {}).get("hits", [])

    results: List[Dict[str, Any]] = []
    for h in hits:
        src = h["_source"]
        results.append(
            {
                "product_id": src["product_id"],
                "title": src["title"],
                "price": src["price"],
                "currency": src["currency"],
                "image_url": src.get("image_url"),
                "color": src.get("color_primary"),
                "brand": src.get("brand"),
                "available_sizes": src.get("available_sizes", []),
            }
        )

    return results


async def search_products_by_image(
    merchant_id: str,
    req: ImageSearchRequest,
) -> List[Dict[str, Any]]:
    client = get_opensearch_client()
    index_name = get_catalog_index_name(merchant_id)

    if not client.indices.exists(index=index_name):
        return []

    # 🔥 get image embedding for query
    query_vector = await embed_image_from_url(str(req.image_url))
    if query_vector is None:
        # Image embeddings not wired yet
        raise RuntimeError(
            "Image embeddings not implemented. Implement embed_image_from_url() first."
        )

    # Build optional filters
    filter_clauses: List[Dict[str, Any]] = []

    if req.filters.category:
        filter_clauses.append({"terms": {"category": req.filters.category}})

    if req.filters.color:
        filter_clauses.append({"terms": {"color_primary": req.filters.color}})

    if req.filters.gender:
        filter_clauses.append({"term": {"gender": req.filters.gender}})

    if req.filters.price_min is not None or req.filters.price_max is not None:
        price_range: Dict[str, Any] = {}
        if req.filters.price_min is not None:
            price_range["gte"] = req.filters.price_min
        if req.filters.price_max is not None:
            price_range["lte"] = req.filters.price_max
        filter_clauses.append({"range": {"price": price_range}})

    if not req.filters.include_out_of_stock:
        filter_clauses.append({"term": {"has_stock": True}})

    if req.filters.sizes:
        filter_clauses.append({"terms": {"available_sizes": req.filters.sizes}})

    knn_field_obj: Dict[str, Any] = {
        "vector": query_vector,
        "k": req.limit,
    }

    if filter_clauses:
        knn_field_obj["filter"] = {
            "bool": {
                "filter": filter_clauses
            }
        }

    body = {
        "size": req.limit,
        "query": {
            "knn": {
                "image_embedding": knn_field_obj
            }
        },
    }

    res = client.search(index=index_name, body=body)
    hits = res.get("hits", {}).get("hits", [])

    results: List[Dict[str, Any]] = []
    for h in hits:
        src = h["_source"]
        results.append(
            {
                "product_id": src["product_id"],
                "title": src["title"],
                "price": src["price"],
                "currency": src["currency"],
                "image_url": src.get("image_url"),
                "available_sizes": src.get("available_sizes", []),
            }
        )

    return results