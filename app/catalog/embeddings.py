from typing import List, Optional

from openai import AsyncOpenAI
import replicate

from app.core.config import settings

_oa_client: AsyncOpenAI | None = None
_rep_client: replicate.Client | None = None


def get_oa_client() -> AsyncOpenAI:
    global _oa_client
    if _oa_client is None:
        kwargs = {}
        if settings.EMBEDDING_API_BASE:
            kwargs["base_url"] = settings.EMBEDDING_API_BASE

        _oa_client = AsyncOpenAI(
            api_key=settings.EMBEDDING_API_KEY,
            **kwargs,
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
        model=settings.EMBEDDING_MODEL_NAME,
        input=text,
    )
    return resp.data[0].embedding


async def embed_image_from_url(url: str) -> Optional[List[float]]:
    """
    Image → embedding using openai/clip on Replicate (768 dims).
    """
    client = get_rep_client()

    result = client.run(
        settings.REPLICATE_IMAGE_EMBEDDING_MODEL,
        input={"image": url},
    )

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