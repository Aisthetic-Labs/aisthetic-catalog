from __future__ import annotations

import json
from datetime import date

from app.core.config import settings
from app.llm.client import get_chat_client
from app.logger import logger
from app.stylist.dto import StylistResponse, QuickReply
from app.stylist.intents import StylistIntent
from app.stylist.models_user import UserProfile, UserPreferences
from app.stylist.persona import summarize_persona
from app.stylist.session_store import get_session_store
from app.stylist.state import AgentState

# Welcome assets (duplicated from stylist_routes to avoid circular import)
WELCOME_MESSAGE = (
    "Hey, I'm your AI stylist from Aisthetic \U0001f44b\n\n"
    "I can help you:\n"
    "- Pick outfits for occasions (weddings, dates, office, trips)\n"
    "- Decide between two garments\n"
    "- Discover pieces that match your style\n\n"
    "Tell me what you're shopping for, or pick an option below."
)

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
# Step definitions (order matters)
# ---------------------------------------------------------------------------

ONBOARDING_STEPS: list[dict] = [
    {
        "key": "awaiting_auth_choice",
        "next": "name_dob",
    },
    {
        "key": "name_dob",
        "prompt": (
            "Let's get you set up! What's your name and date of birth?\n\n"
            "For example: Arjun, 15 April 1996"
        ),
        "quick_replies": [],
        "next": "gender",
    },
    {
        "key": "gender",
        "prompt": "What's your gender?",
        "quick_replies": [
            QuickReply(label="Male", payload={"value": "male"}),
            QuickReply(label="Female", payload={"value": "female"}),
            QuickReply(label="Non-binary", payload={"value": "non-binary"}),
        ],
        "next": "fashion_taste",
    },
    {
        "key": "fashion_taste",
        "prompt": (
            "How would you describe your fashion taste in one line?\n\n"
            "Here are some ideas:\n"
            "- Sophisticated & Refined\n"
            "- Modern & Trendy\n"
            "- Distinctive & Artistic\n"
            "- Curated or Conservative\n"
            "- Traditional\n"
            "- Formals\n"
            "- Minimalist\n"
            "- Bold & Streetwear\n"
            "- Casual & Effortless\n\n"
            "Or describe your own vibe in one line!"
        ),
        "quick_replies": [
            QuickReply(label="Sophisticated & Refined", payload={"value": "Sophisticated & Refined"}),
            QuickReply(label="Modern & Trendy", payload={"value": "Modern & Trendy"}),
            QuickReply(label="Distinctive & Artistic", payload={"value": "Distinctive & Artistic"}),
            QuickReply(label="Minimalist", payload={"value": "Minimalist"}),
        ],
        "next": "body_type",
    },
    {
        "key": "body_type",
        "prompt": "What's your body type?",
        "quick_replies": [
            QuickReply(label="Slim", payload={"value": "slim"}),
            QuickReply(label="Athletic", payload={"value": "athletic"}),
            QuickReply(label="Average", payload={"value": "average"}),
            QuickReply(label="Curvy", payload={"value": "curvy"}),
            QuickReply(label="Plus-size", payload={"value": "plus-size"}),
        ],
        "next": "preferred_top_sizes",
    },
    {
        "key": "preferred_top_sizes",
        "prompt": "What's your usual top / shirt size?",
        "quick_replies": [
            QuickReply(label="XS", payload={"value": "XS"}),
            QuickReply(label="S", payload={"value": "S"}),
            QuickReply(label="M", payload={"value": "M"}),
            QuickReply(label="L", payload={"value": "L"}),
            QuickReply(label="XL", payload={"value": "XL"}),
            QuickReply(label="XXL", payload={"value": "XXL"}),
        ],
        "next": "preferred_bottom_sizes",
    },
    {
        "key": "preferred_bottom_sizes",
        "prompt": "What's your usual bottom / trouser waist size?",
        "quick_replies": [
            QuickReply(label="28", payload={"value": "28"}),
            QuickReply(label="30", payload={"value": "30"}),
            QuickReply(label="32", payload={"value": "32"}),
            QuickReply(label="34", payload={"value": "34"}),
            QuickReply(label="36", payload={"value": "36"}),
            QuickReply(label="38", payload={"value": "38"}),
        ],
        "next": "height_weight",
    },
    # --- Optional steps below ---
    {
        "key": "height_weight",
        "prompt": (
            "What's your height and weight? This helps us match apparel sizes better.\n\n"
            "For example: 5'10\", 75 kg"
        ),
        "quick_replies": [
            QuickReply(label="Skip", payload={"action": "skip"}),
        ],
        "optional": True,
        "next": "preferred_shoe_size",
    },
    {
        "key": "preferred_shoe_size",
        "prompt": "What's your shoe size?",
        "quick_replies": [
            QuickReply(label="UK 6", payload={"value": "UK 6"}),
            QuickReply(label="UK 7", payload={"value": "UK 7"}),
            QuickReply(label="UK 8", payload={"value": "UK 8"}),
            QuickReply(label="UK 9", payload={"value": "UK 9"}),
            QuickReply(label="UK 10", payload={"value": "UK 10"}),
            QuickReply(label="UK 11", payload={"value": "UK 11"}),
            QuickReply(label="Skip", payload={"action": "skip"}),
        ],
        "optional": True,
        "next": "liked_colors",
    },
    {
        "key": "liked_colors",
        "prompt": "Any colors you gravitate toward? You can pick one or list a few.",
        "quick_replies": [
            QuickReply(label="Black", payload={"value": "black"}),
            QuickReply(label="White", payload={"value": "white"}),
            QuickReply(label="Blue", payload={"value": "blue"}),
            QuickReply(label="Beige", payload={"value": "beige"}),
            QuickReply(label="Earth Tones", payload={"value": "earth tones"}),
            QuickReply(label="Pastels", payload={"value": "pastels"}),
            QuickReply(label="Skip", payload={"action": "skip"}),
        ],
        "optional": True,
        "next": "disliked_colors",
    },
    {
        "key": "disliked_colors",
        "prompt": "Any colors you'd rather avoid?",
        "quick_replies": [
            QuickReply(label="Neon", payload={"value": "neon"}),
            QuickReply(label="Pink", payload={"value": "pink"}),
            QuickReply(label="Orange", payload={"value": "orange"}),
            QuickReply(label="Yellow", payload={"value": "yellow"}),
            QuickReply(label="None", payload={"value": "none"}),
            QuickReply(label="Skip", payload={"action": "skip"}),
        ],
        "optional": True,
        "next": "liked_fits",
    },
    {
        "key": "liked_fits",
        "prompt": "What fits do you usually prefer?",
        "quick_replies": [
            QuickReply(label="Slim Fit", payload={"value": "slim fit"}),
            QuickReply(label="Regular", payload={"value": "regular"}),
            QuickReply(label="Relaxed", payload={"value": "relaxed"}),
            QuickReply(label="Oversized", payload={"value": "oversized"}),
            QuickReply(label="Skip", payload={"action": "skip"}),
        ],
        "optional": True,
        "next": "going_out_occasions",
    },
    {
        "key": "going_out_occasions",
        "prompt": "Where do you usually dress up for? Pick or list a few.",
        "quick_replies": [
            QuickReply(label="Casual", payload={"value": "casual"}),
            QuickReply(label="Office", payload={"value": "office"}),
            QuickReply(label="Party / Night Out", payload={"value": "party"}),
            QuickReply(label="Date Night", payload={"value": "date night"}),
            QuickReply(label="Travel", payload={"value": "travel"}),
            QuickReply(label="Skip", payload={"action": "skip"}),
        ],
        "optional": True,
        "next": "price_sensitivity",
    },
    {
        "key": "price_sensitivity",
        "prompt": "What's your usual budget range for fashion?",
        "quick_replies": [
            QuickReply(label="Budget", payload={"value": "budget"}),
            QuickReply(label="Mid-range", payload={"value": "mid-range"}),
            QuickReply(label="Premium", payload={"value": "premium"}),
            QuickReply(label="No Preference", payload={"value": "no preference"}),
            QuickReply(label="Skip", payload={"action": "skip"}),
        ],
        "optional": True,
        "next": "_finalize",
    },
]

_STEP_INDEX: dict[str, int] = {s["key"]: i for i, s in enumerate(ONBOARDING_STEPS)}

LOGIN_PLACEHOLDER = (
    "Login via OTP is coming soon! For now, please register to get started."
)


# ---------------------------------------------------------------------------
# LLM extraction helpers
# ---------------------------------------------------------------------------

async def _extract_name_dob(message: str) -> dict:
    """Use LLM to extract name and date of birth from free-text."""
    chat_client = get_chat_client()
    resp = await chat_client.chat.completions.create(
        model=settings.STYLIST_MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract the user's name and date of birth from the message.\n"
                    "Return JSON: {\"name\": \"...\", \"dob\": \"YYYY-MM-DD\"}\n"
                    "If the date of birth is unclear or missing, set dob to null.\n"
                    "If name is unclear, set name to null.\n"
                    "Output valid JSON only."
                ),
            },
            {"role": "user", "content": message},
        ],
        response_format={"type": "json_object"},
        max_tokens=100,
    )
    raw = resp.choices[0].message.content or "{}"
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_skip(message: str) -> bool:
    return message.strip().lower() == "skip"


def _step_config(key: str) -> dict:
    return ONBOARDING_STEPS[_STEP_INDEX[key]]


def _next_step_response(next_key: str, intent: StylistIntent) -> dict:
    """Build a StylistResponse that asks the question for *next_key*."""
    cfg = _step_config(next_key)
    return {
        "response": StylistResponse(
            answer=cfg["prompt"],
            recommended_product_ids=[],
            intent=intent,
            quick_replies=cfg.get("quick_replies", []),
        ),
    }


# ---------------------------------------------------------------------------
# Onboarding finalizer
# ---------------------------------------------------------------------------

async def _finalize_onboarding(state: AgentState, data: dict) -> dict:
    """Create UserProfile + UserPreferences from collected onboarding data."""
    db_session = state["db_session"]
    external_user_id = state["external_user_id"]
    chat_session_id = state["chat_session_id"]

    # Parse dob
    dob_value = None
    if data.get("dob"):
        try:
            dob_value = date.fromisoformat(data["dob"])
        except (ValueError, TypeError):
            pass

    # Create UserProfile
    profile = UserProfile(
        external_user_id=external_user_id,
        name=data.get("name"),
        dob=dob_value,
        gender=data.get("gender"),
        fashion_taste=data.get("fashion_taste"),
    )
    db_session.add(profile)
    await db_session.flush()

    # Build preferences dict from collected data
    pref_keys = [
        "body_type", "height_weight", "preferred_top_sizes",
        "preferred_bottom_sizes", "preferred_shoe_size",
        "liked_colors", "disliked_colors", "liked_fits",
        "going_out_occasions", "price_sensitivity",
    ]
    prefs_dict: dict = {}
    for k in pref_keys:
        v = data.get(k)
        if v and v.lower() not in ("skip", "none"):
            prefs_dict[k] = v

    # Map to existing preference key names used by search/persona
    if "liked_colors" in prefs_dict:
        prefs_dict["liked_colors"] = _to_list(prefs_dict["liked_colors"])
    if "disliked_colors" in prefs_dict:
        val = prefs_dict["disliked_colors"]
        prefs_dict["disliked_colors"] = _to_list(val)
    if "liked_fits" in prefs_dict:
        prefs_dict["liked_fits"] = _to_list(prefs_dict["liked_fits"])
    if "going_out_occasions" in prefs_dict:
        prefs_dict["liked_occasions"] = _to_list(prefs_dict.pop("going_out_occasions"))
    if "preferred_top_sizes" in prefs_dict:
        prefs_dict["preferred_sizes"] = _to_list(prefs_dict.pop("preferred_top_sizes"))
        # Keep bottom sizes as a separate key
    if "preferred_bottom_sizes" in prefs_dict:
        prefs_dict["preferred_bottom_sizes"] = _to_list(prefs_dict["preferred_bottom_sizes"])

    user_prefs = UserPreferences(user_id=profile.id, preferences=prefs_dict)
    db_session.add(user_prefs)
    await db_session.flush()

    # Generate initial persona
    await summarize_persona(db_session, profile, user_prefs)

    # Clear onboarding state from Redis
    store = get_session_store()
    await store.clear_onboarding_state(chat_session_id)

    logger.info(f"[Onboarding] Completed for user={external_user_id}")

    return {
        "response": StylistResponse(
            answer=WELCOME_MESSAGE,
            recommended_product_ids=[],
            intent=StylistIntent.ONBOARDING,
            quick_replies=WELCOME_QUICK_REPLIES,
        ),
        "user_preferences": user_prefs,
    }


def _to_list(val: str | list) -> list[str]:
    """Normalize a value to a list of strings."""
    if isinstance(val, list):
        return val
    return [v.strip() for v in val.split(",") if v.strip()]


# ---------------------------------------------------------------------------
# Main node
# ---------------------------------------------------------------------------

async def onboarding_node(state: AgentState) -> dict:
    """
    Multi-step onboarding node. Each invocation handles exactly one step,
    saves the user's answer to Redis, and returns the next question.
    """
    logger.info("[AgentFlow] Entering onboarding_node")
    chat_session_id = state["chat_session_id"]
    message = (state.get("message") or "").strip()
    intent = StylistIntent.ONBOARDING

    store = get_session_store()
    ob = await store.get_onboarding_state(chat_session_id)
    step = ob["step"] if ob else "awaiting_auth_choice"
    data = ob.get("data", {}) if ob else {}

    # --- Step: awaiting_auth_choice ---
    if step == "awaiting_auth_choice":
        if message.lower() in ("login", "log in", "signin", "sign in"):
            return {
                "response": StylistResponse(
                    answer=LOGIN_PLACEHOLDER,
                    recommended_product_ids=[],
                    intent=intent,
                    quick_replies=[
                        QuickReply(label="Register instead", payload={"action": "register"}),
                    ],
                ),
            }
        # Treat anything else (including "register") as registration start
        await store.set_onboarding_state(chat_session_id, "name_dob", data)
        return _next_step_response("name_dob", intent)

    # --- Step: name_dob ---
    if step == "name_dob":
        extracted = await _extract_name_dob(message)
        data["name"] = extracted.get("name")
        data["dob"] = extracted.get("dob")
        await store.set_onboarding_state(chat_session_id, "gender", data)
        return _next_step_response("gender", intent)

    # --- Step: gender ---
    if step == "gender":
        data["gender"] = message.lower()
        await store.set_onboarding_state(chat_session_id, "fashion_taste", data)
        return _next_step_response("fashion_taste", intent)

    # --- Step: fashion_taste ---
    if step == "fashion_taste":
        data["fashion_taste"] = message
        await store.set_onboarding_state(chat_session_id, "body_type", data)
        return _next_step_response("body_type", intent)

    # --- Generic handler for body_type through price_sensitivity ---
    if step in _STEP_INDEX:
        cfg = _step_config(step)
        is_optional = cfg.get("optional", False)
        next_key = cfg["next"]

        if is_optional and _is_skip(message):
            # Skip — don't save, just advance
            pass
        else:
            data[step] = message

        if next_key == "_finalize":
            return await _finalize_onboarding(state, data)

        await store.set_onboarding_state(chat_session_id, next_key, data)
        return _next_step_response(next_key, intent)

    # Fallback: shouldn't happen, but recover gracefully
    logger.warning(f"[Onboarding] Unknown step '{step}', resetting to awaiting_auth_choice")
    await store.set_onboarding_state(chat_session_id, "awaiting_auth_choice", {})
    return {
        "response": StylistResponse(
            answer="Something went wrong. Let's start over — would you like to register or log in?",
            recommended_product_ids=[],
            intent=intent,
            quick_replies=[
                QuickReply(label="Register", payload={"action": "register"}),
                QuickReply(label="Login", payload={"action": "login"}),
            ],
        ),
    }
