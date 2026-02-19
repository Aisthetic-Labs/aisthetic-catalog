from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from .intents import StylistIntent


class QuickReply(BaseModel):
    label: str
    payload: dict


class StylistChatRequest(BaseModel):
    external_user_id: str
    message: Optional[str] = None
    chat_session_id: Optional[str] = None
    occasion: Optional[str] = None


class ProductRecommendation(BaseModel):
    product_id: UUID
    title: str
    brand: Optional[str] = None
    price: float
    currency: str = "INR"
    image_url: Optional[str] = None
    color: Optional[str] = None
    reason: str


class StylistResponse(BaseModel):
    chat_session_id: str = ""
    answer: str
    recommended_products: List[ProductRecommendation] = []
    shortlisted_product_ids: List[UUID] = []
    cart_product_ids: List[UUID] = []          # future, always empty for now
    intent: Optional[StylistIntent] = None
    quick_replies: List[QuickReply] = []