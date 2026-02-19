from sqlalchemy import select

from app.logger import logger
from app.stylist.dto import StylistResponse
from app.stylist.models_user import UserProfile
from app.stylist.persona import extract_preferences_from_text, apply_extracted_preferences
from app.stylist.state import AgentState


async def profile_update_node(state: AgentState) -> dict:
    """
    Handles user requests to update their style preferences mid-session.
    Extracts structured preferences from the message and persists them.
    """
    logger.info("[AgentFlow] Entering profile_update_node")
    db_session = state["db_session"]
    user_preferences = state["user_preferences"]
    message = state["message"]

    # Look up the UserProfile from the preferences' user_id
    user_q = select(UserProfile).where(UserProfile.id == user_preferences.user_id)
    res = await db_session.execute(user_q)
    user_profile = res.scalar_one()

    extracted = await extract_preferences_from_text(message)
    updated_keys = await apply_extracted_preferences(
        db_session, user_profile, user_preferences, extracted,
    )

    if updated_keys:
        keys_str = ", ".join(updated_keys)
        answer = (
            f"Done! I've updated your {keys_str}. "
            "I'll keep that in mind for future recommendations."
        )
    else:
        answer = (
            "I wasn't able to pick out specific preferences from that. "
            "Could you tell me more specifically what you'd like to update? "
            "For example: preferred colors, fits, sizes, or budget range."
        )

    response = StylistResponse(
        answer=answer,
        intent=state["intent"],
    )
    return {"response": response}
