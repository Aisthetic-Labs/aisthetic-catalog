import csv

from app.core.tenant_db import get_tenant_sessionmaker
from app.catalog.ingestion import ingest_products
from uuid import UUID
from fastapi import APIRouter, UploadFile, File, HTTPException
# ...
from app.catalog.dto import MerchantProductIn, CatalogSearchRequest, ImageSearchRequest
from app.catalog.search import search_products, search_products_by_image

router = APIRouter(prefix="/merchants/{merchant_id}/catalog", tags=["catalog"])


@router.post("/ingest/csv")
async def ingest_catalog_csv(
    merchant_id: UUID,
    file: UploadFile = File(...),
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV supported for now")

    content = await file.read()
    text = content.decode("utf-8")
    reader = csv.DictReader(text.splitlines())

    products_in: list[MerchantProductIn] = []
    for row in reader:
        # Minimal mapping – adjust column names to your CSV
        p = MerchantProductIn(
            merchant_product_id=row["id"],
            title=row["title"],
            description=row.get("description", ""),
            category=row.get("category", "shirt"),
            sub_category=row.get("sub_category"),
            gender=row.get("gender"),
            color=row.get("color"),
            price=float(row["price"]),
            currency=row.get("currency", "INR"),
            brand=row.get("brand"),
            images=[row["image_url"]],
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