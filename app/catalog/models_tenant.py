from sqlalchemy import (
    Column,
    String,
    DateTime,
    Numeric,
    Boolean,
    ForeignKey,
    Integer,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base
import uuid

TenantBase = declarative_base()


class Product(TenantBase):
    __tablename__ = "product"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_product_id = Column(String, nullable=False, unique=True)

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    category = Column(String, nullable=False)
    sub_category = Column(String, nullable=True)
    gender = Column(String, nullable=True)

    color_primary = Column(String, nullable=True)
    color_secondary = Column(ARRAY(String), nullable=True)

    fit = Column(String, nullable=True)
    style_tags = Column(ARRAY(String), nullable=True)
    occasion_tags = Column(ARRAY(String), nullable=True)

    fabric = Column(String, nullable=True)
    price = Column(Numeric, nullable=False)
    currency = Column(String, nullable=False, default="INR")
    brand = Column(String, nullable=True)
    pattern = Column(String, nullable=True)
    care_instructions = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="active")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ProductVariant(TenantBase):
    __tablename__ = "product_variant"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("product.id"), nullable=False)
    size = Column(String, nullable=True)
    sku = Column(String, nullable=True)
    in_stock = Column(Boolean, nullable=False, default=True)
    extra = Column(JSONB, nullable=True)


class ProductImage(TenantBase):
    __tablename__ = "product_image"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("product.id"), nullable=False)
    image_url = Column(String, nullable=False)
    position = Column(Integer, nullable=False, default=1)
    alt_text = Column(String, nullable=True)