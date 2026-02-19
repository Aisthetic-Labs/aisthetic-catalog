from openai import AsyncOpenAI
from app.core.config import settings

_openai_client: AsyncOpenAI | None = None
_anthropic_client = None   # anthropic.AsyncAnthropic, lazy-loaded


def _get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=settings.TEXT_EMBEDDING_API_KEY)
    return _openai_client


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _anthropic_client


async def chat_complete(
    messages: list[dict],
    max_tokens: int,
    json_mode: bool = False,
) -> str:
    """
    Provider-agnostic chat completion.
    messages: OpenAI-style list with optional {"role": "system", ...} entry.
    Returns the raw text content string.
    Controlled by settings.STYLIST_PROVIDER ("openai" or "anthropic").
    """
    if settings.STYLIST_PROVIDER == "anthropic":
        return await _anthropic_complete(messages, max_tokens)
    return await _openai_complete(messages, max_tokens, json_mode)


async def _openai_complete(messages, max_tokens, json_mode) -> str:
    client = _get_openai_client()
    kwargs = dict(
        model=settings.STYLIST_MODEL_NAME,
        messages=messages,
        max_tokens=max_tokens,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = await client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


async def _anthropic_complete(messages, max_tokens) -> str:
    client = _get_anthropic_client()
    system = next((m["content"] for m in messages if m["role"] == "system"), None)
    user_messages = [m for m in messages if m["role"] != "system"]
    kwargs = dict(
        model=settings.STYLIST_MODEL_NAME,
        messages=user_messages,
        max_tokens=max_tokens,
    )
    if system:
        kwargs["system"] = system
    resp = await client.messages.create(**kwargs)
    text = resp.content[0].text or ""
    return _strip_markdown_fences(text)


def _strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers Claude sometimes adds."""
    stripped = text.strip()
    if stripped.startswith("```"):
        # drop the opening fence line (```json or ```)
        stripped = stripped[stripped.index("\n") + 1:] if "\n" in stripped else stripped[3:]
        # drop the closing fence
        if stripped.endswith("```"):
            stripped = stripped[: stripped.rfind("```")]
    return stripped.strip()
