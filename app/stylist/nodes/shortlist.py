import json
from uuid import UUID

from app.llm.client import chat_complete
from app.logger import logger
from app.stylist.dto import StylistResponse
from app.stylist.intents import StylistIntent
from app.stylist.shortlist_service import get_shortlist_service
from app.stylist.state import AgentState

from .helpers import _load_products_by_ids, _serialize_product_for_prompt

SHORTLIST_RESOLVE_PROMPT = """\
You are a shortlist assistant for an AI fashion salesperson.
Your job is to interpret the user's request about their shortlist and resolve product references.

The user's shortlist (numbered):
{shortlist_items}

Recent product recommendations (numbered):
{recent_items}

Last 4 conversation entries:
{conversation_tail}

User message: "{user_message}"

Determine:
1. The operation: "add", "remove", "clear", or "show"
2. Which specific product IDs the user is referring to (resolve "the red one", "second item", "first and third", "all of these", etc.)

Rules:
- For "add": resolve IDs from recent recommendations. If user says "all of these" or "all", include all recent recommendations.
- For "remove": resolve IDs from the current shortlist. If user says "all" or "everything", treat as "clear" instead.
- For "show"/"clear": resolved_product_ids should be empty.
- If you cannot resolve a reference, return an empty resolved_product_ids list.
- Use the numbering to resolve positional references ("first", "second", "1st", "#2", etc.)

Return ONLY a JSON object:
{{"operation": "add"|"remove"|"clear"|"show", "resolved_product_ids": ["id1", ...], "explanation": "brief reason"}}
"""


async def shortlist_node(state: AgentState) -> dict:
    logger.info("[AgentFlow] Entering shortlist_node")

    db_session = state["db_session"]
    chat_session_id = state["chat_session_id"]
    message = state["message"]
    chat_context = state.get("chat_context") or {}
    shortlist_ids = state.get("shortlist_product_ids") or []

    shortlist_service = get_shortlist_service()

    # Load full product details for current shortlist
    shortlist_items_text = "(empty)"
    if shortlist_ids:
        shortlist_products = await _load_products_by_ids(
            db_session, [UUID(pid) for pid in shortlist_ids]
        )
        # Preserve order from Redis list
        products_by_id = {str(p.id): p for p in shortlist_products}
        ordered_shortlist = [products_by_id[pid] for pid in shortlist_ids if pid in products_by_id]
        if ordered_shortlist:
            shortlist_items_text = "\n".join(
                f"{i+1}. {_serialize_product_for_prompt(p)}"
                for i, p in enumerate(ordered_shortlist)
            )

    # Get recent recommendations from conversation window
    conversation_window = chat_context.get("conversation_window", [])
    recent_rec_ids = []
    for entry in reversed(conversation_window):
        if entry.get("role") == "assistant" and entry.get("recommended_product_ids"):
            recent_rec_ids = entry["recommended_product_ids"]
            break

    recent_items_text = "(none)"
    if recent_rec_ids:
        recent_products = await _load_products_by_ids(
            db_session, [UUID(pid) for pid in recent_rec_ids]
        )
        products_by_id_rec = {str(p.id): p for p in recent_products}
        ordered_recent = [products_by_id_rec[pid] for pid in recent_rec_ids if pid in products_by_id_rec]
        if ordered_recent:
            recent_items_text = "\n".join(
                f"{i+1}. {_serialize_product_for_prompt(p)}"
                for i, p in enumerate(ordered_recent)
            )

    # Last 4 conversation entries for context
    conversation_tail = conversation_window[-4:] if conversation_window else []

    # LLM call to resolve references + determine operation
    prompt = SHORTLIST_RESOLVE_PROMPT.format(
        shortlist_items=shortlist_items_text,
        recent_items=recent_items_text,
        conversation_tail=json.dumps(conversation_tail, default=str),
        user_message=message,
    )

    raw = await chat_complete(
        messages=[
            {"role": "system", "content": "Resolve shortlist operations and product references."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=300,
        json_mode=True,
    )
    parsed = json.loads(raw or "{}")
    operation = parsed.get("operation", "show")
    resolved_ids = parsed.get("resolved_product_ids", [])
    explanation = parsed.get("explanation", "")

    logger.info(f"[Shortlist] operation={operation}, resolved_ids={resolved_ids}, explanation={explanation}")

    # Execute the operation
    if operation == "add":
        if not resolved_ids:
            answer = "I couldn't figure out which product you'd like to save. Could you be more specific?"
            updated_ids = shortlist_ids
        else:
            result = await shortlist_service.add(chat_session_id, resolved_ids)
            answer = result.message
            updated_ids = result.product_ids

    elif operation == "remove":
        if not resolved_ids:
            answer = "I couldn't figure out which item to remove. Could you be more specific?"
            updated_ids = shortlist_ids
        else:
            result = await shortlist_service.remove(chat_session_id, resolved_ids)
            answer = result.message
            updated_ids = result.product_ids

    elif operation == "clear":
        result = await shortlist_service.clear(chat_session_id)
        answer = result.message
        updated_ids = result.product_ids

    else:  # show
        if not shortlist_ids:
            answer = "Your shortlist is empty. Browse some products and save the ones you like!"
            updated_ids = []
        else:
            # Build a numbered list with product details
            shortlist_products = await _load_products_by_ids(
                db_session, [UUID(pid) for pid in shortlist_ids]
            )
            products_by_id = {str(p.id): p for p in shortlist_products}
            lines = []
            for i, pid in enumerate(shortlist_ids):
                p = products_by_id.get(pid)
                if p:
                    price_str = f"{p.currency} {p.price}" if p.currency else f"{p.price}"
                    lines.append(f"{i+1}. {p.title} — {p.color_primary}, {price_str}")
            answer = "Here's your shortlist:\n" + "\n".join(lines) if lines else "Your shortlist is empty."
            updated_ids = shortlist_ids

    response = StylistResponse(
        answer=answer,
        shortlisted_product_ids=[UUID(pid) for pid in updated_ids],
        intent=StylistIntent.SHORTLIST_MANAGEMENT,
    )

    return {
        "response": response,
        "shortlist_product_ids": updated_ids,
    }
