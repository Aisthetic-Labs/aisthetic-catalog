from app.stylist.dto import QuickReply

WELCOME_MESSAGE = (
    "Welcome! I'm here to help you find exactly what you're looking for and make it fun \U0001f44b\n\n"
    "I can help you:\n"
    "- Find outfits for any occasion — weddings, dates, office, travel, casual\n"
    "- Discover pieces that match your daily style\n"
    "- Compare and decide between options\n\n"
    "What are you shopping for today?"
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

PREFERENCE_WELCOME_MESSAGE = (
    "Welcome! Before we start shopping, I'd love to learn about your style \U0001f3a8\n\n"
    "Tell me about your preferences — favorite colors, fits, sizes, or anything "
    "that helps me personalize your experience.\n\n"
    "Or just skip and dive straight into shopping!"
)

PREFERENCE_QUICK_REPLIES = [
    QuickReply(
        label="Skip",
        payload={"action": "skip_preferences"},
    ),
    QuickReply(
        label="I like casual & streetwear",
        payload={"action": "preference_text", "text": "I like casual and streetwear styles"},
    ),
    QuickReply(
        label="I prefer minimal & classic",
        payload={"action": "preference_text", "text": "I prefer minimal and classic styles"},
    ),
]
