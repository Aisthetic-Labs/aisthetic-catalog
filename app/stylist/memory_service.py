from __future__ import annotations

import asyncio
from functools import partial

from app.core.config import settings
from app.logger import logger

_client = None


def get_memory_client():
    """Lazy singleton for mem0 MemoryClient."""
    global _client
    if _client is None:
        from mem0 import MemoryClient

        _client = MemoryClient(api_key=settings.MEM0_API_KEY)
    return _client


async def recall_memories(user_id: str, query: str, limit: int = 5) -> list[dict]:
    """
    Semantically search the user's cross-session memory.
    Returns a list of memory dicts, e.g. [{"memory": "...", "score": 0.9}, ...].
    Returns [] if disabled or on error.
    """
    if not settings.MEM0_ENABLED or not settings.MEM0_API_KEY:
        return []
    try:
        client = get_memory_client()
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(
            None,
            partial(client.search, query, user_id=user_id, limit=limit),
        )
        memories = [
            {"memory": r.get("memory", ""), "score": r.get("score", 0)}
            for r in (results or [])
            if r.get("memory")
        ]
        logger.info(f"[Memory] Recalled {len(memories)} memories for user={user_id}")
        return memories
    except Exception:
        logger.exception("[Memory] Failed to recall memories")
        return []


async def store_interaction(user_id: str, messages: list[dict]) -> None:
    """
    Store a user↔assistant exchange in mem0.
    mem0 automatically extracts, deduplicates, and indexes relevant facts.
    No-op if disabled or on error.
    """
    if not settings.MEM0_ENABLED or not settings.MEM0_API_KEY:
        return
    try:
        client = get_memory_client()
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            partial(client.add, messages, user_id=user_id),
        )
        logger.info(f"[Memory] Stored interaction for user={user_id}")
    except Exception:
        logger.exception("[Memory] Failed to store interaction")
