from app.logger import logger
from app.stylist.chat_context import get_chat_context_summarizer
from app.stylist.intents import StylistIntent
from app.stylist.persona import append_user_event
from app.stylist.session_store import get_session_store
from app.stylist.state import AgentState

async def finalize_node(state: AgentState) -> dict:
    """
    The final step: persists user events, commits the transaction,
    updates the chat session history in Redis.
    """
    logger.info(f"[AgentFlow] Entering finalize_node")
    session = state["session"]
    user_profile = state["user_profile"]
    response = state["response"]
    intent = state["intent"]
    mode = state["mode"]
    message = state["message"]
    chat_session_id = state["chat_session_id"]
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
                "chat_session_id": chat_session_id,
                "recommended_product_ids": [str(x) for x in response.recommended_product_ids],
            },
        )

    # 2) Commit all DB changes accumulated in previous nodes
    await session.commit()

    # 3) Update Chat Context in Redis
    chat_context_summarizer = get_chat_context_summarizer()
    await chat_context_summarizer.append_exchange(
        chat_session_id=chat_session_id,
        user_message=message,
        stylist_response=response,
        intent=intent,
        mode=mode,
    )

    # 4) Persist session to Redis
    store = get_session_store()
    session_data = state.get("session_data")
    if session_data is not None:
        session_data["history"].append({"role": "user", "message": message})
        assistant_entry = {"role": "assistant", "message": response.answer}
        if response.recommended_product_ids:
            assistant_entry["recommended_product_ids"] = [
                str(pid) for pid in response.recommended_product_ids
            ]
        session_data["history"].append(assistant_entry)
        await store.save_session(chat_session_id, session_data)

    return {}
