from langgraph.graph import StateGraph, END
from app.logger import logger
from app.stylist.state import AgentState
from app.stylist.intents import StylistIntent
from app.stylist.nodes import (
    initialize_node,
    product_search_node,
    generate_response_node,
    profile_update_node,
    small_talk_node,
    try_on_node,
    finalize_node,
    follow_up_node,
)

def route_intent(state: AgentState) -> str:
    """
    Logic for conditional edges. Decides which specialized node to visit
    after initialization based on detected intent.
    """
    intent = state["intent"]
    logger.info(f"[AgentFlow] Routing based on intent: {intent.value}")
    if intent in (StylistIntent.PRODUCT_COMPARISON, StylistIntent.OCCASION_STYLING,
                  StylistIntent.DIRECT_PRODUCT_SEARCH, StylistIntent.GENERAL_STYLING):
        return "product_search"
    elif intent == StylistIntent.PROFILE_UPDATE:
        return "profile_update"
    elif intent in (StylistIntent.SMALL_TALK, StylistIntent.HELP_ABOUT_AISTHETIC):
        return "small_talk"
    elif intent == StylistIntent.TRY_ON_REQUEST:
        return "try_on"
    elif intent == StylistIntent.FOLLOW_UP:
        return "follow_up"
    else:
        logger.warning(f"[AgentFlow] Unknown intent {intent}, falling back to small_talk")
        return "small_talk" # fallback

def create_stylist_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("initialize", initialize_node)
    workflow.add_node("follow_up", follow_up_node)
    workflow.add_node("product_search", product_search_node)
    workflow.add_node("generate_response", generate_response_node)
    workflow.add_node("profile_update", profile_update_node)
    workflow.add_node("small_talk", small_talk_node)
    workflow.add_node("try_on", try_on_node)
    workflow.add_node("finalize", finalize_node)

    workflow.set_entry_point("initialize")

    workflow.add_conditional_edges(
        "initialize",
        route_intent,
        {
            "product_search": "product_search",
            "profile_update": "profile_update",
            "small_talk": "small_talk",
            "try_on": "try_on",
            "follow_up": "follow_up"
        }
    )

    workflow.add_edge("follow_up", "product_search")
    workflow.add_edge("product_search", "generate_response")
    workflow.add_edge("generate_response", "finalize")
    workflow.add_edge("profile_update", "finalize")
    workflow.add_edge("small_talk", "finalize")
    workflow.add_edge("try_on", "finalize")
    workflow.add_edge("finalize", END)

    return workflow.compile()

stylist_agent_app = create_stylist_graph()
