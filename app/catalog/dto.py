from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Dict


class MerchantProductIn(BaseModel):
    merchant_product_id: str
    title: str
    description: Optional[str] = ""
    category: str
    sub_category: Optional[str] = None
    gender: Optional[str] = None
    color: Optional[str] = None
    secondary_colors: Optional[List[str]] = None
    fit: Optional[str] = None
    style_tags: Optional[List[str]] = None
    occasion_tags: Optional[List[str]] = None
    fabric: Optional[str] = None
    price: float
    currency: str = "INR"
    brand: Optional[str] = None
    pattern: Optional[str] = None
    images: List[HttpUrl]
    primary_image: HttpUrl
    variants: Optional[List[Dict]] = None
    meta_data: Optional[Dict] = None


class CatalogFilter(BaseModel):
    category: Optional[str] = None
    color: Optional[List[str]] = None
    gender: Optional[str] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None


class CatalogSearchRequest(BaseModel):
    query_text: Optional[str] = None
    filters: CatalogFilter = CatalogFilter()
    limit: int = 10
    user_persona: Optional[Dict] = None  # reserved for later


class ProductOut(BaseModel):
    product_id: str
    title: str
    price: float
    currency: str
    image_url: Optional[HttpUrl] = None


class ProductDetailOut(BaseModel):
    product_id: str
    title: str
    description: Optional[str] = None
    category: str
    sub_category: Optional[str] = None
    gender: Optional[str] = None
    color: Optional[str] = None
    secondary_colors: Optional[List[str]] = None
    fit: Optional[str] = None
    style_tags: Optional[List[str]] = None
    occasion_tags: Optional[List[str]] = None
    fabric: Optional[str] = None
    price: float
    currency: str
    brand: Optional[str] = None
    pattern: Optional[str] = None
    primary_image: Optional[HttpUrl] = None
    images: List[HttpUrl]
    variants: Optional[List[Dict]] = None
    meta_data: Optional[Dict] = None


class ImageSearchRequest(BaseModel):
    image_url: HttpUrl
    filters: CatalogFilter = CatalogFilter()
    limit: int = 10


class BatchStatusOut(BaseModel):
    batch_id: str
    total: int
    pending: int
    processing: int
    processed: int
    failed: int