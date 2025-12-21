from uuid import UUID
from app.catalog.dto import CatalogSearchRequest
from app.catalog.search import search_products
from app.logger import logger
from app.stylist.dto import ChatTurn
from app.stylist.intents import StylistIntent
from app.stylist.query_completion import complete_stylist_query
from app.stylist.state import AgentState
from app.stylist.nodes.helpers import (
    _load_products_by_ids,
    _serialize_product_for_prompt,
    _filters_from_completed_query,
)

async def product_search_node(state: AgentState) -> dict:
    """
    Handles search-related intents by querying OpenSearch.
    This node is only visited if the intent requires product candidates.
    """
    intent = state["intent"]
    merchant_id = state["merchant_id"]
    session = state["session"]
    message = state["message"]
    history = state["history"]
    compare_product_ids = state["compare_product_ids"]
    
    logger.info(f"[AgentFlow] Entering product_search_node for intent: {intent.value}")
    
    candidate_products = []
    mode = "freeform"
    
    # Prepare history for query completion LLM
    history_turns = [ChatTurn(role=h.role, message=h.message) for h in history]

    # --- Routing by intent within search node ---
    if intent == StylistIntent.PRODUCT_COMPARISON:
        mode = "compare"
        if not compare_product_ids:
            # If no IDs provided, use LLM to extract a search query and filter
            cq = await complete_stylist_query(history_turns, message)
            filters = _filters_from_completed_query(cq)
            search_req = CatalogSearchRequest(
                query_text=cq.standalone_query or message,
                filters=filters,
                limit=4,
            )
            logger.info(f"[AgentFlow] Product comparison search req: {search_req}")
            search_hits = await search_products(merchant_id, search_req)
            compare_ids = [UUID(h["product_id"]) for h in search_hits[:2]]
        else:
            compare_ids = compare_product_ids

        products = await _load_products_by_ids(session, compare_ids)
        candidate_products = [_serialize_product_for_prompt(p) for p in products]

    elif intent == StylistIntent.OCCASION_STYLING:
        mode = "occasion"
        # Extract occasion and filters via LLM
        cq = await complete_stylist_query(history_turns, message)
        filters = _filters_from_completed_query(cq)
        query_text = cq.standalone_query or f"outfit for {cq.occasion or message}"
        search_req = CatalogSearchRequest(
            query_text=query_text,
            filters=filters,
            limit=20,
        )
        logger.info(f"[AgentFlow] Occasion styling search req: {search_req}")
        hits = await search_products(merchant_id, search_req)
        ids = [UUID(h["product_id"]) for h in hits]
        products = await _load_products_by_ids(session, ids)
        candidate_products = [_serialize_product_for_prompt(p) for p in products]

    elif intent in (StylistIntent.DIRECT_PRODUCT_SEARCH, StylistIntent.GENERAL_STYLING):
        mode = "freeform"
        # Standard product discovery
        cq = await complete_stylist_query(history_turns, message)
        filters = _filters_from_completed_query(cq)
        search_req = CatalogSearchRequest(
            query_text=cq.standalone_query or message,
            filters=filters,
            limit=20,
        )
        logger.info(f"[AgentFlow] Direct/General styling search req: {search_req}")
        hits = await search_products(merchant_id, search_req)
        ids = [UUID(h["product_id"]) for h in hits]
        products = await _load_products_by_ids(session, ids)
        candidate_products = [_serialize_product_for_prompt(p) for p in products]

    logger.info(f"[AgentFlow] Found {len(candidate_products)} candidate products")
    return {"candidate_products": candidate_products, "mode": mode}
