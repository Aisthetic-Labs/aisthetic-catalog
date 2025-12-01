from typing import List
from uuid import UUID
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.dto import CatalogSearchRequest, CatalogFilter
from app.catalog.models_tenant import Product
from app.catalog.search import search_products
from app.core.config import settings
from app.llm.client import get_chat_client
from app.logger import logger
from app.stylist.dto import StylistChatRequest, StylistResponse, ChatTurn
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


async def _stylist_llm_call(
        persona_json: str,
        user_message: str,
        candidate_products: List[dict],
        mode: str = "freeform",
) -> StylistResponse:
    """
    mode: "freeform", "compare", "occasion"
    """

    system_prompt = (
        "You are Aisthetic, a playful, hype but honest AI fashion stylist for Gen Z and young millennials.\n"
        "Your vibe: casual, friendly, confident. No corporate tone.\n\n"
        "Hard rules:\n"
        "- Answer in ONLY 1–2 sentences, max 40 words total.\n"
        "- You may use at most ONE emoji, and only if it feels natural.\n"
        "- Respect the user's style preferences and constraints from persona.\n"
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
        "user_message": user_message,
        "candidate_products": candidate_products,
    }

    chat_client = get_chat_client()
    resp = await chat_client.chat.completions.create(
        model=settings.STYLIST_MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    "Here is the user persona, the current mode, the user message, and candidate products.\n"
                    "Think through your reasoning silently, but DO NOT write the reasoning out.\n"
                    "Respond ONLY with a single JSON object matching the specified schema.\n\n"
                    f"INPUT:\n{user_payload}"
                ),
            },
        ],
        response_format={"type": "json_object"},
        max_tokens=200,  # shorter to discourage rambly answers
    )

    content = resp.choices[0].message.content

    parsed = json.loads(content)

    rec_ids = [UUID(pid) for pid in parsed.get("recommended_product_ids", [])]
    chosen_id = parsed.get("chosen_product_id")
    chosen_uuid = UUID(chosen_id) if chosen_id else None

    return StylistResponse(
        answer=parsed.get("answer", ""),
        recommended_product_ids=rec_ids,
        chosen_product_id=chosen_uuid,
    )


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


async def handle_stylist_chat(
        merchant_id: str,
        session: AsyncSession,
        req: StylistChatRequest,
) -> StylistResponse:
    # 1) persona context
    persona_json = await build_persona_context(session, req.external_user_id)
    # logger.info(f"Built persona JSON: {persona_json}")
    # 2) detect intent
    intent = await detect_intent(req.message)
    logger.info(f"Detected stylist intent: {intent.value}")

    # 3) get or create user profile (for logging)
    user_profile = await get_or_create_user_profile(session, req.external_user_id)
    # logger.info(f"User profile ID: {user_profile.id}")

    # Convert history for query completion
    history_turns = [ChatTurn(role=h.role, message=h.message) for h in req.history]
    # pretty print history for logging
    for ht in history_turns:
        logger.info(f"History turn - {ht.role}: {ht.recommended_product_ids}:{ht.message}")
    logger.info(f"Converted {len(history_turns)} history turns for query completion.")

    # 4) routing by intent
    candidate_products = []
    mode = "freeform"

    if intent == StylistIntent.PRODUCT_COMPARISON:
        mode = "compare"
        # If product IDs are passed, use them; else we might in future parse from message.
        if not req.compare_product_ids:
            # fallback: search using query completion
            cq = await complete_stylist_query(history_turns, req.message)
            filters = _filters_from_completed_query(cq)
            search_req = CatalogSearchRequest(
                query_text=cq.standalone_query or req.message,
                filters=filters,
                limit=4,
            )
            logger.info(f"Product comparison search req: {search_req}")
            search_hits = await search_products(merchant_id, search_req)
            compare_ids = [UUID(h["product_id"]) for h in search_hits[:2]]
        else:
            compare_ids = req.compare_product_ids

        products = await _load_products_by_ids(session, compare_ids)
        candidate_products = [_serialize_product_for_prompt(p) for p in products]

    elif intent == StylistIntent.OCCASION_STYLING:
        mode = "occasion"
        cq = await complete_stylist_query(history_turns, req.message)
        filters = _filters_from_completed_query(cq)
        # strengthen the query with occasion
        query_text = cq.standalone_query or f"outfit for {cq.occasion or req.message}"
        search_req = CatalogSearchRequest(
            query_text=query_text,
            filters=filters,
            limit=20,
        )
        logger.info(f"Occasion styling search req: {search_req}")
        hits = await search_products(merchant_id, search_req)
        ids = [UUID(h["product_id"]) for h in hits]
        products = await _load_products_by_ids(session, ids)
        candidate_products = [_serialize_product_for_prompt(p) for p in products]

    elif intent == StylistIntent.DIRECT_PRODUCT_SEARCH or intent == StylistIntent.GENERAL_STYLING:
        mode = "freeform"
        cq = await complete_stylist_query(history_turns, req.message)
        filters = _filters_from_completed_query(cq)
        search_req = CatalogSearchRequest(
            query_text=cq.standalone_query or req.message,
            filters=filters,
            limit=20,
        )
        logger.info(f"Direct product search req: {search_req}")
        hits = await search_products(merchant_id, search_req)
        ids = [UUID(h["product_id"]) for h in hits]
        products = await _load_products_by_ids(session, ids)
        candidate_products = [_serialize_product_for_prompt(p) for p in products]

    elif intent == StylistIntent.PROFILE_UPDATE:
        # For MVP: ask LLM to rewrite preferences JSON + update user_profile,
        # then respond with confirmation. We can stub this now.
        # (You can wire a persona-update call later.)
        # Simple behavior for now:
        answer = (
            "Got it, I’ve updated your style preferences based on what you said. "
            "I’ll keep that in mind for future recommendations."
        )
        await append_user_event(
            session,
            user_profile,
            event_type="profile_update",
            product_id=None,
            context={"message": req.message},
        )
        await session.commit()
        return StylistResponse(
            answer=answer,
            recommended_product_ids=[],
            chosen_product_id=None,
            intent=intent,
        )

    elif intent in (StylistIntent.SMALL_TALK, StylistIntent.HELP_ABOUT_AISTHETIC):
        # No catalog context required, let LLM answer directly with persona.
        chat_client = get_chat_client()
        resp = await chat_client.chat.completions.create(
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
                {"role": "user", "content": req.message},
            ],
            max_tokens=400,
        )
        answer = resp.choices[0].message.content or ""
        await append_user_event(
            session,
            user_profile,
            event_type="small_talk" if intent == StylistIntent.SMALL_TALK else "help",
            product_id=None,
            context={"message": req.message},
        )
        await session.commit()
        return StylistResponse(
            answer=answer,
            recommended_product_ids=[],
            chosen_product_id=None,
            intent=intent,
        )

    elif intent == StylistIntent.TRY_ON_REQUEST:
        # Hand-off stub until Abhinav's try-on is wired
        answer = (
            "I can help you choose what to try, and soon I’ll be able to show it on you. "
            "For now, tell me which product you’re looking at and I’ll style it for you."
        )
        await append_user_event(
            session,
            user_profile,
            event_type="try_on_request",
            product_id=None,
            context={"message": req.message},
        )
        await session.commit()
        return StylistResponse(
            answer=answer,
            recommended_product_ids=[],
            chosen_product_id=None,
            intent=intent,
        )

    # 5) Call stylist LLM with persona + candidate products
    resp = await _stylist_llm_call(
        persona_json=persona_json,
        user_message=req.message,
        candidate_products=candidate_products,
        mode=mode,
    )

    # 6) log event
    await append_user_event(
        session,
        user_profile,
        event_type="stylist_question",
        product_id=resp.chosen_product_id,
        context={
            "intent": intent.value,
            "mode": mode,
            "message": req.message,
            "recommended_product_ids": [str(x) for x in resp.recommended_product_ids],
        },
    )
    await session.commit()

    # 7) return response with intent
    resp.intent = intent
    return resp
