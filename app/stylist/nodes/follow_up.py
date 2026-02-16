import json
from app.logger import logger
from app.stylist.query_completion import ChatTurn, complete_stylist_query, CompletedStylistQuery
from app.stylist.state import AgentState

async def follow_up_node(state: AgentState) -> dict:
    """
    Handles follow-up questions by merging current message with conversation history.
    Decides if it's a refinement (new filters) or a request for more products.
    """
    logger.info("[AgentFlow] Entering follow_up_node")
    message = state["message"]
    chat_context = state["chat_context"]

    # Build history turns from backend-managed conversation window
    conversation_window = chat_context.get("conversation_window", [])

    # Extract excluded product IDs from conversation window (previously recommended)
    excluded_ids = [
        pid
        for entry in conversation_window
        if entry.get("role") == "assistant"
        for pid in entry.get("recommended_product_ids") or []
    ]
    history_turns = [ChatTurn(role=h["role"], message=h["message"]) for h in conversation_window]
    
    # Use complete_stylist_query to get a merged standalone query and filters
    # This naturally handles "show more" or "in blue" by looking at history
    refined_query = await complete_stylist_query(history_turns, message)
    
    logger.info(f"[AgentFlow] Refined follow-up query: {refined_query.standalone_query}")
    
    return {
        "refined_query": refined_query,
        "excluded_product_ids": excluded_ids,
        "is_follow_up": True
    }
