from __future__ import annotations

import json

from app.core.config import settings
from app.llm.client import get_chat_client
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
# LLM classification
# ---------------------------------------------------------------------------

_CLASSIFY_PROMPT = """\
You are classifying a user's response to a style-preference prompt.
The user was asked to share fashion preferences (colors, fits, sizes, style).

Classify the message into exactly ONE category:
- "preferences": The user is sharing style preferences, fashion tastes, or clothing details.
- "skip": The user wants to skip preference sharing (e.g. "no thanks", "skip", "nah", "let's just shop").
- "other": The user is asking a product question, greeting, or anything unrelated to sharing preferences.

User message: {message}

Return ONLY a JSON object: {{"category": "<preferences|skip|other>"}}
"""


async def _classify_preference_response(message: str) -> str:
    """Classify whether the user message is preferences, skip, or other."""
    chat_client = get_chat_client()
    resp = await chat_client.chat.completions.create(
        model=settings.STYLIST_MODEL_NAME,
        messages=[
            {"role": "system", "content": "Classify user responses to a preference prompt."},
            {"role": "user", "content": _CLASSIFY_PROMPT.format(message=message)},
        ],
        response_format={"type": "json_object"},
        max_tokens=50,
    )
    raw = resp.choices[0].message.content or "{}"
    data = json.loads(raw)
    category = data.get("category", "other")
    if category not in ("preferences", "skip", "other"):
        return "other"
    return category


# ---------------------------------------------------------------------------
# Main node
# ---------------------------------------------------------------------------

async def preference_collection_node(state: AgentState) -> dict:
    """
    Stateless single-step preference collection.
    Always receives a message (route handler guarantees this).
    Uses LLM to classify the response into: preferences, skip, or other.
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

    # Classify the user's response
    category = await _classify_preference_response(message)
    logger.info(f"[PreferenceCollection] Classified response as: {category}")

    user_profile = await find_user_profile(db_session, external_user_id)

    # ── skip: user wants to skip preference sharing ───────────────────
    if category == "skip":
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

    # ── other: product query, greeting, etc. ──────────────────────────
    if category == "other":
        await summarize_persona(db_session, user_profile, user_preferences)
        logger.info("[PreferenceCollection] Non-preference message, generating persona and moving on")
        return {
            "response": StylistResponse(
                answer=(
                    "Sure, let's get started! You can share style preferences anytime.\n\n"
                    "What are you shopping for today?"
                ),
                intent=intent,
                quick_replies=WELCOME_QUICK_REPLIES,
            ),
        }

    # ── preferences: extract, apply, and generate persona ─────────────
    extracted = await extract_preferences_from_text(message)
    updated_keys = await apply_extracted_preferences(
        db_session, user_profile, user_preferences, extracted,
    )

    if updated_keys:
        keys_str = ", ".join(updated_keys)
        answer = (
            f"Got it! I've noted your preferences ({keys_str}). "
            "I'll use these to personalize your recommendations.\n\n"
            "What are you shopping for today?"
        )
    else:
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
