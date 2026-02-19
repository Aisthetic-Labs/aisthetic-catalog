from sqlalchemy import (
    Column,
    Date,
    String,
    DateTime,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.catalog.models_tenant import TenantBase  # reuse same base
import uuid


class UserProfile(TenantBase):
    __tablename__ = "user_profile"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # merchant's user id, e.g. from their auth system
    external_user_id = Column(String, nullable=False, unique=True)

    # stable identity / physical attributes
    name = Column(String, nullable=True)
    dob = Column(Date, nullable=True)
    gender = Column(String, nullable=True)  # "male"/"female"/"unisex"/etc
    meta = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class UserPreferences(TenantBase):
    """
    Mutable style preferences stored as flexible JSONB.
    Keys include: body_type, preferred_sizes, liked_colors, disliked_colors,
    liked_fits, liked_styles, price_sensitivity, persona_summary.
    """
    __tablename__ = "user_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("user_profile.id"), nullable=False, unique=True)
    preferences = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


