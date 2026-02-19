from app.llm.client import chat_complete
from app.logger import logger
from app.stylist.dto import StylistResponse
from app.stylist.state import AgentState

async def small_talk_node(state: AgentState) -> dict:
    """
    Handles non-catalog related queries (greetings, general help, personality).
    """
    logger.info("[AgentFlow] Entering small_talk_node")
    message = state["message"]
    intent = state["intent"]

    answer = await chat_complete(
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

    response = StylistResponse(
        answer=answer,
        intent=intent,
    )
    return {"response": response}
