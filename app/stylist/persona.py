import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.stylist.models_user import UserProfile, UserPreferences
from app.llm.client import get_chat_client
from app.core.config import settings


async def find_user_profile(
    session: AsyncSession,
    external_user_id: str,
) -> UserProfile | None:
    """Return the profile for *external_user_id*, or None if not found."""
    q = select(UserProfile).where(UserProfile.external_user_id == external_user_id)
    res = await session.execute(q)
    return res.scalar_one_or_none()


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
        f"Date of Birth: {user.dob or 'Unknown'}\n"
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
                    "   styling brief written for an AI fashion salesperson (not the end user). "
                    "   Mention defining taste, key constraints, and anything the salesperson "
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


# ── Conversational preference extraction ──────────────────────────────

# Fields that live on the UserProfile table (not in JSONB)
_PROFILE_FIELDS = {"gender"}


async def extract_preferences_from_text(message: str) -> dict:
    """
    LLM call that pulls structured preference keys from free-form text.
    Returns {} when nothing useful can be extracted.
    """
    chat_client = get_chat_client()
    resp = await chat_client.chat.completions.create(
        model=settings.STYLIST_MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a fashion preference extractor. Given a user message, "
                    "extract any style preferences into a flat JSON object.\n\n"
                    "Possible keys (only include those clearly expressed):\n"
                    "  gender, liked_colors (list), disliked_colors (list),\n"
                    "  liked_fits (list), preferred_sizes (list), body_type,\n"
                    "  price_sensitivity, height_weight, preferred_shoe_size,\n"
                    "  preferred_bottom_sizes (list).\n\n"
                    "Rules:\n"
                    "- Only include keys the user explicitly or clearly implies.\n"
                    "- List values should be JSON arrays of strings.\n"
                    "- If nothing useful can be extracted, return {}.\n"
                    "- Output valid JSON only. No markdown, no commentary."
                ),
            },
            {"role": "user", "content": message},
        ],
        response_format={"type": "json_object"},
        max_tokens=300,
    )
    raw = resp.choices[0].message.content or "{}"
    return json.loads(raw)


async def apply_extracted_preferences(
    session: AsyncSession,
    user_profile: UserProfile,
    user_prefs: UserPreferences,
    extracted: dict,
) -> list[str]:
    """
    Split *extracted* data: profile-level fields go to UserProfile columns,
    everything else goes to UserPreferences JSONB. Re-generates persona.

    Returns a list of human-readable key names that were updated.
    """
    if not extracted:
        return []

    updated_keys: list[str] = []

    # 1) Profile-level columns
    profile_changed = False
    for field in _PROFILE_FIELDS:
        if field in extracted:
            setattr(user_profile, field, extracted[field])
            updated_keys.append(field.replace("_", " "))
            profile_changed = True

    if profile_changed:
        session.add(user_profile)
        await session.flush()

    # 2) Preference-level (JSONB)
    pref_changes = {k: v for k, v in extracted.items() if k not in _PROFILE_FIELDS}
    if pref_changes:
        updated_keys.extend(k.replace("_", " ") for k in pref_changes)
        await update_user_preferences(session, user_prefs, pref_changes)

    # If only profile fields changed, still regenerate persona
    if profile_changed and not pref_changes:
        await summarize_persona(session, user_profile, user_prefs)

    return updated_keys
