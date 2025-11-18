from typing import List, Dict, Any

from app.catalog.dto import CatalogSearchRequest, ImageSearchRequest
from app.catalog.opensearch_client import get_opensearch_client, get_catalog_index_name
from app.catalog.embeddings import embed_text, embed_image_from_url


async def search_products(
    merchant_id: str,
    req: CatalogSearchRequest,
) -> List[Dict[str, Any]]:
    client = get_opensearch_client()
    index_name = get_catalog_index_name(merchant_id)

    if not client.indices.exists(index=index_name):
        return []

    # --- Build filter clauses ---
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

    # --- Semantic + filtered search (Lucene knn with filter) ---
    if req.query_text:
        query_vector = await embed_text(req.query_text)

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
                    "embedding": knn_field_obj
                }
            },
        }

    # --- Pure filter-only search (no query_text) ---
    else:
        body = {
            "size": req.limit,
            "sort": [{"_id": "desc"}],
            "query": {
                "bool": {
                    "filter": filter_clauses or [{"match_all": {}}],
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
            }
        )

    return results