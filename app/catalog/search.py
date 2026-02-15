from typing import List, Dict, Any

from app.catalog.dto import CatalogSearchRequest, ImageSearchRequest
from app.catalog.opensearch_client import get_opensearch_client, get_catalog_index_name
from app.catalog.embeddings import embed_text, embed_image_from_url
from app.logger import logger


def _build_filter_clauses(filters, user_persona: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    clauses = []
    
    # 1) Category (from explicit filters)
    if filters.category:
        clauses.append({"term": {"category": filters.category}})

    # 2) Color (explicit filter OR persona preferred, minus avoid)
    final_colors = filters.color or []
    if not final_colors and user_persona and user_persona.get("preferred_colors"):
        # Respect ordering: preferred_colors is already ordered by user preference
        final_colors = user_persona["preferred_colors"]
    
    if final_colors:
        # If we have avoid_colors, remove them from the list if they were added via persona
        avoid_colors = user_persona.get("avoid_colors", []) if user_persona else []
        final_colors = [c for c in final_colors if c not in avoid_colors]
        if final_colors:
            clauses.append({"terms": {"color_primary": final_colors}})
    elif user_persona and user_persona.get("avoid_colors"):
        # Even if no preferred color, we should avoid specific ones
        clauses.append({"bool": {"must_not": {"terms": {"color_primary": user_persona["avoid_colors"]}}}})

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

    # 6) Size filter (explicit or from persona)
    size_filter = filters.sizes or []
    if not size_filter and user_persona and user_persona.get("preferred_sizes"):
        size_filter = user_persona["preferred_sizes"]
    if size_filter:
        clauses.append({"terms": {"available_sizes": size_filter}})

    # 7) Fits and Style Vibes (from persona)
    if user_persona:
        if user_persona.get("preferred_fits"):
            clauses.append({"terms": {"fit": user_persona["preferred_fits"]}})
        if user_persona.get("style_vibes"):
            clauses.append({"terms": {"style_tags": user_persona["style_vibes"]}})

    return clauses


def _build_search_body(
    filter_clauses: List[Dict[str, Any]],
    limit: int,
    query_vector: List[float] | None = None,
) -> Dict[str, Any]:
    """Build an OpenSearch request body for either kNN or filter-only search."""
    if query_vector is not None:
        knn_field_obj: Dict[str, Any] = {"vector": query_vector, "k": limit}
        if filter_clauses:
            knn_field_obj["filter"] = {"bool": {"filter": filter_clauses}}
        return {
            "size": limit,
            "query": {"knn": {"embedding": knn_field_obj}},
        }
    return {
        "size": limit,
        "sort": [{"_id": "desc"}],
        "query": {"bool": {"filter": filter_clauses or [{"match_all": {}}]}},
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

    query_text = req.query_text
    query_vector = await embed_text(query_text) if query_text else None

    # Try with persona filters first
    filter_clauses = _build_filter_clauses(req.filters, req.user_persona)
    logger.info(f"[Search] Built filters: {filter_clauses}")
    body = _build_search_body(filter_clauses, req.limit, query_vector)
    res = client.search(index=index_name, body=body)

    # Fallback 1: drop persona filters
    if _hit_count(res) == 0 and req.user_persona:
        logger.info("[Search] No results with persona filters, falling back to basic filters")
        basic_filters = _build_filter_clauses(req.filters, None)
        body = _build_search_body(basic_filters, req.limit, query_vector)
        res = client.search(index=index_name, body=body)

    # Fallback 2: also drop size filter
    has_sizes = req.filters.sizes or (req.user_persona and req.user_persona.get("preferred_sizes"))
    if _hit_count(res) == 0 and has_sizes:
        logger.info("[Search] No results with size filter, falling back without size constraint")
        relaxed_filters = req.filters.model_copy(update={"sizes": None})
        size_relaxed_clauses = _build_filter_clauses(relaxed_filters, None)
        body = _build_search_body(size_relaxed_clauses, req.limit, query_vector)
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
        filter_clauses.append({"term": {"category": req.filters.category}})

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