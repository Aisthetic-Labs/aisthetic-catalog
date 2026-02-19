import json
from uuid import UUID
from app.core.config import settings
from app.llm.client import get_chat_client
from app.logger import logger
from app.stylist.dto import StylistResponse, ProductRecommendation
from app.stylist.intents import StylistIntent
from app.stylist.state import AgentState
from .helpers import _load_products_by_ids, _serialize_product_for_prompt


def _assemble_response(
    parsed: dict,
    candidate_products: list[dict],
    shortlist_ids: list[str],
    intent: StylistIntent,
) -> StylistResponse:
    opening = parsed.get("opening", "")
    recommendations_raw = parsed.get("recommendations", [])
    closing = parsed.get("closing")

    # Build product lookup from candidates
    products_by_id = {p["id"]: p for p in candidate_products}

    recommended_products = []
    answer_parts = [opening, ""]  # opening + blank line

    for i, rec in enumerate(recommendations_raw, 1):
        pid = rec.get("product_id", "")
        reason = rec.get("reason", "")
        product = products_by_id.get(pid, {})

        title = product.get("title", "Unknown")
        brand = product.get("brand")
        price = product.get("price", 0)
        currency = product.get("currency", "INR")
        image_url = product.get("image_url") or (product.get("images", [None])[0] if product.get("images") else None)
        color = product.get("color")

        # Formatted line for answer text
        brand_str = f" by {brand}" if brand else ""
        answer_parts.append(f"**{i}. {title}**{brand_str} — ₹{price:,.0f}")
        answer_parts.append(f"{reason}")
        answer_parts.append("")

        recommended_products.append(ProductRecommendation(
            product_id=UUID(pid), title=title, brand=brand,
            price=price, currency=currency, image_url=image_url,
            color=color, reason=reason,
        ))

    if closing:
        answer_parts.append(closing)

    # Add shortlist nudge when recommending
    if recommended_products:
        answer_parts.append("\nSave any you like to your shortlist, or ask me to refine!")

    rec_ids = [rp.product_id for rp in recommended_products]

    return StylistResponse(
        answer="\n".join(answer_parts).strip(),
        recommended_products=recommended_products,
        recommended_product_ids=rec_ids,
        shortlisted_product_ids=[UUID(pid) for pid in shortlist_ids],
        intent=intent,
    )


async def generate_response_node(state: AgentState) -> dict:
    """
    Calls the Stylist LLM to generate the final response message.
    It takes persona, candidate products, and chat context into account.
    """
    logger.info(f"[AgentFlow] Entering generate_response_node")
    persona_json = (state["user_preferences"].preferences or {}).get("persona_summary", "{}")
    candidate_products = state["candidate_products"]
    intent = state["intent"]
    chat_context = state["chat_context"]
    shortlist_ids = state.get("shortlist_product_ids") or []

    # Load shortlisted product details for context
    shortlisted_products_serialized = []
    if shortlist_ids:
        db_session = state["db_session"]
        shortlisted_products = await _load_products_by_ids(
            db_session, [UUID(pid) for pid in shortlist_ids]
        )
        shortlisted_products_serialized = [
            _serialize_product_for_prompt(p) for p in shortlisted_products
        ]

    system_prompt = (
        "You are an AI fashion salesperson embedded in an online store.\n"
        "Tone: calm, confident, and knowledgeable — like the best in-store advisor who listens first.\n"
        "Be warm and approachable, but never over-excited or pushy. Honesty builds trust.\n"
        "Read the room — mirror the customer's energy and language. If they're casual and brief, keep it light. If they're detailed and specific, match that depth.\n\n"

        "How you work:\n"
        "- Lead with genuine curiosity about what the customer needs.\n"
        "- You have access to the customer's memory from past sessions (user_memories). Use these naturally — reference past preferences, previous purchases, or stated needs without being creepy about it.\n"
        "- If trend_context is provided, weave relevant trend insights into your advice naturally. Don't dump raw search results.\n"
        "- You may use at most ONE emoji, and only if it feels natural.\n\n"

        "Recommendation guidelines:\n"
        "- When candidates are available, recommend at least 4 products to give the customer enough to compare. If fewer than 4 candidates exist, recommend all of them.\n"
        "- For each recommended product, write a brief 'reason' explaining WHY it works — reference the customer's style, occasion, fabric, fit, color, or persona.\n"
        "- Recommend only from the candidate_products list. Never invent products.\n"
        "- Avoid recommending products already in the customer's shortlist.\n"
        "- If nothing fits well, say so honestly in 'opening' and set recommendations to [].\n"
        "- If the request is ambiguous or lacks detail, ask a clarifying question in 'opening' and set recommendations to [].\n\n"

        "Context usage:\n"
        "- All conversational context is provided via chat_context. Treat chat_context.current_user_message as the canonical ask; use conversation_window to stay consistent, follow up naturally, and avoid repeating products.\n"
        "- The user has a shortlist of saved products (shortlisted_products). Avoid recommending items already shortlisted and acknowledge the shortlist when relevant.\n\n"

        "Output format (JSON ONLY, no extra text):\n"
        "{\n"
        '  "opening": "Brief intro/summary addressing the customer",\n'
        '  "recommendations": [\n'
        '    {"product_id": "uuid", "reason": "Why this pick works for them"}\n'
        "  ],\n"
        '  "closing": "Optional sign-off or null"\n'
        "}\n"
        "Do not add any other keys. Do not add explanations or markdown outside the JSON."
    )

    user_payload = {
        "persona": persona_json,
        "intent": intent.value,
        "candidate_products": candidate_products,
        "chat_context": chat_context,
        "shortlisted_products": shortlisted_products_serialized,
        "user_memories": state.get("user_memories") or [],
        "trend_context": state.get("trend_context"),
    }

    chat_client = get_chat_client()
    resp = await chat_client.chat.completions.create(
        model=settings.STYLIST_MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    "Here are the user persona, the chat_context (conversation_window, current_user_message), the detected intent, and the candidate products.\n"
                    "chat_context.current_user_message is the canonical latest user ask. Use conversation_window to stay consistent with prior turns, resolve ambiguities, and avoid repeating recommendations.\n"
                    "Think through your reasoning silently, but DO NOT write the reasoning out.\n"
                    "Respond ONLY with a single JSON object matching the specified schema.\n\n"
                    f"INPUT:\n{user_payload}"
                ),
            },
        ],
        response_format={"type": "json_object"},
        max_tokens=1024,
    )

    content = resp.choices[0].message.content
    parsed = json.loads(content)

    response = _assemble_response(parsed, candidate_products, shortlist_ids, intent)
    return {"response": response}
