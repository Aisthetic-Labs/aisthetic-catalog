from app.logger import logger
from app.stylist.chat_context import get_chat_context_summarizer
from app.stylist.intent_detection import detect_intent
from app.stylist.persona import (
    build_persona_context,
    get_or_create_user_profile,
)
from app.stylist.state import AgentState

async def initialize_node(state: AgentState) -> dict:
    """
    Gathers basic context: persona summary, user profile, chat context, and intent.
    This runs at the start of every request.
    """
    session = state["session"] # DB session
    external_user_id = state["external_user_id"]
    merchant_id = state["merchant_id"]
    
    logger.info(f"[AgentFlow] Entering initialize_node for user={external_user_id}")

    # 1) Build/Load Persona Context
    persona_json = await build_persona_context(session, external_user_id)
    logger.info("[AgentFlow] Built persona context: " + persona_json)
    # 2) Get/Create User Profile
    user_profile = await get_or_create_user_profile(session, external_user_id)
    
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
        "persona_json": persona_json,
        "user_profile": user_profile,
        "chat_context": chat_context,
        "intent": intent,
        "candidate_products": [],
        "search_iteration": 0,
        "mode": "freeform"
    }
