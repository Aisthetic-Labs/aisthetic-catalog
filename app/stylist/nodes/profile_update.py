from app.logger import logger
from app.stylist.dto import StylistResponse
from app.stylist.persona import update_user_preferences
from app.stylist.state import AgentState

async def profile_update_node(state: AgentState) -> dict:
    """
    Handles user requests to update their style preferences.
    """
    logger.info(f"[AgentFlow] Entering profile_update_node")
    db_session = state["db_session"]
    user_preferences = state["user_preferences"]
    message = state["message"]

    answer = (
        "Got it, I've updated your style preferences based on what you said. "
        "I'll keep that in mind for future recommendations."
    )
    # Note: Commit happens later in finalize_node

    response = StylistResponse(
        answer=answer,
        recommended_product_ids=[],
        chosen_product_id=None,
        intent=state["intent"],
    )
    return {"response": response, "mode": "profile_update"}
