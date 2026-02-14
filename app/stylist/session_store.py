from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.dynamo import dynamo_resource
from app.core.redis import get_redis_client
from app.logger import logger

SessionData = dict[str, Any]


def _redis_key(chat_session_id: str) -> str:
    return f"stylist:session:{chat_session_id}"


class SessionStore:

    def __init__(self) -> None:
        self._redis = get_redis_client()
        self._ttl = settings.CHAT_SESSION_TTL_SECONDS
        self._table_name = settings.DYNAMODB_TABLE_NAME

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

        asyncio.create_task(self._put_dynamo(chat_session_id, data))

        return chat_session_id, data

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_session(self, chat_session_id: str) -> SessionData | None:
        raw = await self._redis.get(_redis_key(chat_session_id))
        if raw:
            return json.loads(raw)

        # Cache miss – try DynamoDB recovery
        data = await self._get_dynamo(chat_session_id)
        if data is None:
            return None

        # Rehydrate into Redis
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self._redis.set(
            _redis_key(chat_session_id),
            json.dumps(data, ensure_ascii=False),
            ex=self._ttl,
        )
        logger.info("Session %s rehydrated from DynamoDB", chat_session_id)
        return data

    # ------------------------------------------------------------------
    # Save (Redis) + async DynamoDB sync
    # ------------------------------------------------------------------

    async def save_session(self, chat_session_id: str, data: SessionData) -> None:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self._redis.set(
            _redis_key(chat_session_id),
            json.dumps(data, ensure_ascii=False),
            ex=self._ttl,
        )

    async def sync_to_dynamo(self, chat_session_id: str, data: SessionData) -> None:
        """Fire-and-forget wrapper – schedule as asyncio.create_task."""
        try:
            await self._put_dynamo(chat_session_id, data)
        except Exception:
            logger.exception("DynamoDB sync failed for session %s", chat_session_id)

    # ------------------------------------------------------------------
    # DynamoDB internals
    # ------------------------------------------------------------------

    async def _put_dynamo(self, chat_session_id: str, data: SessionData) -> None:
        history = data.get("history", [])
        item = {
            "chat_session_id": chat_session_id,
            "merchant_id": data["merchant_id"],
            "external_user_id": data["external_user_id"],
            "created_at": data.get("created_at", ""),
            "updated_at": data.get("updated_at", ""),
            "history": json.dumps(history, ensure_ascii=False),
            "turn_count": len(history),
        }
        try:
            async with dynamo_resource() as dynamo:
                table = await dynamo.Table(self._table_name)
                await table.put_item(Item=item)
        except Exception:
            logger.exception("DynamoDB put_item failed for session %s", chat_session_id)

    async def _get_dynamo(self, chat_session_id: str) -> SessionData | None:
        try:
            async with dynamo_resource() as dynamo:
                table = await dynamo.Table(self._table_name)
                resp = await table.get_item(Key={"chat_session_id": chat_session_id})
            item = resp.get("Item")
            if not item:
                return None
            history_raw = item.get("history", "[]")
            return {
                "chat_session_id": chat_session_id,
                "merchant_id": item.get("merchant_id", ""),
                "external_user_id": item.get("external_user_id", ""),
                "created_at": item.get("created_at", ""),
                "updated_at": item.get("updated_at", ""),
                "history": json.loads(history_raw) if isinstance(history_raw, str) else history_raw,
            }
        except Exception:
            logger.exception("DynamoDB get_item failed for session %s", chat_session_id)
            return None


_store_singleton: SessionStore | None = None


def get_session_store() -> SessionStore:
    global _store_singleton
    if _store_singleton is None:
        _store_singleton = SessionStore()
    return _store_singleton
