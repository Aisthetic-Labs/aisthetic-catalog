import asyncio
import random
from typing import Any, Dict, Optional
from typing import List

import replicate
from openai import AsyncOpenAI
from replicate.exceptions import ReplicateError

from app.catalog.rate_limiter import SimpleRateLimiter
from app.core.config import settings

_oa_client: AsyncOpenAI | None = None
_rep_client: replicate.Client | None = None

# Simple in-memory cache (use Redis/DB for persistence)
_embedding_cache: Dict[str, Any] = {}
# configure to match Replicate message: 6 requests/minute with burst 1
_rate_limiter = SimpleRateLimiter(rate_per_minute=6, burst=1)


def get_oa_client() -> AsyncOpenAI:
    global _oa_client
    if _oa_client is None:
        _oa_client = AsyncOpenAI(
            api_key=settings.TEXT_EMBEDDING_API_KEY
        )
    return _oa_client


def get_rep_client() -> replicate.Client:
    global _rep_client
    if _rep_client is None:
        if not settings.REPLICATE_API_TOKEN:
            raise RuntimeError("REPLICATE_API_TOKEN not set in .env")
        _rep_client = replicate.Client(api_token=settings.REPLICATE_API_TOKEN)
    return _rep_client


async def embed_text(text: str) -> List[float]:
    """
    Text → embedding using OpenAI text-embedding-3-small (1536 dims).
    """
    if not text:
        text = ""

    client = get_oa_client()
    resp = await client.embeddings.create(
        model=settings.TEXT_EMBEDDING_MODEL_NAME,
        input=text,
    )
    return resp.data[0].embedding


async def _call_replicate_with_retries(client, input: dict, *, max_retries: int = 6):
    backoff = 1.0
    for attempt in range(max_retries):
        await _rate_limiter.acquire()
        try:
            # run in thread to avoid blocking event loop
            return await asyncio.to_thread(client.run,settings.REPLICATE_IMAGE_EMBEDDING_MODEL,  input)
        except ReplicateError as e:
            status = getattr(e, "status", None)
            # attempt to extract retry seconds from error detail string if present
            retry_after: Optional[float] = None
            detail = getattr(e, "detail", "") or str(e)
            # look for integer in the message like "resets in ~9s" or "Retry-After: 9"
            import re
            m = re.search(r"(\d+)\s*s(ec(onds)?)?", detail)
            if m:
                retry_after = float(m.group(1))

            if status == 429:
                if retry_after is None:
                    # exponential backoff with jitter
                    sleep_time = min(backoff, 60.0) + random.random()
                else:
                    sleep_time = max(retry_after, 0.5) + random.random() * 0.5
                await asyncio.sleep(sleep_time)
                backoff = min(backoff * 2, 60.0)
                continue
            # non-rate-limit error -> re-raise
            raise

    # after retries
    raise RuntimeError("Replicate predictions failed after retries due to rate limits")


async def embed_image_from_url(image_url: str) -> Any:
    client = get_rep_client()
    key = f"replicate:embed:{image_url}"
    if key in _embedding_cache:
        return _embedding_cache[key]

    input_payload = {"image": image_url}
    result = await _call_replicate_with_retries(client, input_payload)
    # persist to cache
    _embedding_cache[key] = result

    # openai/clip on Replicate returns one 768-dim vector
    # In case it's wrapped, handle dict form too
    if isinstance(result, dict):
        if "image_embedding" in result:
            embedding = result["image_embedding"]
        elif "embedding" in result:
            embedding = result["embedding"]
        else:
            raise RuntimeError(f"Unexpected keys from openai/clip: {list(result.keys())}")
    else:
        embedding = result

    if not isinstance(embedding, list):
        raise RuntimeError(f"Unexpected embedding type from openai/clip: {type(embedding)}")

    return embedding
