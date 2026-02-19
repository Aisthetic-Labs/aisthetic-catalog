from fastapi import APIRouter, HTTPException
from uuid import UUID

from app.core.tenant_db import get_tenant_sessionmaker
from app.logger import logger
from app.stylist.agent import handle_stylist_chat
from app.stylist.constants import (
    WELCOME_MESSAGE,
    WELCOME_QUICK_REPLIES,
    PREFERENCE_WELCOME_MESSAGE,
    PREFERENCE_QUICK_REPLIES,
)
from app.stylist.dto import StylistResponse, StylistChatRequest
from app.stylist.persona import find_user_profile, get_or_create_user_preferences
from app.stylist.session_store import get_session_store

router = APIRouter(
    prefix="/merchants/{merchant_id}/stylist",
    tags=["stylist"],
)


@router.post("/chat", response_model=StylistResponse)
async def stylist_chat(
    merchant_id: UUID,
    req: StylistChatRequest,
):
    store = get_session_store()
    has_session = req.chat_session_id is not None
    has_message = bool(req.message and req.message.strip())

    # session_id present but no message → 422
    if has_session and not has_message:
        raise HTTPException(
            status_code=422,
            detail="message is required when chat_session_id is provided",
        )

    # No session_id → validate user, then create new session
    if not has_session:
        SessionLocal = get_tenant_sessionmaker(str(merchant_id))
        async with SessionLocal() as db_session:
            profile = await find_user_profile(db_session, req.external_user_id)
            if profile is None:
                raise HTTPException(
                    status_code=404,
                    detail="User not found. Please register first.",
                )

            # Check if bare user (no persona yet)
            user_prefs = await get_or_create_user_preferences(db_session, profile.id)
            persona = (user_prefs.preferences or {}).get("persona_summary")
            is_bare_user = not persona

        welcome_msg = PREFERENCE_WELCOME_MESSAGE if is_bare_user else WELCOME_MESSAGE
        chat_session_id, _ = await store.create_session(
            merchant_id=str(merchant_id),
            external_user_id=req.external_user_id,
            welcome_message=welcome_msg,
        )
        if not has_message:
            return StylistResponse(
                chat_session_id=chat_session_id,
                answer=welcome_msg,
                quick_replies=PREFERENCE_QUICK_REPLIES if is_bare_user else WELCOME_QUICK_REPLIES,
            )
        # Has message → fall through to agent processing
    else:
        # Existing session
        chat_session_id = req.chat_session_id
        if await store.get_session(chat_session_id) is None:
            raise HTTPException(
                status_code=404,
                detail="Session not found or expired",
            )

    # Run the agent
    SessionLocal = get_tenant_sessionmaker(str(merchant_id))

    async with SessionLocal() as db_session:
        try:
            resp = await handle_stylist_chat(
                merchant_id=str(merchant_id),
                db_session=db_session,
                req=req,
                chat_session_id=chat_session_id,
            )
        except Exception as e:
            logger.exception(f"Stylist chat failed for merchant={merchant_id} user={req.external_user_id}")
            raise HTTPException(status_code=500, detail=str(e))

    return resp
