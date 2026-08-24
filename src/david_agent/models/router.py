"""Model Router — decides which provider handles a turn.

Two modes: manual (`/model <name>`, Fase 2) and auto (`/route auto`,
CLAUDE.md §6). Auto is deterministic keyword rules over the turn's text,
never ML — the spec is explicit about that ("No crear un router basado en
machine learning inicialmente"). Each category names providers in priority
order; the router walks that list and picks the first one that is both
registered and actually declares the capability the category needs, so a
provider without vision support never gets handed a vision task just
because it's first in a hardcoded list. If nothing in the category matches
(provider missing, capability missing), it falls back to the manual
selection rather than raising — auto-routing degrading to manual is a
safe failure, an unhandled turn is not.
"""

from __future__ import annotations

from dataclasses import dataclass

from david_agent.models.base import ModelProvider
from david_agent.models.registry import ModelRegistry


@dataclass(frozen=True)
class RoutingRule:
    providers: tuple[str, ...]  # priority order
    requires: str | None = None  # ModelCapabilities field that must be True, if any


# Keyword sets are deliberately small and literal — this is a first pass of
# deterministic rules (CLAUDE.md §6), not an attempt at real intent
# classification. Spanish keywords included since that's how the turns
# calling this actually get typed.
_VISION_KEYWORDS = ("image", "screenshot", "photo", "diagram", "picture", "imagen", "captura", "foto", "diagrama")
_REASONING_KEYWORDS = (
    "why", "explain", "architecture", "trade-off", "tradeoff", "compare",
    "por qué", "porque", "arquitectura", "explica", "diseño", "design",
)
_CHEAP_KEYWORDS = ("quick", "typo", "rename", "small fix", "rápido", "simple", "trivial")

DEFAULT_ROUTING_RULES: dict[str, RoutingRule] = {
    "vision": RoutingRule(providers=("gemini", "claude"), requires="vision"),
    "reasoning": RoutingRule(providers=("claude", "gemini"), requires="reasoning"),
    "cheap": RoutingRule(providers=("qwen-local", "gemini")),
    "coding": RoutingRule(providers=("gemini", "claude")),
}
DEFAULT_CATEGORY = "coding"


def classify(text: str) -> str:
    lowered = text.lower()
    if any(k in lowered for k in _VISION_KEYWORDS):
        return "vision"
    if any(k in lowered for k in _REASONING_KEYWORDS):
        return "reasoning"
    if any(k in lowered for k in _CHEAP_KEYWORDS):
        return "cheap"
    return DEFAULT_CATEGORY


class ModelRouter:
    def __init__(
        self,
        registry: ModelRegistry,
        *,
        default: str | None = None,
        rules: dict[str, RoutingRule] | None = None,
    ) -> None:
        self._registry = registry
        self._manual = default or registry.names()[0]
        self._auto = False
        self._rules = rules if rules is not None else DEFAULT_ROUTING_RULES

    def set_manual(self, name: str) -> None:
        self._registry.get(name)  # raises KeyError if unknown — fail before switching
        self._manual = name
        self._auto = False

    def set_auto(self) -> None:
        self._auto = True

    def is_auto(self) -> bool:
        return self._auto

    def current(self) -> str:
        return "auto" if self._auto else self._manual

    def available(self) -> list[str]:
        return self._registry.names()

    def _capable(self, name: str, requires: str | None) -> bool:
        if requires is None:
            return True
        try:
            provider = self._registry.get(name)
        except KeyError:
            return False
        return bool(getattr(provider.capabilities, requires, False))

    def resolve(self, text: str | None = None) -> str:
        if not self._auto:
            return self._manual

        category = classify(text) if text else DEFAULT_CATEGORY
        rule = self._rules.get(category)
        if rule is not None:
            for name in rule.providers:
                if name in self._registry.names() and self._capable(name, rule.requires):
                    return name
        # No candidate registered/capable for this category — auto-routing
        # degrades to whatever manual would have picked, rather than erroring.
        return self._manual

    def get_provider(self, text: str | None = None) -> ModelProvider:
        return self._registry.get(self.resolve(text))
