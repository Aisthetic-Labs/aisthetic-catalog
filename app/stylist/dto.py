from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from app.catalog.dto import CatalogFilter
from .intents import StylistIntent


class QuickReply(BaseModel):
    label: str
    payload: dict


class StylistChatRequest(BaseModel):
    external_user_id: str
    message: str
    history: List["ChatTurn"] = []   # forward-ref, defined below
    occasion: Optional[str] = None
    compare_product_ids: Optional[List[UUID]] = None


class ChatTurn(BaseModel):
    role: str  # "user" or "assistant"
    message: str


class StylistResponse(BaseModel):
    answer: str
    recommended_product_ids: List[UUID] = []
    chosen_product_id: Optional[UUID] = None
    intent: Optional[StylistIntent] = None
    quick_replies: List[QuickReply] = []