import json
from uuid import UUID
from app.core.config import settings
from app.llm.client import get_chat_client
from app.logger import logger
from app.stylist.dto import StylistResponse
from app.stylist.state import AgentState

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
    
    system_prompt = (
        "You are Aisthetic, a playful, hype but honest AI fashion stylist for Gen Z and young millennials.\n"
        "Your vibe: casual, friendly, confident. No corporate tone.\n\n"
        "Hard rules:\n"
        "- Answer in ONLY 1–2 sentences, max 60 words total.\n"
        "- You may use at most ONE emoji, and only if it feels natural.\n"
        "- Respect the user's style preferences and constraints from persona but go outside if nothing is available in preferences or user asks you to.\n"
        "- All conversional context (including the latest user ask) is provided via chat_context. Treat chat_context.current_user_message as the canonical ask, and if it is missing, infer intent from chat_context.conversation_window or conversation_summary.\n"
        "- Use chat_context.conversation_window, conversation_summary, and recent_recommended_product_ids to stay consistent with the thread, follow up on past advice, and avoid repeating products.\n"
        "- Recommend only from the candidate_products list. Never invent products.\n"
        "- If nothing fits well, say that honestly and suggest what to look for instead (still in 1–2 sentences).\n\n"
        "Output format (JSON ONLY, no extra text):\n"
        "{\n"
        '  "answer": "<your short message>",\n'
        '  "recommended_product_ids": ["product_id_1", "product_id_2"]\n'
        "}\n"
        "Do not add any other keys. Do not add explanations or markdown."
    )

    user_payload = {
        "persona": persona_json,
        "intent": intent.value,
        "candidate_products": candidate_products,
        "chat_context": chat_context,
    }

    chat_client = get_chat_client()
    resp = await chat_client.chat.completions.create(
        model=settings.STYLIST_MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    "Here are the user persona, the chat_context summary (conversation_window, conversation_summary, recommendations, current_user_message), the detected intent, and the candidate products.\n"
                    "chat_context.current_user_message is the canonical latest user ask. Use conversation_summary and conversation_window to stay consistent with prior turns, resolve ambiguities, and avoid repeating recommendations.\n"
                    "Think through your reasoning silently, but DO NOT write the reasoning out.\n"
                    "Respond ONLY with a single JSON object matching the specified schema.\n\n"
                    f"INPUT:\n{user_payload}"
                ),
            },
        ],
        response_format={"type": "json_object"},
        max_tokens=200,
    )

    content = resp.choices[0].message.content
    parsed = json.loads(content)

    rec_ids = [UUID(pid) for pid in parsed.get("recommended_product_ids", [])]

    response = StylistResponse(
        answer=parsed.get("answer", ""),
        recommended_product_ids=rec_ids,
        intent=intent
    )
    return {"response": response}
