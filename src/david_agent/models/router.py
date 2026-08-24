"""Model Router — decides which provider handles a turn.

Fase 2 supports only manual selection (`/model <name>`). Rule-based and
scored auto-routing (`/route auto`, capability/cost/latency-aware selection)
land later behind this same `resolve()` call — the CLI and Agent Loop won't
need to change again when that happens.
"""

from __future__ import annotations

from david_agent.models.base import ModelProvider
from david_agent.models.registry import ModelRegistry


class ModelRouter:
    def __init__(self, registry: ModelRegistry, *, default: str | None = None) -> None:
        self._registry = registry
        self._manual = default or registry.names()[0]

    def set_manual(self, name: str) -> None:
        self._registry.get(name)  # raises KeyError if unknown — fail before switching
        self._manual = name

    def current(self) -> str:
        return self._manual

    def available(self) -> list[str]:
        return self._registry.names()

    def resolve(self) -> str:
        # Fase 2: always manual. Task-based/auto routing arrives later.
        return self._manual

    def get_provider(self) -> ModelProvider:
        return self._registry.get(self.resolve())
