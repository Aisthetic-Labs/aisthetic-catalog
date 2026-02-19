from app.core.config import settings
from app.llm.client import get_chat_client
from app.logger import logger
from app.stylist.dto import StylistResponse
from app.stylist.state import AgentState

async def small_talk_node(state: AgentState) -> dict:
    """
    Handles non-catalog related queries (greetings, general help, personality).
    """
    logger.info(f"[AgentFlow] Entering small_talk_node")
    message = state["message"]
    intent = state["intent"]

    chat_client = get_chat_client()
    completions_resp = await chat_client.chat.completions.create(
        model=settings.STYLIST_MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an AI fashion salesperson embedded in an online store. "
                    "You're calm, friendly, and knowledgeable. "
                    "Answer briefly and helpfully. If the user asks about the product "
                    "or catalog, guide them toward describing what they're looking for."
                ),
            },
            {"role": "user", "content": message},
        ],
        max_tokens=400,
    )
    answer = completions_resp.choices[0].message.content or ""

    response = StylistResponse(
        answer=answer,
        intent=intent,
    )
    return {"response": response}
