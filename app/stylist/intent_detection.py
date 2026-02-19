import json

from app.llm.client import chat_complete
from .intents import STYLIST_INTENTS, StylistIntent

INTENT_PROMPT = """
You are a fashion shopping intent classifier.
You will receive a user query delimited by <qs></qs>.
You must classify it into ONE of the intents defined below.

<intent>{intents}</intent>

<qs>{qs}</qs>

Return ONLY a JSON object with the key `name`, for example:
{{"name": "direct_product_search"}}

Do NOT explain anything.
"""


async def detect_intent(message: str) -> StylistIntent:
    content = INTENT_PROMPT.format(
        intents=json.dumps(STYLIST_INTENTS),
        qs=message
    )

    raw = await chat_complete(
        messages=[
            {"role": "system", "content": "Classify fashion shopping intents."},
            {"role": "user", "content": content},
        ],
        max_tokens=200,
        json_mode=True,
    )
    data = json.loads(raw)
    name = data.get("name") or StylistIntent.GENERAL_STYLING.value

    # fallback safeguard
    try:
        return StylistIntent(name)
    except ValueError:
        return StylistIntent.GENERAL_STYLING
