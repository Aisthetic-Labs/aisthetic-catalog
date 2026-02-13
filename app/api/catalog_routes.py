import csv
import traceback
import uuid as uuid_mod
from typing import Optional

from app.core.tenant_db import get_tenant_sessionmaker
from app.catalog.ingestion import ingest_products, parse_csv_row_to_dto
from uuid import UUID
from fastapi import APIRouter, Query, UploadFile, File, HTTPException
from sqlalchemy import select, func, text

from app.catalog.dto import (
    CatalogSearchRequest,
    ImageSearchRequest,
    ProductDetailOut,
    BatchStatusOut,
)
from app.catalog.search import search_products, search_products_by_image
from app.catalog.models_tenant import CsvUploadRow, Product, ProductImage, ProductVariant
from app.logger import logger

router = APIRouter(prefix="/merchants/{merchant_id}/catalog", tags=["catalog"])


@router.post("/ingest/csv")
async def ingest_catalog_csv(
    merchant_id: UUID,
    file: UploadFile = File(...),
):
    """Stage CSV rows for later processing. Returns immediately with a batch_id."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV supported for now")

    content = await file.read()
    decoded = content.decode("utf-8")
    reader = csv.DictReader(decoded.splitlines())

    required_columns = ["id", "title", "price", "primary_image_url"]
    for col in required_columns:
        if col not in reader.fieldnames:
            raise HTTPException(status_code=400, detail=f"Missing required column: {col}")

    batch_id = uuid_mod.uuid4()
    rows_to_stage: list[CsvUploadRow] = []

    for row in reader:
        rows_to_stage.append(
            CsvUploadRow(
                batch_id=batch_id,
                merchant_product_id=row["id"],
                row_data=dict(row),
                status="pending",
            )
        )

    if not rows_to_stage:
        raise HTTPException(status_code=400, detail="CSV contains no data rows")

    SessionLocal = get_tenant_sessionmaker(str(merchant_id))
    async with SessionLocal() as session:
        session.add_all(rows_to_stage)
        await session.commit()

    return {"status": "accepted", "batch_id": str(batch_id), "rows_staged": len(rows_to_stage)}


@router.post("/ingest/process")
async def process_staged_rows(
    merchant_id: UUID,
    limit: int = Query(default=50, ge=1, le=500),
    batch_id: Optional[UUID] = Query(default=None),
):
    """Claim and process pending CsvUploadRows. Uses FOR UPDATE SKIP LOCKED for concurrency safety."""
    SessionLocal = get_tenant_sessionmaker(str(merchant_id))

    processed_count = 0
    failed_count = 0

    async with SessionLocal() as session:
        # Build claim query
        where_clause = "status = 'pending'"
        params = {"lim": limit}
        if batch_id:
            where_clause += " AND batch_id = :bid"
            params["bid"] = str(batch_id)

        claim_sql = text(
            f"SELECT id FROM csv_upload_row "
            f"WHERE {where_clause} "
            f"ORDER BY created_at "
            f"LIMIT :lim "
            f"FOR UPDATE SKIP LOCKED"
        )
        result = await session.execute(claim_sql, params)
        claimed_ids = [r[0] for r in result.fetchall()]

        if not claimed_ids:
            return {"processed": 0, "failed": 0, "total_claimed": 0}

        # Mark claimed rows as processing
        await session.execute(
            text(
                "UPDATE csv_upload_row "
                "SET status = 'processing', attempt_count = attempt_count + 1, updated_at = now() "
                "WHERE id = ANY(:ids)"
            ),
            {"ids": claimed_ids},
        )
        await session.commit()

    # Process each row individually for per-row error isolation
    total = len(claimed_ids)
    for idx, row_id in enumerate(claimed_ids, start=1):
        async with SessionLocal() as session:
            row_result = await session.execute(
                select(CsvUploadRow).where(CsvUploadRow.id == row_id)
            )
            upload_row = row_result.scalar_one()

            try:
                logger.info(f"Processing {idx}/{total} (merchant={merchant_id})")
                product_in = parse_csv_row_to_dto(upload_row.row_data)
                await ingest_products(
                    session=session,
                    merchant_id=str(merchant_id),
                    products=[product_in],
                )
                upload_row.status = "processed"
                upload_row.processed_at = func.now()
                processed_count += 1
            except Exception as e:
                logger.error(f"Failed processing row {row_id}: {e}")
                upload_row.status = "failed"
                upload_row.error_message = traceback.format_exc()
                failed_count += 1

            await session.commit()

    return {"processed": processed_count, "failed": failed_count, "total_claimed": total}


@router.get("/ingest/batch/{batch_id}/status", response_model=BatchStatusOut)
async def get_batch_status(
    merchant_id: UUID,
    batch_id: UUID,
):
    """Return count breakdown by status for a given batch."""
    SessionLocal = get_tenant_sessionmaker(str(merchant_id))

    async with SessionLocal() as session:
        result = await session.execute(
            select(
                CsvUploadRow.status,
                func.count().label("cnt"),
            )
            .where(CsvUploadRow.batch_id == batch_id)
            .group_by(CsvUploadRow.status)
        )
        counts = {row.status: row.cnt for row in result.fetchall()}

    if not counts:
        raise HTTPException(status_code=404, detail="Batch not found")

    total = sum(counts.values())
    return BatchStatusOut(
        batch_id=str(batch_id),
        total=total,
        pending=counts.get("pending", 0),
        processing=counts.get("processing", 0),
        processed=counts.get("processed", 0),
        failed=counts.get("failed", 0),
    )


@router.post("/ingest/retry-failed")
async def retry_failed_rows(
    merchant_id: UUID,
    batch_id: Optional[UUID] = Query(default=None),
    max_attempts: int = Query(default=3, ge=1),
):
    """Requeue failed rows back to pending for reprocessing."""
    SessionLocal = get_tenant_sessionmaker(str(merchant_id))

    async with SessionLocal() as session:
        where_clause = "status = 'failed' AND attempt_count < :max_attempts"
        params: dict = {"max_attempts": max_attempts}
        if batch_id:
            where_clause += " AND batch_id = :bid"
            params["bid"] = str(batch_id)

        result = await session.execute(
            text(
                f"UPDATE csv_upload_row "
                f"SET status = 'pending', error_message = NULL, updated_at = now() "
                f"WHERE {where_clause}"
            ),
            params,
        )
        requeued = result.rowcount
        await session.commit()

    return {"status": "ok", "requeued": requeued}


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