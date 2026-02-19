from app.logger import logger
from app.stylist.chat_context import get_chat_context_summarizer
from app.stylist.intent_detection import detect_intent
from app.stylist.intents import StylistIntent
from app.stylist.persona import (
    find_user_profile,
    get_or_create_user_preferences,
)
from app.stylist.session_store import get_session_store
from app.stylist.shortlist_service import get_shortlist_service
from app.stylist.state import AgentState

async def initialize_node(state: AgentState) -> dict:
    """
    Gathers basic context: persona summary, user profile, chat context, and intent.
    This runs at the start of every request.

    If the user profile is not found, or persona is empty, routes to
    PREFERENCE_COLLECTION so the graph can collect preferences (or tell
    the user to register).
    """
    db_session = state["db_session"]
    external_user_id = state["external_user_id"]
    chat_session_id = state["chat_session_id"]

    logger.info(f"[AgentFlow] Entering initialize_node for user={external_user_id}")

    store = get_session_store()

    # 0) Check for active preference collection flow
    pref_state = await store.get_onboarding_state(chat_session_id)
    if pref_state:
        logger.info(f"[AgentFlow] Active preference collection (step={pref_state['step']}), skipping normal init")
        return {
            "intent": StylistIntent.PREFERENCE_COLLECTION,
            "search_iteration": 0,
            "shortlist_product_ids": [],
        }

    # 1) Look up user profile — must exist (validated in route handler)
    user_profile = await find_user_profile(db_session, external_user_id)

    if user_profile is None:
        # Should never happen — route handler validates before session creation.
        # Defensive guard only.
        logger.error(f"[AgentFlow] User {external_user_id} not found despite route validation")
        raise ValueError(f"User profile not found for external_user_id={external_user_id}")

    # 2) Get/Create Preferences
    user_preferences = await get_or_create_user_preferences(db_session, user_profile.id)

    # 3) Check persona summary — if empty, ask for preferences
    persona = (user_preferences.preferences or {}).get("persona_summary")
    if not persona:
        logger.info("[AgentFlow] Empty persona, routing to preference_collection")
        await store.set_onboarding_state(chat_session_id, step="awaiting_preferences")
        return {
            "intent": StylistIntent.PREFERENCE_COLLECTION,
            "user_preferences": user_preferences,
            "search_iteration": 0,
            "shortlist_product_ids": [],
        }

    logger.info("[AgentFlow] Persona context ready")

    # 4) Build Chat Context Summary (recent history, summarized)
    chat_context_summarizer = get_chat_context_summarizer()
    chat_context = await chat_context_summarizer.build_context(
        chat_session_id=chat_session_id,
        current_user_message=state["message"],
    )

    # 5) Load shortlist from Redis
    shortlist_service = get_shortlist_service()
    shortlist_product_ids = await shortlist_service.get_all(chat_session_id)

    # 6) Recall relevant memories from mem0
    from app.stylist.memory_service import recall_memories
    user_memories = await recall_memories(
        user_id=f"{state['merchant_id']}:{external_user_id}",
        query=state["message"],
    )

    # 7) Detect User Intent (e.g., search, styling, small talk)
    intent = await detect_intent(state["message"])
    logger.info(f"[AgentFlow] Detected intent: {intent.value}")

    return {
        "user_preferences": user_preferences,
        "chat_context": chat_context,
        "intent": intent,
        "search_iteration": 0,
        "shortlist_product_ids": shortlist_product_ids,
        "user_memories": user_memories,
    }
