from fastapi import FastAPI
from app.api.catalog_routes import router as catalog_router

app = FastAPI(title="Aisthetic Catalog Service")
app.include_router(catalog_router)


@app.get("/health")
async def health():
    return {"status": "ok"}