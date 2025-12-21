from app.core.config import settings
from app.llm.client import get_chat_client
from app.logger import logger
from app.stylist.dto import StylistResponse
from app.stylist.intents import StylistIntent
from app.stylist.persona import append_user_event
from app.stylist.state import AgentState

async def small_talk_node(state: AgentState) -> dict:
    """
    Handles non-catalog related queries (greetings, general help, personality).
    """
    logger.info(f"[AgentFlow] Entering small_talk_node")
    session = state["session"]
    user_profile = state["user_profile"]
    message = state["message"]
    intent = state["intent"]
    
    chat_client = get_chat_client()
    completions_resp = await chat_client.chat.completions.create(
        model=settings.STYLIST_MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are Aisthetic, a friendly AI fashion stylist. "
                    "Answer briefly and helpfully. If the user asks about the product "
                    "or catalog, tell them how to ask styling/product queries."
                ),
            },
            {"role": "user", "content": message},
        ],
        max_tokens=400,
    )
    answer = completions_resp.choices[0].message.content or ""
    await append_user_event(
        session,
        user_profile,
        event_type="small_talk" if intent == StylistIntent.SMALL_TALK else "help",
        product_id=None,
        context={"message": message},
    )
    
    response = StylistResponse(
        answer=answer,
        recommended_product_ids=[],
        chosen_product_id=None,
        intent=intent,
    )
    return {"response": response}
