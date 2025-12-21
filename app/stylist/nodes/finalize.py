from app.logger import logger
from app.stylist.chat_context import get_chat_context_summarizer
from app.stylist.intents import StylistIntent
from app.stylist.persona import append_user_event
from app.stylist.state import AgentState

async def finalize_node(state: AgentState) -> dict:
    """
    The final step: persists user events, commits the transaction,
    and updates the chat session history in Redis.
    """
    logger.info(f"[AgentFlow] Entering finalize_node")
    session = state["session"]
    user_profile = state["user_profile"]
    response = state["response"]
    intent = state["intent"]
    mode = state["mode"]
    message = state["message"]
    merchant_id = state["merchant_id"]
    external_user_id = state["external_user_id"]
    
    # 1) Log the primary event for product discovery intents
    if intent in (StylistIntent.PRODUCT_COMPARISON, StylistIntent.OCCASION_STYLING,
                  StylistIntent.DIRECT_PRODUCT_SEARCH, StylistIntent.GENERAL_STYLING):
        await append_user_event(
            session,
            user_profile,
            event_type="stylist_question",
            product_id=response.chosen_product_id,
            context={
                "intent": intent.value,
                "mode": mode,
                "message": message,
                "recommended_product_ids": [str(x) for x in response.recommended_product_ids],
            },
        )
    
    # 2) Commit all DB changes accumulated in previous nodes
    await session.commit()

    # 3) Update Chat Context in Redis
    chat_context_summarizer = get_chat_context_summarizer()
    await chat_context_summarizer.append_exchange(
        merchant_id=merchant_id,
        external_user_id=external_user_id,
        user_message=message,
        stylist_response=response,
        intent=intent,
        mode=mode,
    )
    
    return {}
