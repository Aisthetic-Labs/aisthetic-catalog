from fastapi import APIRouter, HTTPException
from uuid import UUID

from app.core.tenant_db import get_tenant_sessionmaker
from app.stylist.agent import handle_stylist_chat
from app.stylist.dto import StylistResponse, QuickReply, StylistChatRequest

router = APIRouter(
    prefix="/merchants/{merchant_id}/stylist",
    tags=["stylist"],
)


@router.get("/start", response_model=StylistResponse)
async def stylist_start(merchant_id: UUID):
    # For now, no DB needed; pure UX endpoint
    return StylistResponse(
        answer=(
            "Hey, I'm your AI stylist from Aisthetic 👋\n\n"
            "I can help you:\n"
            "- Pick outfits for occasions (weddings, dates, office, trips)\n"
            "- Decide between two garments\n"
            "- Discover pieces that match your style\n\n"
            "Tell me what you're shopping for, or pick an option below."
        ),
        quick_replies=[
            QuickReply(
                label="Style me for an occasion",
                payload={"suggested_intent": "occasion_styling"},
            ),
            QuickReply(
                label="Help me choose between two items",
                payload={"suggested_intent": "product_comparison"},
            ),
            QuickReply(
                label="Recommend shirts for me",
                payload={"suggested_intent": "direct_product_search", "query": "shirt"},
            ),
        ],
    )


@router.post("/chat", response_model=StylistResponse)
async def stylist_chat(
    merchant_id: UUID,
    req: StylistChatRequest,
):
    SessionLocal = get_tenant_sessionmaker(str(merchant_id))

    async with SessionLocal() as session:
        try:
            resp = await handle_stylist_chat(
                merchant_id=str(merchant_id),
                session=session,
                req=req,
            )
        except Exception as e:
            # you can refine error handling later
            raise HTTPException(status_code=500, detail=str(e))

    return resp