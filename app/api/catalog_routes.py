import csv
import json

from app.core.tenant_db import get_tenant_sessionmaker
from app.catalog.ingestion import ingest_products
from uuid import UUID
from fastapi import APIRouter, UploadFile, File, HTTPException
from sqlalchemy import select

from app.catalog.dto import (
    MerchantProductIn,
    CatalogSearchRequest,
    ImageSearchRequest,
    ProductDetailOut,
)
from app.catalog.search import search_products, search_products_by_image
from app.catalog.models_tenant import Product, ProductImage, ProductVariant

router = APIRouter(prefix="/merchants/{merchant_id}/catalog", tags=["catalog"])


@router.post("/ingest/csv")
async def ingest_catalog_csv(
    merchant_id: UUID,
    file: UploadFile = File(...),
):
    """
    Ingest merchant catalog from CSV file.
    The CSV is expected to have columns: id, title, description, category, sub_category, gender,
    color, price, currency, brand, primary_image_url, image_urls_list, etc.
    Adjust the mapping in the code as per your CSV structure.
    1. Reads the CSV file.
    2. Parses each row into MerchantProductIn objects.
    3. Calls ingest_products to upsert into DB and index into search.
    4. Returns count of ingested products.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV supported for now")

    content = await file.read()
    text = content.decode("utf-8")
    reader = csv.DictReader(text.splitlines())

    # validate required columns
    required_columns = ["id", "title", "price", "primary_image_url"]
    for col in required_columns:
        if col not in reader.fieldnames:
            raise HTTPException(status_code=400, detail=f"Missing required column: {col}")



    products_in: list[MerchantProductIn] = []
    for row in reader:
        # Minimal mapping – adjust column names to your CSV
        p = MerchantProductIn(
            merchant_product_id=row["id"],
            title=row["title"],
            description=row.get("description", ""),
            category=row.get("category", "UNKNOWN"),
            sub_category=row.get("sub_category"),
            gender=row.get("gender"),
            color=row.get("color"),
            price=float(row["price"]),
            currency=row.get("currency", "INR"),
            brand=row.get("brand"),
            primary_image=row.get("primary_image_url"),
            images=[],
            meta_data=json.loads(row["metadata"]),
        )
        products_in.append(p)

    SessionLocal = get_tenant_sessionmaker(str(merchant_id))

    async with SessionLocal() as session:
        count = await ingest_products(
            session=session,
            merchant_id=str(merchant_id),
            products=products_in,
        )

    return {"status": "ok", "ingested": count}


@router.post("/search")
async def search_catalog(
    merchant_id: UUID,
    req: CatalogSearchRequest,
):
    results = await search_products(
        merchant_id=str(merchant_id),
        req=req,
    )
    return {"results": results}


@router.post("/search_by_image")
async def search_catalog_by_image(
    merchant_id: UUID,
    req: ImageSearchRequest,
):
    try:
        results = await search_products_by_image(
            merchant_id=str(merchant_id),
            req=req,
        )
    except RuntimeError as e:
        # clean 501 for "not implemented"
        raise HTTPException(status_code=501, detail=str(e))
    return {"results": results}


@router.get("/products/{product_id}", response_model=ProductDetailOut)
async def get_product_detail(
    merchant_id: UUID,
    product_id: UUID,
):
    SessionLocal = get_tenant_sessionmaker(str(merchant_id))

    async with SessionLocal() as session:
        # Load main product
        result = await session.execute(
            select(Product).where(Product.id == product_id)
        )
        product = result.scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        # Load images ordered by position
        img_result = await session.execute(
            select(ProductImage)
            .where(ProductImage.product_id == product.id)
            .order_by(ProductImage.position.asc())
        )
        images = img_result.scalars().all()

        primary_image_url = None
        other_image_urls: list[str] = []
        if images:
            primary_image_url = images[0].image_url
            other_image_urls = [img.image_url for img in images[1:]]

        # Load variants
        var_result = await session.execute(
            select(ProductVariant).where(ProductVariant.product_id == product.id)
        )
        variant_rows = var_result.scalars().all()
        variants_payload: list[dict] = []
        for v in variant_rows:
            payload = {
                "size": v.size,
                "sku": v.sku,
                "in_stock": v.in_stock,
            }
            if v.extra:
                payload.update(v.extra)
            variants_payload.append(payload)

        return ProductDetailOut(
            product_id=str(product.id),
            title=product.title,
            description=product.description,
            category=product.category,
            sub_category=product.sub_category,
            gender=product.gender,
            color=product.color_primary,
            secondary_colors=product.color_secondary,
            fit=product.fit,
            style_tags=product.style_tags,
            occasion_tags=product.occasion_tags,
            fabric=product.fabric,
            price=float(product.price),
            currency=product.currency,
            brand=product.brand,
            pattern=product.pattern,
            primary_image=primary_image_url,
            images=other_image_urls,
            variants=variants_payload or None,
            meta_data=product.meta_data,
        )