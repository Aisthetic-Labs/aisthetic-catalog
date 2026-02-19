from uuid import UUID

from app.logger import logger
from app.stylist.chat_context import get_chat_context_summarizer
from app.stylist.shortlist_service import get_shortlist_service
from app.stylist.state import AgentState

async def finalize_node(state: AgentState) -> dict:
    """
    The final step: commits the transaction and updates the chat session
    history in Redis.
    """
    logger.info("[AgentFlow] Entering finalize_node")
    db_session = state["db_session"]
    response = state["response"]
    intent = state["intent"]
    message = state["message"]
    chat_session_id = state["chat_session_id"]

    # 1) Commit all DB changes accumulated in previous nodes
    await db_session.commit()

    # 2) Ensure shortlisted_product_ids is populated in every response
    if not response.shortlisted_product_ids:
        shortlist_service = get_shortlist_service()
        shortlist_ids = await shortlist_service.get_all(chat_session_id)
        response.shortlisted_product_ids = [UUID(pid) for pid in shortlist_ids]

    # 3) Update Chat Context in Redis
    chat_context_summarizer = get_chat_context_summarizer()
    await chat_context_summarizer.append_exchange(
        chat_session_id=chat_session_id,
        user_message=message,
        stylist_response=response,
        intent=intent,
    )

    # 4) Store interaction memory to mem0
    from app.stylist.memory_service import store_interaction
    external_user_id = state.get("external_user_id", "")
    if external_user_id:
        await store_interaction(
            user_id=f"{state['merchant_id']}:{external_user_id}",
            messages=[
                {"role": "user", "content": message},
                {"role": "assistant", "content": response.answer},
            ],
        )

    return {}
