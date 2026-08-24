"""Registry of available model providers.

Fase 1 registers a single provider by hand. Fase 2 adds a Router on top of
this — the registry itself never picks a model, it only looks one up by name.
"""

from __future__ import annotations

from david_agent.models.base import ModelProvider


class ModelRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ModelProvider] = {}
        self._default: str | None = None

    def register(self, provider: ModelProvider, *, default: bool = False) -> None:
        self._providers[provider.name] = provider
        if default or self._default is None:
            self._default = provider.name

    def get(self, name: str | None = None) -> ModelProvider:
        key = name or self._default
        if key is None or key not in self._providers:
            available = ", ".join(self._providers) or "(none)"
            raise KeyError(f"Unknown model '{key}'. Available: {available}")
        return self._providers[key]

    def names(self) -> list[str]:
        return list(self._providers)
