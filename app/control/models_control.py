from sqlalchemy import Column, String, DateTime, Enum, ForeignKey, JSON, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum

from app.core.db_control import ControlBase


class MerchantStatus(str, enum.Enum):
    active = "active"
    suspended = "suspended"


class Merchant(ControlBase):
    __tablename__ = "merchant"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, unique=True)
    status = Column(Enum(MerchantStatus), nullable=False, default=MerchantStatus.active)
    plan = Column(String, nullable=False, default="starter")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class MerchantDBConnection(ControlBase):
    __tablename__ = "merchant_db_connection"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchant.id"), nullable=False, unique=True)
    db_type = Column(String, nullable=False, default="postgres")
    db_host = Column(String, nullable=False)
    db_port = Column(Integer, nullable=False, default=5432)
    db_name = Column(String, nullable=False)
    db_user = Column(String, nullable=False)
    db_password = Column(String, nullable=False)  # TODO: encrypt at rest
    extra = Column(JSON, nullable=True)