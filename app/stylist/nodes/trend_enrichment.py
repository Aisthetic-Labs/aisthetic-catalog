from app.logger import logger
from app.stylist.state import AgentState


async def trend_enrichment_node(state: AgentState) -> dict:
    """
    Conditional web search node that runs between product_search and
    generate_response. Only triggers when query_completion determined
    that a web search would help (non-null web_search_query).
    """
    logger.info("[AgentFlow] Entering trend_enrichment_node")

    refined_query = state.get("refined_query")
    web_search_query = (
        getattr(refined_query, "web_search_query", None)
        if refined_query
        else None
    )

    if not web_search_query:
        logger.info("[AgentFlow] No web_search_query, skipping trend enrichment")
        return {"trend_context": None}

    from app.stylist.web_search_service import search_fashion_context

    trend_context = await search_fashion_context(web_search_query)
    logger.info(
        f"[AgentFlow] Trend enrichment {'found context' if trend_context else 'no results'}"
    )
    return {"trend_context": trend_context}
