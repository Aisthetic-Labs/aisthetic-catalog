from __future__ import annotations

import asyncio

from tavily import AsyncTavilyClient

from app.core.config import settings
from app.logger import logger

_TIMEOUT = 3.0  # seconds — trend context is nice-to-have, don't block the pipeline


async def search_fashion_context(query: str, count: int = 5) -> str | None:
    """
    Search the web via Tavily and return a condensed text summary
    suitable for LLM context injection.

    Returns None if disabled, on error, or if no useful results found.
    """
    if not settings.TAVILY_SEARCH_ENABLED or not settings.TAVILY_API_KEY:
        return None
    try:
        client = AsyncTavilyClient(api_key=settings.TAVILY_API_KEY)
        response = await asyncio.wait_for(
            client.search(query, max_results=count),
            timeout=_TIMEOUT,
        )

        results = response.get("results", [])
        if not results:
            return None

        snippets = []
        for r in results[:count]:
            title = r.get("title", "")
            content = r.get("content", "")
            if title or content:
                snippets.append(f"- {title}: {content}")

        if not snippets:
            return None

        summary = "\n".join(snippets)
        logger.info(f"[WebSearch] Got {len(snippets)} results for query='{query}'")
        return summary
    except Exception:
        logger.exception(f"[WebSearch] Failed to search for '{query}'")
        return None
