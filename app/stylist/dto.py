from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from app.catalog.dto import CatalogFilter
from .intents import StylistIntent


class QuickReply(BaseModel):
    label: str
    payload: dict


class StylistChatRequest(BaseModel):
    external_user_id: Optional[str] = None
    message: Optional[str] = None
    chat_session_id: Optional[str] = None
    occasion: Optional[str] = None


class ChatTurn(BaseModel):
    role: str  # "user" or "assistant"
    message: str
    recommended_product_ids: Optional[List[UUID]] = None


class StylistResponse(BaseModel):
    chat_session_id: str = ""
    answer: str
    recommended_product_ids: List[UUID] = []
    shortlisted_product_ids: List[UUID] = []
    cart_product_ids: List[UUID] = []          # future, always empty for now
    intent: Optional[StylistIntent] = None
    quick_replies: List[QuickReply] = []