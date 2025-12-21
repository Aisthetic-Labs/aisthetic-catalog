import json
from typing import List
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.dto import CatalogSearchRequest, CatalogFilter
from app.catalog.models_tenant import Product
from app.catalog.search import search_products
from app.core.config import settings
from app.llm.client import get_chat_client
from app.logger import logger
from app.stylist.chat_context import get_chat_context_summarizer
from app.stylist.dto import StylistResponse, ChatTurn
from app.stylist.intent_detection import detect_intent
from app.stylist.intents import StylistIntent
from app.stylist.persona import (
    build_persona_context,
    append_user_event,
    get_or_create_user_profile,
)
from app.stylist.query_completion import (
    complete_stylist_query,
    CompletedStylistQuery,
)
from app.stylist.state import AgentState

# --- Helper Functions ---

async def _load_products_by_ids(
        session: AsyncSession,
        product_ids: List[UUID],
) -> List[Product]:
    if not product_ids:
        return []
    q = select(Product).where(Product.id.in_(product_ids))
    res = await session.execute(q)
    return res.scalars().all()


def _serialize_product_for_prompt(p: Product) -> dict:
    return {
        "id": str(p.id),
        "title": p.title,
        "description": p.description,
        "category": p.category,
        "sub_category": p.sub_category,
        "gender": p.gender,
        "color": p.color_primary,
        "fit": p.fit,
        "style_tags": p.style_tags,
        "occasion_tags": p.occasion_tags,
        "fabric": p.fabric,
        "price": float(p.price),
        "currency": p.currency,
        "brand": p.brand,
        "pattern": p.pattern,
    }


def _filters_from_completed_query(cq: CompletedStylistQuery) -> CatalogFilter:
    price_min = cq.price_min
    price_max = cq.price_max

    color = cq.colors[0] if cq.colors else None
    gender = cq.gender
    category = cq.garment_types[0] if cq.garment_types else None

    return CatalogFilter(
        category=category,
        color=[color] if color else None,
        gender=gender,
        price_min=price_min,
        price_max=price_max,
    )

# --- LangGraph Nodes ---

async def initialize_node(state: AgentState) -> dict:
    """
    Gathers basic context: persona summary, user profile, chat context, and intent.
    This runs at the start of every request.
    """
    session = state["session"]
    external_user_id = state["external_user_id"]
    merchant_id = state["merchant_id"]
    
    logger.info(f"[AgentFlow] Entering initialize_node for user={external_user_id}")

    # 1) Build/Load Persona Context
    persona_json = await build_persona_context(session, external_user_id)
    # 2) Get/Create User Profile
    user_profile = await get_or_create_user_profile(session, external_user_id)
    
    # 3) Build Chat Context Summary (recent history, summarized)
    chat_context_summarizer = get_chat_context_summarizer()
    chat_context = await chat_context_summarizer.build_context(
        merchant_id=merchant_id,
        external_user_id=external_user_id,
        incoming_history=state["history"],
        current_user_message=state["message"],
    )
    
    # 4) Detect User Intent (e.g., search, styling, small talk)
    intent = await detect_intent(state["message"])
    logger.info(f"[AgentFlow] Detected intent: {intent.value}")
    
    return {
        "persona_json": persona_json,
        "user_profile": user_profile,
        "chat_context": chat_context,
        "intent": intent,
        "candidate_products": [],
        "mode": "freeform"
    }

async def product_search_node(state: AgentState) -> dict:
    """
    Handles search-related intents by querying OpenSearch.
    This node is only visited if the intent requires product candidates.
    """
    intent = state["intent"]
    merchant_id = state["merchant_id"]
    session = state["session"]
    message = state["message"]
    history = state["history"]
    compare_product_ids = state["compare_product_ids"]
    
    logger.info(f"[AgentFlow] Entering product_search_node for intent: {intent.value}")
    
    candidate_products = []
    mode = "freeform"
    
    # Prepare history for query completion LLM
    history_turns = [ChatTurn(role=h.role, message=h.message) for h in history]

    # --- Routing by intent within search node ---
    if intent == StylistIntent.PRODUCT_COMPARISON:
        mode = "compare"
        if not compare_product_ids:
            # If no IDs provided, use LLM to extract a search query and filter
            cq = await complete_stylist_query(history_turns, message)
            filters = _filters_from_completed_query(cq)
            search_req = CatalogSearchRequest(
                query_text=cq.standalone_query or message,
                filters=filters,
                limit=4,
            )
            logger.info(f"[AgentFlow] Product comparison search req: {search_req}")
            search_hits = await search_products(merchant_id, search_req)
            compare_ids = [UUID(h["product_id"]) for h in search_hits[:2]]
        else:
            compare_ids = compare_product_ids

        products = await _load_products_by_ids(session, compare_ids)
        candidate_products = [_serialize_product_for_prompt(p) for p in products]

    elif intent == StylistIntent.OCCASION_STYLING:
        mode = "occasion"
        # Extract occasion and filters via LLM
        cq = await complete_stylist_query(history_turns, message)
        filters = _filters_from_completed_query(cq)
        query_text = cq.standalone_query or f"outfit for {cq.occasion or message}"
        search_req = CatalogSearchRequest(
            query_text=query_text,
            filters=filters,
            limit=20,
        )
        logger.info(f"[AgentFlow] Occasion styling search req: {search_req}")
        hits = await search_products(merchant_id, search_req)
        ids = [UUID(h["product_id"]) for h in hits]
        products = await _load_products_by_ids(session, ids)
        candidate_products = [_serialize_product_for_prompt(p) for p in products]

    elif intent in (StylistIntent.DIRECT_PRODUCT_SEARCH, StylistIntent.GENERAL_STYLING):
        mode = "freeform"
        # Standard product discovery
        cq = await complete_stylist_query(history_turns, message)
        filters = _filters_from_completed_query(cq)
        search_req = CatalogSearchRequest(
            query_text=cq.standalone_query or message,
            filters=filters,
            limit=20,
        )
        logger.info(f"[AgentFlow] Direct/General styling search req: {search_req}")
        hits = await search_products(merchant_id, search_req)
        ids = [UUID(h["product_id"]) for h in hits]
        products = await _load_products_by_ids(session, ids)
        candidate_products = [_serialize_product_for_prompt(p) for p in products]

    logger.info(f"[AgentFlow] Found {len(candidate_products)} candidate products")
    return {"candidate_products": candidate_products, "mode": mode}

async def generate_response_node(state: AgentState) -> dict:
    """
    Calls the Stylist LLM to generate the final response message.
    It takes persona, candidate products, and chat context into account.
    """
    logger.info(f"[AgentFlow] Entering generate_response_node")
    persona_json = state["persona_json"]
    candidate_products = state["candidate_products"]
    mode = state["mode"]
    chat_context = state["chat_context"]
    
    system_prompt = (
        "You are Aisthetic, a playful, hype but honest AI fashion stylist for Gen Z and young millennials.\n"
        "Your vibe: casual, friendly, confident. No corporate tone.\n\n"
        "Hard rules:\n"
        "- Answer in ONLY 1–2 sentences, max 40 words total.\n"
        "- You may use at most ONE emoji, and only if it feels natural.\n"
        "- Respect the user's style preferences and constraints from persona but go outside if nothing is available in preferences or user asks you to.\n"
        "- All conversational context (including the latest user ask) is provided via chat_context. Treat chat_context.current_user_message as the canonical ask, and if it is missing, infer intent from chat_context.conversation_window or recent_user_requests.\n"
        "- Use chat_context.conversation_window, recent_user_requests, recent_stylist_answers, and recent_recommended_product_ids to stay consistent with the thread, follow up on past advice, and avoid repeating products.\n"
        "- Recommend only from the candidate_products list. Never invent products.\n"
        "- If nothing fits well, say that honestly and suggest what to look for instead (still in 1–2 sentences).\n\n"
        "Output format (JSON ONLY, no extra text):\n"
        "{\n"
        '  "answer": "<your short message>",\n'
        '  "recommended_product_ids": ["product_id_1", "product_id_2"],\n'
        '  "chosen_product_id": "product_id_1_or_null"\n'
        "}\n"
        "Do not add any other keys. Do not add explanations or markdown."
    )

    user_payload = {
        "persona": persona_json,
        "mode": mode,
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
                    "Here are the user persona, the chat_context summary (conversation_window, recent requests/answers, recommendations, current_user_message), the current mode, and the candidate products.\n"
                    "chat_context.current_user_message is the canonical latest user ask. Use the other chat_context fields to stay consistent with prior turns, resolve ambiguities, and avoid repeating recommendations.\n"
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
    chosen_id = parsed.get("chosen_product_id")
    chosen_uuid = UUID(chosen_id) if chosen_id else None

    response = StylistResponse(
        answer=parsed.get("answer", ""),
        recommended_product_ids=rec_ids,
        chosen_product_id=chosen_uuid,
        intent=state["intent"]
    )
    return {"response": response}

async def profile_update_node(state: AgentState) -> dict:
    """
    Handles user requests to update their style preferences.
    """
    logger.info(f"[AgentFlow] Entering profile_update_node")
    session = state["session"]
    user_profile = state["user_profile"]
    message = state["message"]
    
    answer = (
        "Got it, I’ve updated your style preferences based on what you said. "
        "I’ll keep that in mind for future recommendations."
    )
    # Log the update event
    await append_user_event(
        session,
        user_profile,
        event_type="profile_update",
        product_id=None,
        context={"message": message},
    )
    # Note: Commit happens later in finalize_node
    
    response = StylistResponse(
        answer=answer,
        recommended_product_ids=[],
        chosen_product_id=None,
        intent=state["intent"],
    )
    return {"response": response, "mode": "profile_update"}

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

async def try_on_node(state: AgentState) -> dict:
    """
    Handoff for virtual try-on requests. (Future functionality)
    """
    logger.info(f"[AgentFlow] Entering try_on_node")
    session = state["session"]
    user_profile = state["user_profile"]
    message = state["message"]
    
    answer = (
        "I can help you choose what to try, and soon I’ll be able to show it on you. "
        "For now, tell me which product you’re looking at and I’ll style it for you."
    )
    await append_user_event(
        session,
        user_profile,
        event_type="try_on_request",
        product_id=None,
        context={"message": message},
    )
    
    response = StylistResponse(
        answer=answer,
        recommended_product_ids=[],
        chosen_product_id=None,
        intent=state["intent"],
    )
    return {"response": response, "mode": "try_on_request"}

async def finalize_node(state: AgentState) -> dict:
    """
    The final step: persists user events, commits the transaction,
    and updates the chat session history in Redis.
    """
    logger.info(f"[AgentFlow] Entering finalize_node")
    session = state["session"]
    user_profile = state["user_profile"]
    response = state["response"]
    intent = state["intent"]
    mode = state["mode"]
    message = state["message"]
    merchant_id = state["merchant_id"]
    external_user_id = state["external_user_id"]
    
    # 1) Log the primary event for product discovery intents
    if intent in (StylistIntent.PRODUCT_COMPARISON, StylistIntent.OCCASION_STYLING,
                  StylistIntent.DIRECT_PRODUCT_SEARCH, StylistIntent.GENERAL_STYLING):
        await append_user_event(
            session,
            user_profile,
            event_type="stylist_question",
            product_id=response.chosen_product_id,
            context={
                "intent": intent.value,
                "mode": mode,
                "message": message,
                "recommended_product_ids": [str(x) for x in response.recommended_product_ids],
            },
        )
    
    # 2) Commit all DB changes accumulated in previous nodes
    await session.commit()

    # 3) Update Chat Context in Redis
    chat_context_summarizer = get_chat_context_summarizer()
    await chat_context_summarizer.append_exchange(
        merchant_id=merchant_id,
        external_user_id=external_user_id,
        user_message=message,
        stylist_response=response,
        intent=intent,
        mode=mode,
    )
    
    return {}
