from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from app.stylist.dto import StylistChatRequest, StylistResponse
from app.stylist.graph import stylist_agent_app


async def handle_stylist_chat(
        merchant_id: str,
        db_session: AsyncSession,
        req: StylistChatRequest,
        chat_session_id: str,
        chat_session_data: dict[str, Any] | None = None,
) -> StylistResponse:
    """
    Main entrypoint for the Stylist Agent.
    Invokes the LangGraph workflow with initial inputs.
    """

    # Initialize the input state
    initial_state = {
        "merchant_id": merchant_id,
        "external_user_id": req.external_user_id,
        "message": req.message,
        "chat_session_id": chat_session_id,
        "chat_session_data": chat_session_data,
        "compare_product_ids": req.compare_product_ids,
        "db_session": db_session,
        "candidate_products": [],
        "mode": "freeform",
        "is_follow_up": False,
        "excluded_product_ids": [],
        "refined_query": None
    }

    # Execute the graph
    final_state = await stylist_agent_app.ainvoke(initial_state)

    # Return the StylistResponse object from the state
    response: StylistResponse = final_state["response"]
    response.chat_session_id = chat_session_id
    return response
