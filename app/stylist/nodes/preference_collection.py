from __future__ import annotations

from app.logger import logger
from app.stylist.dto import StylistResponse, QuickReply
from app.stylist.intents import StylistIntent
from app.stylist.persona import (
    find_user_profile,
    get_or_create_user_preferences,
    extract_preferences_from_text,
    apply_extracted_preferences,
)
from app.stylist.session_store import get_session_store
from app.stylist.state import AgentState

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PREFERENCE_PROMPT = (
    "I'd love to get to know your style! Tell me a bit about yourself — "
    "for example, what fits you prefer, colors you like, your usual sizes, "
    "or your general fashion vibe.\n\n"
    "You can also skip this and jump straight to shopping."
)

PREFERENCE_QUICK_REPLIES = [
    QuickReply(label="Skip", payload={"action": "skip"}),
    QuickReply(
        label="I like minimal, neutral tones",
        payload={"value": "I like minimal, neutral tones"},
    ),
    QuickReply(
        label="Bold streetwear, oversized fits",
        payload={"value": "Bold streetwear, oversized fits"},
    ),
]

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
    Single-step conversational preference collection:
    - Not registered → tell user to register
    - awaiting_preferences + skip → clear state, welcome
    - awaiting_preferences + text → extract & save preferences, welcome
    """
    logger.info("[AgentFlow] Entering preference_collection_node")
    db_session = state["db_session"]
    external_user_id = state["external_user_id"]
    chat_session_id = state["chat_session_id"]
    message = (state.get("message") or "").strip()
    intent = StylistIntent.PREFERENCE_COLLECTION

    store = get_session_store()
    user_preferences = state.get("user_preferences")

    # If preferences weren't passed from initialize, fetch them
    if user_preferences is None:
        user_profile = await find_user_profile(db_session, external_user_id)
        user_preferences = await get_or_create_user_preferences(db_session, user_profile.id)

    # ── awaiting_preferences: first visit (no message yet) ────────────
    ob = await store.get_onboarding_state(chat_session_id)
    step = ob["step"] if ob else None

    if step == "awaiting_preferences" and not message:
        return {
            "response": StylistResponse(
                answer=PREFERENCE_PROMPT,
                intent=intent,
                quick_replies=PREFERENCE_QUICK_REPLIES,
            ),
        }

    # ── User skips ────────────────────────────────────────────────────
    if step == "awaiting_preferences" and message.lower() in ("skip", "skip this"):
        await store.clear_onboarding_state(chat_session_id)
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
    if step == "awaiting_preferences" and message:
        user_profile = await find_user_profile(db_session, external_user_id)
        extracted = await extract_preferences_from_text(message)
        updated_keys = await apply_extracted_preferences(
            db_session, user_profile, user_preferences, extracted,
        )

        await store.clear_onboarding_state(chat_session_id)

        if updated_keys:
            keys_str = ", ".join(updated_keys)
            answer = (
                f"Got it! I've noted your preferences ({keys_str}). "
                "I'll use these to personalize your recommendations.\n\n"
                "What are you shopping for today?"
            )
        else:
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

    # ── Fallback (shouldn't happen) ───────────────────────────────────
    logger.warning(f"[PreferenceCollection] Unexpected state step={step}, message={message!r}")
    await store.clear_onboarding_state(chat_session_id)
    return {
        "response": StylistResponse(
            answer="Let's get started! What are you shopping for today?",
            intent=intent,
            quick_replies=WELCOME_QUICK_REPLIES,
        ),
    }
