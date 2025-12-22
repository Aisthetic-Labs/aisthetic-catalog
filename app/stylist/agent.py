from sqlalchemy.ext.asyncio import AsyncSession
from app.stylist.dto import StylistChatRequest, StylistResponse
from app.stylist.graph import stylist_agent_app

async def handle_stylist_chat(
        merchant_id: str,
        session: AsyncSession,
        req: StylistChatRequest,
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
        "history": req.history,
        "compare_product_ids": req.compare_product_ids,
        "session": session,
        "candidate_products": [],
        "mode": "freeform",
        "is_follow_up": False,
        "excluded_product_ids": [],
        "refined_query": None
    }
    
    # Execute the graph
    final_state = await stylist_agent_app.ainvoke(initial_state)
    
    # Return the StylistResponse object from the state
    return final_state["response"]
