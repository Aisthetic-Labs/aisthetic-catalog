from sqlalchemy import (
    Column,
    String,
    DateTime,
    Boolean,
    Numeric,
    Text,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.sql import func
from app.catalog.models_tenant import TenantBase  # reuse same base
import uuid


class UserProfile(TenantBase):
    __tablename__ = "user_profile"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # merchant's user id, e.g. from their auth system
    external_user_id = Column(String, nullable=False, unique=True)

    # core attributes
    name = Column(String, nullable=True)
    gender = Column(String, nullable=True)  # "male"/"female"/"unisex"/etc
    preferred_sizes = Column(ARRAY(String), nullable=True)  # ["M", "32", "UK8"]
    body_type = Column(String, nullable=True)  # "athletic", "slim", etc

    # preferences
    liked_colors = Column(ARRAY(String), nullable=True)
    disliked_colors = Column(ARRAY(String), nullable=True)
    liked_fits = Column(ARRAY(String), nullable=True)       # ["oversized", "slim"]
    liked_styles = Column(ARRAY(String), nullable=True)     # ["streetwear", "minimal"]
    liked_occasions = Column(ARRAY(String), nullable=True)  # ["party", "wedding"]
    price_sensitivity = Column(String, nullable=True)       # "budget", "mid", "premium"

    # free-form summary we keep updating with LLM
    persona_summary = Column(Text, nullable=True)

    meta = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class UserEvent(TenantBase):
    """
    Generic event log for preference learning.
    """
    __tablename__ = "user_event"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("user_profile.id"), nullable=False)

    event_type = Column(String, nullable=False)
    # e.g. "view", "click", "add_to_cart", "purchase",
    #      "like", "dislike", "stylist_question"

    product_id = Column(UUID(as_uuid=True), ForeignKey("product.id"), nullable=True)
    context = Column(JSONB, nullable=True)  # arbitrary extra data

    created_at = Column(DateTime(timezone=True), server_default=func.now())