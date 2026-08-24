"""Storage interface for sessions/messages/tool calls/model calls
(CLAUDE.md §22). SQLite (sqlite.py) is Fase 8's implementation; a future
Postgres/Firestore backend implements the same interface without touching
any caller.

Agent defaults to NullMemoryStore — construction stays side-effect-free
(no disk I/O) unless something explicitly wires in a real store, matching
how ModelRegistry/SkillRegistry/ToolRegistry all default to empty/inert.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SessionRecord:
    id: str
    agent_name: str
    created_at: str


class MemoryStore(ABC):
    @abstractmethod
    def create_session(self, session_id: str, agent_name: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_message(self, session_id: str, role: str, content: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_model_call(
        self,
        session_id: str,
        provider: str,
        model: str,
        input_tokens: int | None,
        output_tokens: int | None,
        cost_usd: float | None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_tool_call(self, session_id: str, tool_name: str, args: dict, result: str, error: str | None) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_sessions(self, limit: int = 20) -> list[SessionRecord]:
        raise NotImplementedError

    @abstractmethod
    def get_session_detail(self, session_id: str) -> dict:
        """Everything the webui dashboard needs for one session: messages,
        model_calls, tool_calls, each as a list of plain dicts."""
        raise NotImplementedError


class NullMemoryStore(MemoryStore):
    def create_session(self, session_id: str, agent_name: str) -> None:
        pass

    def save_message(self, session_id: str, role: str, content: str) -> None:
        pass

    def save_model_call(self, session_id, provider, model, input_tokens, output_tokens, cost_usd) -> None:
        pass

    def save_tool_call(self, session_id, tool_name, args, result, error) -> None:
        pass

    def list_sessions(self, limit: int = 20) -> list[SessionRecord]:
        return []

    def get_session_detail(self, session_id: str) -> dict:
        return {"messages": [], "model_calls": [], "tool_calls": []}
