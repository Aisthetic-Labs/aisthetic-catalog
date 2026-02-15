from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Sequence

from redis.asyncio import Redis

from app.core.config import settings
from app.core.redis import get_redis_client
from app.logger import logger
from app.stylist.dto import StylistResponse
from app.stylist.intents import StylistIntent

HistoryEntry = dict[str, Any]


@dataclass
class ChatSessionState:
    history: list[HistoryEntry] = field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: str | None) -> "ChatSessionState":
        if not raw:
            return cls()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Failed to decode chat session payload: %s", raw)
            return cls()
        history = data.get("history") or []
        return cls(history=history)

    def to_raw(self) -> str:
        return json.dumps({"history": self.history}, ensure_ascii=False)

    def trim(self, limit: int) -> None:
        if len(self.history) > limit:
            self.history = self.history[-limit:]


class ChatContextSummarizer:
    def __init__(self, redis_client: Redis | None = None):
        self._redis = redis_client or get_redis_client()
        self._history_limit = settings.CHAT_SESSION_STORAGE_TURNS
        self._product_tail = settings.CHAT_SESSION_SUMMARY_PRODUCT_LIMIT
        self._window = min(12, self._history_limit)

    async def build_context(
        self,
        chat_session_id: str,
        current_user_message: str | None = None,
    ) -> dict[str, Any]:
        key = self._session_key(chat_session_id)
        state = await self._get_state(key)

        summary = self._render_context(state.history)
        summary["total_turn_count"] = len(state.history)
        if current_user_message:
            summary["current_user_message"] = current_user_message
        return summary

    async def append_exchange(
        self,
        chat_session_id: str,
        user_message: str,
        stylist_response: StylistResponse,
        intent: StylistIntent | None = None,
    ) -> None:
        key = self._session_key(chat_session_id)
        state = await self._get_state(key)

        user_entry: HistoryEntry = {
            "role": "user",
            "message": user_message,
        }

        assistant_entry: HistoryEntry = {
            "role": "assistant",
            "message": stylist_response.answer,
        }

        recommended_ids = [
            str(pid) for pid in (stylist_response.recommended_product_ids or [])
        ]
        if recommended_ids:
            assistant_entry["recommended_product_ids"] = recommended_ids[
                : self._product_tail
            ]

        if stylist_response.chosen_product_id:
            assistant_entry["chosen_product_id"] = str(
                stylist_response.chosen_product_id
            )

        final_intent = stylist_response.intent or intent
        if final_intent:
            assistant_entry["intent"] = (
                final_intent.value
                if isinstance(final_intent, StylistIntent)
                else str(final_intent)
            )

        state.history.extend([user_entry, assistant_entry])
        state.trim(self._history_limit)
        await self._persist(key, state)

    async def reset_session(self, chat_session_id: str) -> None:
        key = self._session_key(chat_session_id)
        await self._redis.delete(key)

    async def _get_state(self, key: str) -> ChatSessionState:
        raw = await self._redis.get(key)
        return ChatSessionState.from_raw(raw)

    async def _persist(self, key: str, state: ChatSessionState) -> None:
        await self._redis.set(
            key,
            state.to_raw(),
            ex=settings.CHAT_SESSION_TTL_SECONDS,
        )

    @staticmethod
    def _session_key(chat_session_id: str) -> str:
        return f"stylist:session:{chat_session_id}"

    def _render_context(self, history: Sequence[HistoryEntry]) -> dict[str, Any]:
        window = list(history[-self._window :])
        summary_lines = [f"{e['role']}: {e['message']}" for e in window]
        recommended = self._collect_recent_recommendations(window)
        return {
            "conversation_window": window,
            "conversation_summary": "\n".join(summary_lines),
            "recent_recommended_product_ids": recommended,
        }

    def _collect_recent_recommendations(
        self, window: Sequence[HistoryEntry]
    ) -> list[str]:
        collected: list[str] = []
        seen: set[str] = set()
        for entry in reversed(window):
            if entry.get("role") != "assistant":
                continue
            for pid in entry.get("recommended_product_ids") or []:
                if pid in seen:
                    continue
                collected.append(pid)
                seen.add(pid)
                if len(collected) >= self._product_tail:
                    return collected
        return collected


_summarizer_singleton: ChatContextSummarizer | None = None


def get_chat_context_summarizer() -> ChatContextSummarizer:
    global _summarizer_singleton
    if _summarizer_singleton is None:
        _summarizer_singleton = ChatContextSummarizer()
    return _summarizer_singleton