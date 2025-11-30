from fastapi import FastAPI

from app.api.catalog_routes import router as catalog_router
from app.api.stylist_routes import router as stylist_router

app = FastAPI(title="Aisthetic Catalog Service")

from fastapi.middleware.cors import CORSMiddleware

# Allow your frontend origin(s)
origins = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
]

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
