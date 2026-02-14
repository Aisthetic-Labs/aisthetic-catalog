import json
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
    persona_json = state.get("persona_json")
    
    # Follow-up related fields
    is_follow_up = state.get("is_follow_up", False)
    refined_query = state.get("refined_query")
    excluded_product_ids = state.get("excluded_product_ids", [])
    search_iteration = state.get("search_iteration", 0)
    
    user_persona_dict = None
    if persona_json:
        try:
            user_persona_dict = json.loads(persona_json)
        except Exception:
            logger.warning("[AgentFlow] Failed to parse persona_json for search")

    logger.info(f"[AgentFlow] Entering product_search_node for intent: {intent.value} (follow_up={is_follow_up})")
    
    candidate_products = []
    mode = "freeform"
    
    # Prepare history for query completion LLM
    history_turns = [ChatTurn(role=h.role, message=h.message) for h in history]

    # --- Routing by intent within search node ---
    if intent == StylistIntent.FOLLOW_UP and refined_query:
        # For follow-ups, we use the refined query from follow_up_node
        filters = _filters_from_completed_query(refined_query)
        
        # Agentic Refinement: Broaden search if it's a re-attempt
        if search_iteration > 0:
            logger.info(f"[AgentFlow] Broadening search for follow-up (iteration {search_iteration})")
            filters.color = [] # drop color constraint
            filters.category = None # broaden category

        search_req = CatalogSearchRequest(
            query_text=refined_query.standalone_query or message,
            filters=filters,
            limit=20 + len(excluded_product_ids), # fetch more to allow exclusion
            user_persona=user_persona_dict
        )
        logger.info(f"[AgentFlow] Follow-up search req: {search_req}")
        hits = await search_products(merchant_id, search_req)

        # Filter out already seen products
        ids = []
        excluded_strs = [str(eid) for eid in excluded_product_ids]
        for h in hits:
            if h["product_id"] not in excluded_strs:
                ids.append(UUID(h["product_id"]))
            if len(ids) >= 20: # maintain limit after exclusion
                break

        sizes_by_id = {h["product_id"]: h.get("available_sizes", []) for h in hits}
        products = await _load_products_by_ids(session, ids)
        candidate_products = [_serialize_product_for_prompt(p, available_sizes=sizes_by_id.get(str(p.id))) for p in products]

    elif intent == StylistIntent.PRODUCT_COMPARISON:
        mode = "compare"
        if not compare_product_ids:
            # If no IDs provided, use LLM to extract a search query and filter
            cq = await complete_stylist_query(history_turns, message)
            filters = _filters_from_completed_query(cq)
            if search_iteration > 0:
                filters.color = []
                filters.category = None
            search_req = CatalogSearchRequest(
                query_text=cq.standalone_query or message,
                filters=filters,
                limit=4,
                user_persona=user_persona_dict
            )
            logger.info(f"[AgentFlow] Product comparison search req: {search_req}")
            search_hits = await search_products(merchant_id, search_req)
            compare_ids = [UUID(h["product_id"]) for h in search_hits[:2]]
            sizes_by_id = {h["product_id"]: h.get("available_sizes", []) for h in search_hits}
        else:
            compare_ids = compare_product_ids
            sizes_by_id = {}

        products = await _load_products_by_ids(session, compare_ids)
        candidate_products = [_serialize_product_for_prompt(p, available_sizes=sizes_by_id.get(str(p.id))) for p in products]

    elif intent == StylistIntent.OCCASION_STYLING:
        mode = "occasion"
        # Extract occasion and filters via LLM
        cq = await complete_stylist_query(history_turns, message)
        filters = _filters_from_completed_query(cq)
        if search_iteration > 0:
            filters.color = []
            filters.category = None
        query_text = cq.standalone_query or f"outfit for {cq.occasion or message}"
        search_req = CatalogSearchRequest(
            query_text=query_text,
            filters=filters,
            limit=20,
            user_persona=user_persona_dict
        )
        logger.info(f"[AgentFlow] Occasion styling search req: {search_req}")
        hits = await search_products(merchant_id, search_req)
        ids = [UUID(h["product_id"]) for h in hits]
        sizes_by_id = {h["product_id"]: h.get("available_sizes", []) for h in hits}
        products = await _load_products_by_ids(session, ids)
        candidate_products = [_serialize_product_for_prompt(p, available_sizes=sizes_by_id.get(str(p.id))) for p in products]

    elif intent in (StylistIntent.DIRECT_PRODUCT_SEARCH, StylistIntent.GENERAL_STYLING):
        mode = "freeform"
        # Standard product discovery
        cq = await complete_stylist_query(history_turns, message)
        filters = _filters_from_completed_query(cq)
        if search_iteration > 0:
            filters.color = []
            filters.category = None
        search_req = CatalogSearchRequest(
            query_text=cq.standalone_query or message,
            filters=filters,
            limit=20,
            user_persona=user_persona_dict
        )
        logger.info(f"[AgentFlow] Direct/General styling search req: {search_req}")
        hits = await search_products(merchant_id, search_req)
        ids = [UUID(h["product_id"]) for h in hits]
        sizes_by_id = {h["product_id"]: h.get("available_sizes", []) for h in hits}
        products = await _load_products_by_ids(session, ids)
        candidate_products = [_serialize_product_for_prompt(p, available_sizes=sizes_by_id.get(str(p.id))) for p in products]

    logger.info(f"[AgentFlow] Found {len(candidate_products)} candidate products")
    return {
        "candidate_products": candidate_products,
        "mode": mode,
        "search_iteration": search_iteration + 1
    }
