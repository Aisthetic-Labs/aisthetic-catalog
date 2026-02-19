from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.catalog_routes import router as catalog_router
from app.api.stylist_routes import router as stylist_router
from app.core.config import settings

app = FastAPI(title="Aisthetic Catalog Service")

# Allow your frontend origin(s)
_default_origins = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
]
_extra = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
origins = _default_origins + _extra

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # or ["POST", "OPTIONS"]
    allow_headers=["*"],  # or ["Content-Type", "Authorization"]
)

app.include_router(stylist_router)
app.include_router(catalog_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
