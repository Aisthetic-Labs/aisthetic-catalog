from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import Optional

from app.stylist.models_user import UserProfile, UserEvent
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


async def append_user_event(
    session: AsyncSession,
    user: UserProfile,
    event_type: str,
    product_id=None,
    context: Optional[dict] = None,
) -> None:
    event = UserEvent(
        user_id=user.id,
        event_type=event_type,
        product_id=product_id,
        context=context or {},
    )
    session.add(event)


async def summarize_persona(session: AsyncSession, user: UserProfile) -> str:
    """
    Look at profile + recent events and generate a compact stylist persona summary.
    Also writes back to user.persona_summary.
    """
    events_q = (
        select(UserEvent)
        .where(UserEvent.user_id == user.id)
        .order_by(desc(UserEvent.created_at))
        .limit(50)
    )
    res = await session.execute(events_q)
    events = res.scalars().all()

    # build simple text view of historical behavior
    event_lines = []
    for e in events:
        line = f"{e.event_type}"
        if e.context:
            line += f" | ctx={e.context}"
        if e.product_id:
            line += f" | product_id={e.product_id}"
        event_lines.append(line)

    events_text = "\n".join(event_lines)

    # simple raw preference dump
    pref = user

    pref_text = f"""
Name: {pref.name or 'Unknown'}
Gender: {pref.gender or 'Unknown'}
Preferred sizes: {pref.preferred_sizes or []}
Body type: {pref.body_type or 'Unknown'}

Liked colors: {pref.liked_colors or []}
Disliked colors: {pref.disliked_colors or []}
Liked fits: {pref.liked_fits or []}
Liked styles: {pref.liked_styles or []}
Liked occasions: {pref.liked_occasions or []}
Price sensitivity: {pref.price_sensitivity or 'Unknown'}
    """.strip()

    chat_client = get_chat_client()
    resp = await chat_client.chat.completions.create(
        model=settings.STYLIST_MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a fashion persona summarizer. "
                    "Given profile fields and recent events, produce a concise JSON "
                    "describing the user's fashion persona with keys like "
                    "preferred_colors, avoid_colors, preferred_fits, style_vibes, "
                    "occasions, budget, and a short natural_language_summary."
                ),
            },
            {
                "role": "user",
                "content": f"PROFILE:\n{pref_text}\n\nEVENTS:\n{events_text}",
            },
        ],
        response_format={"type": "json_object"},
        max_tokens=350,
    )

    persona_json = resp.choices[0].message.content or "{}"
    user.persona_summary = persona_json
    session.add(user)
    await session.flush()
    return persona_json


async def build_persona_context(
    session: AsyncSession,
    external_user_id: str,
) -> str:
    """
    High-level entrypoint: ensure profile exists, and return persona summary text
    that can be dropped into stylist prompts.
    """
    user = await get_or_create_user_profile(session, external_user_id)

    # if we already have a persona summary, reuse it
    if user.persona_summary:
        return user.persona_summary

    # else build a fresh one
    return await summarize_persona(session, user)