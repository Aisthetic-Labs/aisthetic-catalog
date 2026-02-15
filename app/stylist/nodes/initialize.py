from app.logger import logger
from app.stylist.chat_context import get_chat_context_summarizer
from app.stylist.intent_detection import detect_intent
from app.stylist.persona import (
    get_or_create_user_profile,
    get_or_create_user_preferences,
    summarize_persona,
)
from app.stylist.state import AgentState

async def initialize_node(state: AgentState) -> dict:
    """
    Gathers basic context: persona summary, user profile, chat context, and intent.
    This runs at the start of every request.
    """
    db_session = state["db_session"]
    external_user_id = state["external_user_id"]
    merchant_id = state["merchant_id"]
    
    logger.info(f"[AgentFlow] Entering initialize_node for user={external_user_id}")

    # 1) Get/Create User Profile + Preferences
    user_profile = await get_or_create_user_profile(db_session, external_user_id)
    user_preferences = await get_or_create_user_preferences(db_session, user_profile.id)

    # 2) Ensure persona summary exists in preferences
    if not (user_preferences.preferences or {}).get("persona_summary"):
        await summarize_persona(db_session, user_profile, user_preferences)
    logger.info("[AgentFlow] Persona context ready")

    # 3) Build Chat Context Summary (recent history, summarized)
    chat_context_summarizer = get_chat_context_summarizer()
    chat_context = await chat_context_summarizer.build_context(
        chat_session_id=state["chat_session_id"],
        current_user_message=state["message"],
    )
    
    # 4) Detect User Intent (e.g., search, styling, small talk)
    intent = await detect_intent(state["message"])
    logger.info(f"[AgentFlow] Detected intent: {intent.value}")
    
    return {
        "user_preferences": user_preferences,
        "chat_context": chat_context,
        "intent": intent,
        "search_iteration": 0,
    }
