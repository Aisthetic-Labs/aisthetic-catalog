from __future__ import annotations

import httpx

from app.core.config import settings
from app.logger import logger

_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
_TIMEOUT = 3.0  # seconds — trend context is nice-to-have, don't block the pipeline


async def search_fashion_context(query: str, count: int = 5) -> str | None:
    """
    Search the web via Brave Search API and return a condensed text summary
    suitable for LLM context injection.

    Returns None if disabled, on error, or if no useful results found.
    """
    if not settings.BRAVE_SEARCH_ENABLED or not settings.BRAVE_SEARCH_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                _BRAVE_SEARCH_URL,
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": settings.BRAVE_SEARCH_API_KEY,
                },
                params={"q": query, "count": count},
            )
            resp.raise_for_status()
            data = resp.json()

        web_results = data.get("web", {}).get("results", [])
        if not web_results:
            return None

        snippets = []
        for r in web_results[:count]:
            title = r.get("title", "")
            description = r.get("description", "")
            if title or description:
                snippets.append(f"- {title}: {description}")

        if not snippets:
            return None

        summary = "\n".join(snippets)
        logger.info(f"[WebSearch] Got {len(snippets)} results for query='{query}'")
        return summary
    except Exception:
        logger.exception(f"[WebSearch] Failed to search for '{query}'")
        return None
