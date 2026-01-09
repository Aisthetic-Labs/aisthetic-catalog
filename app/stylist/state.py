from typing import List, Optional, Annotated, TypedDict
from uuid import UUID
import operator
from sqlalchemy.ext.asyncio import AsyncSession
from app.stylist.dto import ChatTurn, StylistResponse
from app.stylist.intents import StylistIntent
from app.stylist.query_completion import CompletedStylistQuery


class AgentState(TypedDict):
    """
    Represents the state of the Stylist Agent during a single chat request.
    This state is passed between LangGraph nodes.
    """
    # --- Input Fields ---
    merchant_id: str
    external_user_id: str
    message: str
    history: List[ChatTurn]
    compare_product_ids: Optional[List[UUID]]
    
    # --- Internal Work State ---
    session: AsyncSession  # Active DB session
    persona_json: Optional[str]  # Serialized user persona context
    intent: Optional[StylistIntent]  # Detected intent (e.g., product_search)
    chat_context: Optional[dict]  # Structured conversation history & summary
    # Annotated with operator.add to allow multiple nodes to contribute products
    candidate_products: Annotated[List[dict], operator.add]
    search_iteration: int  # Tracking number of search attempts
    mode: str  # Current behavior mode (freeform, compare, occasion)
    user_profile: Optional[any]  # UserProfile model instance
    
    # --- Follow-up and Context Fields ---
    is_follow_up: bool  # Whether current message is a follow-up
    refined_query: Optional[CompletedStylistQuery]  # Merged query for follow-ups
    excluded_product_ids: List[UUID]  # IDs to exclude from search results
    
    # --- Output Fields ---
    response: Optional[StylistResponse]  # Final response returned to API
