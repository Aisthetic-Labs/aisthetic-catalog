from typing import List, Optional, Annotated, TypedDict
from uuid import UUID
import operator
from sqlalchemy.ext.asyncio import AsyncSession
from app.stylist.dto import StylistResponse
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
    chat_session_id: str
    # --- Internal Work State ---
    db_session: AsyncSession  # Active DB session
    intent: Optional[StylistIntent]  # Detected intent (e.g., product_search)
    chat_context: Optional[dict]  # Structured conversation history & summary
    shortlist_product_ids: Optional[List[str]]  # product IDs from Redis shortlist
    # Annotated with operator.add to allow multiple nodes to contribute products
    candidate_products: Annotated[List[dict], operator.add]
    search_iteration: int  # Tracking number of search attempts
    user_preferences: Optional[any]  # UserPreferences model instance
    
    # --- Follow-up and Context Fields ---
    is_follow_up: bool  # Whether current message is a follow-up
    refined_query: Optional[CompletedStylistQuery]  # Merged query for follow-ups
    excluded_product_ids: List[UUID]  # IDs to exclude from search results
    
    # --- Enrichment Fields ---
    user_memories: Optional[List[dict]]  # mem0 recalled memories for this user
    trend_context: Optional[str]  # Web search results for trend queries

    # --- Output Fields ---
    response: Optional[StylistResponse]  # Final response returned to API
