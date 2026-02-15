from fastapi import APIRouter, HTTPException
from uuid import UUID

from app.core.tenant_db import get_tenant_sessionmaker
from app.logger import logger
from app.stylist.agent import handle_stylist_chat
from app.stylist.dto import StylistResponse, QuickReply, StylistChatRequest
from app.stylist.session_store import get_session_store

router = APIRouter(
    prefix="/merchants/{merchant_id}/stylist",
    tags=["stylist"],
)

WELCOME_MESSAGE = (
    "Hey, I'm your AI stylist from Aisthetic \U0001f44b\n\n"
    "I can help you:\n"
    "- Pick outfits for occasions (weddings, dates, office, trips)\n"
    "- Decide between two garments\n"
    "- Discover pieces that match your style\n\n"
    "Tell me what you're shopping for, or pick an option below."
)

WELCOME_QUICK_REPLIES = [
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
]


@router.post("/chat", response_model=StylistResponse)
async def stylist_chat(
    merchant_id: UUID,
    req: StylistChatRequest,
):
    store = get_session_store()
    has_session = req.chat_session_id is not None
    has_message = bool(req.message and req.message.strip())

    # Case 3: session_id present but no message → 422
    if has_session and not has_message:
        raise HTTPException(
            status_code=422,
            detail="message is required when chat_session_id is provided",
        )

    # Case 1 & 2: no session_id → create new session
    if not has_session:
        chat_session_id, chat_session_data = await store.create_session(
            merchant_id=str(merchant_id),
            external_user_id=req.external_user_id,
            welcome_message=WELCOME_MESSAGE,
        )

        # Case 1: no message either → return welcome
        if not has_message:
            return StylistResponse(
                chat_session_id=chat_session_id,
                answer=WELCOME_MESSAGE,
                quick_replies=WELCOME_QUICK_REPLIES,
            )

        # Case 2: has message → fall through to agent processing
    else:
        # Case 4: existing session
        chat_session_id = req.chat_session_id
        chat_session_data = await store.get_session(chat_session_id)
        if chat_session_data is None:
            raise HTTPException(
                status_code=404,
                detail="Session not found or expired",
            )

    # Cases 2 & 4: run the agent
    SessionLocal = get_tenant_sessionmaker(str(merchant_id))

    async with SessionLocal() as db_session:
        try:
            resp = await handle_stylist_chat(
                merchant_id=str(merchant_id),
                db_session=db_session,
                req=req,
                chat_session_id=chat_session_id,
                chat_session_data=chat_session_data,
            )
        except Exception as e:
            logger.exception(f"Stylist chat failed for merchant={merchant_id} user={req.external_user_id}")
            raise HTTPException(status_code=500, detail=str(e))

    return resp
