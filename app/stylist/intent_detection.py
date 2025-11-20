import json

from app.core.config import settings
from app.llm.client import get_chat_client
from .intents import STYLIST_INTENTS, StylistIntent

INTENT_PROMPT = """
You are Aisthetic's intent classifier.
You will receive a user query delimited by <qs></qs>.
You must classify it into ONE of the intents defined below.

<intent>{intents}</intent>

<qs>{qs}</qs>

Return ONLY a JSON object with the key `name`, for example:
{{"name": "direct_product_search"}}

Do NOT explain anything.
"""


async def detect_intent(message: str) -> StylistIntent:
    chat_client = get_chat_client()
    content = INTENT_PROMPT.format(
        intents=json.dumps(STYLIST_INTENTS),
        qs=message
    )

    resp = await chat_client.chat.completions.create(
        model=settings.STYLIST_MODEL_NAME,
        messages=[
            {"role": "system", "content": "Classify fashion & styling intents."},
            {"role": "user", "content": content},
        ],
        response_format={"type": "json_object"},
        max_tokens=200,
    )

    raw = resp.choices[0].message.content or "{}"
    data = json.loads(raw)
    name = data.get("name") or StylistIntent.GENERAL_STYLING.value

    # fallback safeguard
    try:
        return StylistIntent(name)
    except ValueError:
        return StylistIntent.GENERAL_STYLING
