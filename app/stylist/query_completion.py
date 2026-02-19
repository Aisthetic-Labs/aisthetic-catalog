import json
from typing import List, Dict, Any, Optional, Literal

from pydantic import BaseModel, field_validator
from app.llm.client import get_chat_client
from app.core.config import settings
from app.logger import logger


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    message: str


class CompletedStylistQuery(BaseModel):
    standalone_query: str
    garment_types: List[str] = []
    colors: List[str] = []
    gender: Optional[str] = None
    fit: Optional[str] = None
    occasion: Optional[str] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    sizes: List[str] = []
    web_search_query: Optional[str] = None

    @field_validator("garment_types", "colors", "sizes", mode="before")
    @classmethod
    def none_to_empty_list(cls, v):
        return v if v is not None else []


QUERY_COMPLETION_INSTRUCTIONS = """
You are a fashion shopping query normalizer.

You will receive:
- `conversation`: recent chat history as a list of {role, message}
- `last_human_message`: the latest user message
- `product_context`: optional text about the product the user is viewing

Your job:
1. Turn the user's request into a clear standalone text query suitable for product search.
2. Extract structured filters when possible:
   - garment_types: e.g. ["shirt", "t-shirt", "jeans"]
   - colors: e.g. ["black", "navy", "pastel pink"]
   - gender: "male", "female", "unisex" or null
   - fit: e.g. "slim", "oversized", "regular"
   - occasion: e.g. "wedding", "office", "party", "vacation"
   - price_min / price_max: numeric INR if mentioned
   - sizes: e.g. ["M", "L", "32", "UK8"] — clothing/shoe sizes mentioned
   - web_search_query: If the user's request involves current fashion trends, celebrity/cultural references, or seasonal style advice that goes beyond catalog search, write a concise web search query to find relevant context. Otherwise set to null. Examples: "men's summer fashion trends 2026", "Timothée Chalamet outfit style"

Return ONLY a JSON object with keys:
{
  "standalone_query": "...",
  "garment_types": [...],
  "colors": [...],
  "gender": "... or null",
  "fit": "... or null",
  "occasion": "... or null",
  "price_min": null or number,
  "price_max": null or number,
  "sizes": [...],
  "web_search_query": "... or null"
}
"""


async def complete_stylist_query(
    history: List[ChatTurn],
    last_message: str,
    product_context: str = "",
) -> CompletedStylistQuery:
    chat_client = get_chat_client()

    payload: Dict[str, Any] = {
        "conversation": [h.model_dump() for h in history],
        "last_human_message": last_message,
        "product_context": product_context,
    }
    logger.info(f"Qcompletion payload: {payload}")

    resp = await chat_client.chat.completions.create(
        model=settings.STYLIST_MODEL_NAME,
        messages=[
            {"role": "system", "content": QUERY_COMPLETION_INSTRUCTIONS.strip()},
            {
                "role": "user",
                "content": json.dumps(payload),
            },
        ],
        response_format={"type": "json_object"},
        max_tokens=400,
    )

    raw = resp.choices[0].message.content or "{}"
    data = json.loads(raw)
    logger.info(f"Qcompletion data: {data}")
    return CompletedStylistQuery(**data)