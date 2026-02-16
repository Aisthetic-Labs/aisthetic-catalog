from enum import Enum


class StylistIntent(str, Enum):
    OCCASION_STYLING = "occasion_styling"
    DIRECT_PRODUCT_SEARCH = "direct_product_search"
    PROFILE_UPDATE = "profile_update"
    GENERAL_STYLING = "general_styling"
    SMALL_TALK = "small_talk"
    HELP_ABOUT_AISTHETIC = "help_about_aisthetic"
    TRY_ON_REQUEST = "try_on_request"  # for future
    FOLLOW_UP = "follow_up"
    ONBOARDING = "onboarding"  # internal only, never LLM-detected


STYLIST_INTENTS = [
    {
        "name": StylistIntent.OCCASION_STYLING.value,
        "description": "User wants outfit ideas for a specific event or occasion.",
        "examples": [
            "Style me for a beach vacation.",
            "What should I wear for a wedding reception?",
            "Help me pick an outfit for a Friday pub night.",
        ],
    },
    {
        "name": StylistIntent.DIRECT_PRODUCT_SEARCH.value,
        "description": "User wants to discover/browse garments with specific attributes.",
        "examples": [
            "Show me black slim fit shirts under 2000.",
            "I want a linen beige shirt for summer.",
            "Find me relaxed fit jeans for men.",
        ],
    },
    {
        "name": StylistIntent.PROFILE_UPDATE.value,
        "description": "User is stating preferences that should update their fashion profile.",
        "examples": [
            "I don't like bright colors anymore.",
            "I prefer oversized fits now.",
            "I usually wear size M in shirts.",
        ],
    },
    {
        "name": StylistIntent.GENERAL_STYLING.value,
        "description": "User wants generic styling advice, not necessarily bound to the catalog.",
        "examples": [
            "What colors suit wheatish skin tone?",
            "How do I style a black shirt for office?",
            "What should my wardrobe basics be?",
        ],
    },
    {
        "name": StylistIntent.SMALL_TALK.value,
        "description": "User is chatting casually or saying things not directly actionable for styling.",
        "examples": [
            "Hi, how are you?",
            "Who built you?",
            "You are funny.",
        ],
    },
    {
        "name": StylistIntent.HELP_ABOUT_AISTHETIC.value,
        "description": "User asks about what Aisthetic does or how to use the stylist.",
        "examples": [
            "What can you do?",
            "How does this stylist work?",
            "Can you help me try outfits?",
        ],
    },
    {
        "name": StylistIntent.TRY_ON_REQUEST.value,
        "description": "User is explicitly asking for virtual try-on.",
        "examples": [
            "Can I try this shirt on me?",
            "Show me how this would look on me.",
            "Do a virtual try-on for this dress.",
        ],
    },
    {
        "name": StylistIntent.FOLLOW_UP.value,
        "description": "User is asking a follow-up question, refining a previous query, or asking for more options based on what was just shown.",
        "examples": [
            "Show me more like these.",
            "Can you find these in blue?",
            "Any cheaper options?",
            "Show me some more please.",
            "Make it more casual."
        ],
    },
]