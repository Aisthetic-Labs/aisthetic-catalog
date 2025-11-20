from openai import AsyncOpenAI
from app.core.config import settings

_chat_client: AsyncOpenAI | None = None


def get_chat_client() -> AsyncOpenAI:
    global _chat_client
    if _chat_client is None:

        _chat_client = AsyncOpenAI(
            api_key=settings.EMBEDDING_API_KEY
        )
    return _chat_client