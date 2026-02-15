from app.logger import logger
from app.stylist.dto import StylistResponse
from app.stylist.persona import append_user_event
from app.stylist.state import AgentState

async def try_on_node(state: AgentState) -> dict:
    """
    Handoff for virtual try-on requests. (Future functionality)
    """
    logger.info(f"[AgentFlow] Entering try_on_node")
    db_session = state["db_session"]
    user_profile = state["user_profile"]
    message = state["message"]
    
    answer = (
        "I can help you choose what to try, and soon I’ll be able to show it on you. "
        "For now, tell me which product you’re looking at and I’ll style it for you."
    )
    await append_user_event(
        db_session,
        user_profile,
        event_type="try_on_request",
        product_id=None,
        context={"message": message},
    )
    
    response = StylistResponse(
        answer=answer,
        recommended_product_ids=[],
        chosen_product_id=None,
        intent=state["intent"],
    )
    return {"response": response, "mode": "try_on_request"}
