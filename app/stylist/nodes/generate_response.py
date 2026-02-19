import json
from uuid import UUID
from app.core.config import settings
from app.llm.client import get_chat_client
from app.logger import logger
from app.stylist.dto import StylistResponse
from app.stylist.state import AgentState
from .helpers import _load_products_by_ids, _serialize_product_for_prompt

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
        "- When recommending products, briefly explain WHY each pick works for them — reference their style, the occasion, fabric, fit, or color.\n"
        "- Be concise but complete. Say enough to help the customer decide, no more. For simple asks, 1–2 sentences is plenty. For nuanced advice, take the space you need.\n"
        "- You may use at most ONE emoji, and only if it feels natural.\n"
        "- You have access to the customer's memory from past sessions (user_memories). Use these naturally — reference past preferences, previous purchases, or stated needs without being creepy about it.\n"
        "- If trend_context is provided, weave relevant trend insights into your advice naturally. Don't dump raw search results.\n\n"

        "Rules:\n"
        "- Respect the user's style preferences and constraints from persona, but go beyond them if nothing matches or the user asks you to.\n"
        "- All conversational context is provided via chat_context. Treat chat_context.current_user_message as the canonical ask; use conversation_window to stay consistent, follow up naturally, and avoid repeating products.\n"
        "- Recommend only from the candidate_products list. Never invent products.\n"
        "- If nothing fits well, say so honestly and suggest what to look for instead.\n"
        "- If the user's request is ambiguous, conflicting, or lacks detail, ask a brief clarifying question instead of guessing. Set recommended_product_ids to [] when clarifying.\n"
        "- Do not force recommendations when you're unsure — it's better to ask than to guess wrong.\n"
        "- The user has a shortlist of saved products (shortlisted_products). Avoid recommending items already shortlisted and acknowledge the shortlist when relevant.\n"
        "- When you recommend products (non-empty recommended_product_ids), ALWAYS append a short nudge line after your main message, separated by a newline. Examples: 'Save any you like to your shortlist, or ask me to refine!' / 'Shortlist your favorites or tell me what to tweak!' This nudge does NOT count toward the conciseness guideline.\n"
        "- When NOT recommending products (clarification, empty list), do NOT append the nudge line.\n\n"

        "Output format (JSON ONLY, no extra text):\n"
        "{\n"
        '  "answer": "<your message>",\n'
        '  "recommended_product_ids": ["product_id_1", "product_id_2"]\n'
        "}\n"
        "Do not add any other keys. Do not add explanations or markdown."
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
        max_tokens=512,
    )

    content = resp.choices[0].message.content
    parsed = json.loads(content)

    rec_ids = [UUID(pid) for pid in parsed.get("recommended_product_ids", [])]

    response = StylistResponse(
        answer=parsed.get("answer", ""),
        recommended_product_ids=rec_ids,
        shortlisted_product_ids=[UUID(pid) for pid in shortlist_ids],
        intent=intent
    )
    return {"response": response}
