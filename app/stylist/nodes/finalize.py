from app.logger import logger
from app.stylist.chat_context import get_chat_context_summarizer
from app.stylist.state import AgentState

async def finalize_node(state: AgentState) -> dict:
    """
    The final step: commits the transaction and updates the chat session
    history in Redis.
    """
    logger.info(f"[AgentFlow] Entering finalize_node")
    db_session = state["db_session"]
    response = state["response"]
    intent = state["intent"]
    message = state["message"]
    chat_session_id = state["chat_session_id"]

    # 1) Commit all DB changes accumulated in previous nodes
    await db_session.commit()

    # 2) Update Chat Context in Redis
    chat_context_summarizer = get_chat_context_summarizer()
    await chat_context_summarizer.append_exchange(
        chat_session_id=chat_session_id,
        user_message=message,
        stylist_response=response,
        intent=intent,
    )

    return {}
