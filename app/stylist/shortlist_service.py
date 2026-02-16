from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from redis.asyncio import Redis

from app.core.config import settings
from app.core.redis import get_redis_client
from app.logger import logger


@dataclass
class ShortlistResult:
    success: bool
    product_ids: List[str] = field(default_factory=list)
    message: str = ""


def _list_key(chat_session_id: str) -> str:
    return f"stylist:shortlist:{chat_session_id}"


def _set_key(chat_session_id: str) -> str:
    return f"stylist:shortlist_set:{chat_session_id}"


class ShortlistService:

    def __init__(self, redis_client: Redis | None = None) -> None:
        self._redis = redis_client or get_redis_client()
        self._max_size = settings.SHORTLIST_MAX_SIZE
        self._ttl = settings.CHAT_SESSION_TTL_SECONDS

    async def get_all(self, session_id: str) -> List[str]:
        return await self._redis.lrange(_list_key(session_id), 0, -1)

    async def add(self, session_id: str, product_ids: List[str]) -> ShortlistResult:
        lk = _list_key(session_id)
        sk = _set_key(session_id)

        added: list[str] = []
        for pid in product_ids:
            # duplicate check
            if await self._redis.sismember(sk, pid):
                logger.info(f"[Shortlist] Duplicate ignored: {pid}")
                continue

            # overflow check
            current_count = await self._redis.llen(lk)
            if current_count >= self._max_size:
                msg = f"Your shortlist is full ({self._max_size} items max). Remove some items before adding new ones."
                return ShortlistResult(
                    success=False,
                    product_ids=await self.get_all(session_id),
                    message=msg,
                )

            pipe = self._redis.pipeline()
            pipe.rpush(lk, pid)
            pipe.sadd(sk, pid)
            pipe.expire(lk, self._ttl)
            pipe.expire(sk, self._ttl)
            await pipe.execute()
            added.append(pid)

        all_ids = await self.get_all(session_id)
        count = len(all_ids)
        if added:
            msg = f"Added to your shortlist! You now have {count} item{'s' if count != 1 else ''} saved."
        else:
            msg = f"Those items are already in your shortlist. You have {count} item{'s' if count != 1 else ''} saved."
        return ShortlistResult(success=True, product_ids=all_ids, message=msg)

    async def remove(self, session_id: str, product_ids: List[str]) -> ShortlistResult:
        lk = _list_key(session_id)
        sk = _set_key(session_id)

        removed: list[str] = []
        not_found: list[str] = []
        for pid in product_ids:
            if not await self._redis.sismember(sk, pid):
                not_found.append(pid)
                continue
            pipe = self._redis.pipeline()
            pipe.lrem(lk, 0, pid)
            pipe.srem(sk, pid)
            await pipe.execute()
            removed.append(pid)

        all_ids = await self.get_all(session_id)
        if removed:
            msg = "Removed from your shortlist."
        else:
            msg = "Those items were not in your shortlist."
        return ShortlistResult(success=True, product_ids=all_ids, message=msg)

    async def clear(self, session_id: str) -> ShortlistResult:
        pipe = self._redis.pipeline()
        pipe.delete(_list_key(session_id))
        pipe.delete(_set_key(session_id))
        await pipe.execute()
        return ShortlistResult(success=True, product_ids=[], message="Your shortlist has been cleared.")

    async def count(self, session_id: str) -> int:
        return await self._redis.llen(_list_key(session_id))


_shortlist_singleton: ShortlistService | None = None


def get_shortlist_service() -> ShortlistService:
    global _shortlist_singleton
    if _shortlist_singleton is None:
        _shortlist_singleton = ShortlistService()
    return _shortlist_singleton
