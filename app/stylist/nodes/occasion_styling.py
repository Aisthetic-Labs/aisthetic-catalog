from app.logger import logger
from app.stylist.dto import StylistResponse, QuickReply
from app.stylist.intents import StylistIntent
from app.stylist.query_completion import ChatTurn, complete_stylist_query
from app.stylist.state import AgentState


OCCASION_QUICK_REPLIES = [
    QuickReply(label="Wedding", payload={"value": "wedding"}),
    QuickReply(label="Date Night", payload={"value": "date night"}),
    QuickReply(label="Office / Work", payload={"value": "office"}),
    QuickReply(label="Party / Night Out", payload={"value": "party"}),
    QuickReply(label="Vacation / Travel", payload={"value": "vacation"}),
    QuickReply(label="Casual Outing", payload={"value": "casual outing"}),
]


async def occasion_styling_node(state: AgentState) -> dict:
    """
    Handles OCCASION_STYLING intent. Extracts the occasion from the user's
    message via query completion. If the occasion is unclear, asks the user
    before proceeding to product search.
    """
    logger.info("[AgentFlow] Entering occasion_styling_node")
    message = state["message"]
    chat_context = state["chat_context"]

    # Build history turns from conversation window
    conversation_window = chat_context.get("conversation_window", [])
    history_turns = [ChatTurn(role=h["role"], message=h["message"]) for h in conversation_window]

    cq = await complete_stylist_query(history_turns, message)

    if not cq.occasion:
        # Occasion is unclear — ask the user
        logger.info("[AgentFlow] Occasion unclear, asking user for clarification")
        return {
            "response": StylistResponse(
                answer="What occasion are you dressing up for?",
                intent=StylistIntent.OCCASION_STYLING,
                quick_replies=OCCASION_QUICK_REPLIES,
            ),
        }

    # Occasion is clear — prepare query for product search
    logger.info(f"[AgentFlow] Occasion identified: {cq.occasion}")
    cq.standalone_query = cq.standalone_query or f"outfit for {cq.occasion}"

    return {
        "refined_query": cq,
    }
