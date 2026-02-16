from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.redis import get_redis_client
from app.logger import logger

SessionData = dict[str, Any]


def _redis_key(chat_session_id: str) -> str:
    return f"stylist:session:{chat_session_id}"


def _onboarding_key(chat_session_id: str) -> str:
    return f"stylist:onboarding:{chat_session_id}"


class SessionStore:

    def __init__(self) -> None:
        self._redis = get_redis_client()
        self._ttl = settings.CHAT_SESSION_TTL_SECONDS

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_session(
        self,
        merchant_id: str,
        external_user_id: str,
        welcome_message: str,
    ) -> tuple[str, SessionData]:
        chat_session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        data: SessionData = {
            "chat_session_id": chat_session_id,
            "merchant_id": merchant_id,
            "external_user_id": external_user_id,
            "created_at": now,
            "updated_at": now,
            "history": [
                {"role": "assistant", "message": welcome_message},
            ],
        }

        await self._redis.set(
            _redis_key(chat_session_id),
            json.dumps(data, ensure_ascii=False),
            ex=self._ttl,
        )

        return chat_session_id, data

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_session(self, chat_session_id: str) -> SessionData | None:
        raw = await self._redis.get(_redis_key(chat_session_id))
        if raw:
            return json.loads(raw)
        return None

    # ------------------------------------------------------------------
    # Save (Redis)
    # ------------------------------------------------------------------

    async def save_session(self, chat_session_id: str, data: SessionData) -> None:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self._redis.set(
            _redis_key(chat_session_id),
            json.dumps(data, ensure_ascii=False),
            ex=self._ttl,
        )

    # ------------------------------------------------------------------
    # Onboarding state (separate Redis key)
    # ------------------------------------------------------------------

    async def get_onboarding_state(self, chat_session_id: str) -> dict | None:
        raw = await self._redis.get(_onboarding_key(chat_session_id))
        if raw:
            return json.loads(raw)
        return None

    async def set_onboarding_state(
        self, chat_session_id: str, step: str, data: dict | None = None,
    ) -> None:
        payload = {"step": step, "data": data or {}}
        await self._redis.set(
            _onboarding_key(chat_session_id),
            json.dumps(payload, ensure_ascii=False),
            ex=self._ttl,
        )

    async def clear_onboarding_state(self, chat_session_id: str) -> None:
        await self._redis.delete(_onboarding_key(chat_session_id))


_store_singleton: SessionStore | None = None


def get_session_store() -> SessionStore:
    global _store_singleton
    if _store_singleton is None:
        _store_singleton = SessionStore()
    return _store_singleton
