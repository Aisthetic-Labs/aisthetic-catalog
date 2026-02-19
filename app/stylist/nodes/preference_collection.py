from __future__ import annotations

from app.logger import logger
from app.stylist.dto import StylistResponse, QuickReply
from app.stylist.intents import StylistIntent
from app.stylist.persona import (
    find_user_profile,
    get_or_create_user_preferences,
    extract_preferences_from_text,
    apply_extracted_preferences,
    summarize_persona,
)
from app.stylist.state import AgentState

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WELCOME_QUICK_REPLIES = [
    QuickReply(
        label="Style me for an occasion",
        payload={"suggested_intent": "occasion_styling"},
    ),
    QuickReply(
        label="Recommend shirts for me",
        payload={"suggested_intent": "direct_product_search", "query": "shirt"},
    ),
]


# ---------------------------------------------------------------------------
# Main node
# ---------------------------------------------------------------------------

async def preference_collection_node(state: AgentState) -> dict:
    """
    Stateless single-step preference collection.
    Always receives a message (route handler guarantees this).
    - skip → generate persona from existing data, welcome
    - text  → extract & save preferences, generate persona, welcome
    """
    logger.info("[AgentFlow] Entering preference_collection_node")
    db_session = state["db_session"]
    external_user_id = state["external_user_id"]
    message = (state.get("message") or "").strip()
    intent = StylistIntent.PREFERENCE_COLLECTION

    user_preferences = state.get("user_preferences")

    # If preferences weren't passed from initialize, fetch them
    if user_preferences is None:
        user_profile = await find_user_profile(db_session, external_user_id)
        user_preferences = await get_or_create_user_preferences(db_session, user_profile.id)

    # ── User skips ────────────────────────────────────────────────────
    if message.lower() in ("skip", "skip this"):
        user_profile = await find_user_profile(db_session, external_user_id)
        await summarize_persona(db_session, user_profile, user_preferences)
        logger.info("[PreferenceCollection] User skipped preferences")
        return {
            "response": StylistResponse(
                answer=(
                    "No problem! You can always update your preferences later.\n\n"
                    "What are you shopping for today?"
                ),
                intent=intent,
                quick_replies=WELCOME_QUICK_REPLIES,
            ),
        }

    # ── User provides preference text ─────────────────────────────────
    user_profile = await find_user_profile(db_session, external_user_id)
    extracted = await extract_preferences_from_text(message)
    updated_keys = await apply_extracted_preferences(
        db_session, user_profile, user_preferences, extracted,
    )

    if updated_keys:
        # apply_extracted_preferences already calls summarize_persona
        keys_str = ", ".join(updated_keys)
        answer = (
            f"Got it! I've noted your preferences ({keys_str}). "
            "I'll use these to personalize your recommendations.\n\n"
            "What are you shopping for today?"
        )
    else:
        # Nothing extracted — still generate persona from existing profile data
        await summarize_persona(db_session, user_profile, user_preferences)
        answer = (
            "Thanks! I couldn't pick out specific preferences from that, "
            "but no worries — you can always tell me more later.\n\n"
            "What are you shopping for today?"
        )

    logger.info(f"[PreferenceCollection] Preferences saved: {updated_keys}")
    return {
        "response": StylistResponse(
            answer=answer,
            intent=intent,
            quick_replies=WELCOME_QUICK_REPLIES,
        ),
        "user_preferences": user_preferences,
    }
