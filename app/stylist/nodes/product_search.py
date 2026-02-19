import json
from app.logger import logger
from app.stylist.query_completion import ChatTurn, complete_stylist_query
from app.stylist.state import AgentState
from app.stylist.nodes.helpers import _search_and_load_products

async def product_search_node(state: AgentState) -> dict:
    """
    Handles search-related intents by querying OpenSearch.
    Uses refined_query from upstream nodes (occasion_styling, follow_up)
    or runs query completion itself (direct_product_search, general_styling).
    """
    merchant_id = state["merchant_id"]
    db_session = state["db_session"]
    message = state["message"]
    chat_context = state["chat_context"]
    search_iteration = state.get("search_iteration", 0)

    user_persona_dict = None
    persona_json = (state["user_preferences"].preferences or {}).get("persona_summary")
    if persona_json:
        try:
            user_persona_dict = json.loads(persona_json)
        except Exception:
            logger.warning("[AgentFlow] Failed to parse persona_json for search")

    logger.info("[AgentFlow] Entering product_search_node")

    # Use refined_query if an upstream node (occasion_styling, follow_up) set it
    upstream_query = state.get("refined_query")
    if upstream_query:
        cq = upstream_query
        query_text = cq.standalone_query or message
    else:
        # Direct product search / general styling — run query completion here
        conversation_window = chat_context.get("conversation_window", [])
        history_turns = [ChatTurn(role=h["role"], message=h["message"]) for h in conversation_window]
        cq = await complete_stylist_query(history_turns, message)
        query_text = cq.standalone_query or message

    excluded = state.get("excluded_product_ids") or []

    candidate_products = await _search_and_load_products(
        merchant_id=merchant_id,
        db_session=db_session,
        completed_query=cq,
        query_text=query_text,
        search_iteration=search_iteration,
        user_persona=user_persona_dict,
        excluded_product_ids=excluded,
    )

    logger.info(f"[AgentFlow] Found {len(candidate_products)} candidate products")
    result: dict = {
        "candidate_products": candidate_products,
        "search_iteration": search_iteration + 1,
    }
    # Pass refined_query to state so trend_enrichment can read web_search_query
    if not upstream_query:
        result["refined_query"] = cq
    return result
