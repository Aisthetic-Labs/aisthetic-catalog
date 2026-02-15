import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.stylist.models_user import UserProfile, UserPreferences
from app.llm.client import get_chat_client
from app.core.config import settings


async def get_or_create_user_profile(
    session: AsyncSession,
    external_user_id: str,
) -> UserProfile:
    q = select(UserProfile).where(UserProfile.external_user_id == external_user_id)
    res = await session.execute(q)
    profile = res.scalar_one_or_none()
    if profile:
        return profile

    profile = UserProfile(external_user_id=external_user_id)
    session.add(profile)
    await session.flush()
    return profile


async def get_or_create_user_preferences(
    session: AsyncSession,
    user_id,
) -> UserPreferences:
    q = select(UserPreferences).where(UserPreferences.user_id == user_id)
    res = await session.execute(q)
    prefs = res.scalar_one_or_none()
    if prefs:
        return prefs

    prefs = UserPreferences(user_id=user_id, preferences={})
    session.add(prefs)
    await session.flush()
    return prefs


async def summarize_persona(
    session: AsyncSession,
    user: UserProfile,
    user_prefs: UserPreferences,
) -> str:
    """
    Generate a compact stylist persona summary from profile + preferences.
    Writes back into user_prefs.preferences["persona_summary"].
    """
    # build preference dict excluding cached persona_summary
    prefs_for_prompt = {
        k: v for k, v in (user_prefs.preferences or {}).items()
        if k != "persona_summary"
    }

    profile_text = (
        f"Name: {user.name or 'Unknown'}\n"
        f"Gender: {user.gender or 'Unknown'}\n"
        f"Preferences: {json.dumps(prefs_for_prompt, default=str)}"
    )

    chat_client = get_chat_client()
    resp = await chat_client.chat.completions.create(
        model=settings.STYLIST_MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a fashion persona engine. Given a user profile and their "
                    "style preferences, produce a JSON object that a downstream stylist "
                    "AI will use to personalize recommendations.\n\n"
                    "Rules:\n"
                    "1. Preserve every key from the input preferences. You may add new "
                    "   inferred keys but never remove existing ones.\n"
                    "2. Include a top-level \"natural_language_summary\" key: a 2-3 sentence "
                    "   styling brief written for an AI stylist (not the end user). "
                    "   Mention defining taste, key constraints, and anything the stylist "
                    "   should watch out for.\n"
                    "3. Only include information supported by the input data. Do not "
                    "   hallucinate preferences or interests.\n"
                    "4. Output valid JSON only. No markdown, no commentary."
                ),
            },
            {
                "role": "user",
                "content": f"PROFILE:\n{profile_text}",
            },
        ],
        response_format={"type": "json_object"},
        max_tokens=500,
    )

    persona_json = resp.choices[0].message.content or "{}"
    # write persona_summary back into preferences JSONB
    updated = dict(user_prefs.preferences or {})
    updated["persona_summary"] = persona_json
    user_prefs.preferences = updated
    session.add(user_prefs)
    await session.flush()
    return persona_json


async def update_user_preferences(
    session: AsyncSession,
    user_prefs: UserPreferences,
    changes: dict,
) -> None:
    """
    Merge *changes* into the preferences JSONB, then re-generate and
    persist the persona summary so it always reflects the latest state.
    """
    updated = dict(user_prefs.preferences or {})
    updated.update(changes)
    user_prefs.preferences = updated
    session.add(user_prefs)
    await session.flush()

    # re-summarize persona to reflect the new preferences
    user_q = select(UserProfile).where(UserProfile.id == user_prefs.user_id)
    res = await session.execute(user_q)
    user = res.scalar_one()
    await summarize_persona(session, user, user_prefs)
