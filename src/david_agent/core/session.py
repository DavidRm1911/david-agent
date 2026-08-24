"""In-memory conversation state.

Fase 1 keeps this in a Python list — no persistence yet. SQLite-backed
sessions arrive in Fase 8, behind the same interface, so nothing above this
layer changes when that lands.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from david_agent.models.base import ModelMessage


@dataclass
class Session:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    messages: list[ModelMessage] = field(default_factory=list)

    def add_user(self, content: str) -> None:
        self.messages.append(ModelMessage(role="user", content=content))

    def add_assistant(self, content: str) -> None:
        self.messages.append(ModelMessage(role="assistant", content=content))
