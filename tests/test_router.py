"""ModelRouter: manual selection, auto-routing classification, and the
capability-aware fallback that keeps auto-routing from picking a provider
that can't actually do what the category needs."""

from __future__ import annotations

import pytest

from david_agent.models.base import ModelCapabilities, ModelMessage, ModelProvider, ModelResponse
from david_agent.models.registry import ModelRegistry
from david_agent.models.router import ModelRouter, classify


class FakeProvider(ModelProvider):
    def __init__(self, name: str, **caps) -> None:
        self.name = name
        self.capabilities = ModelCapabilities(**caps)

    def complete(self, messages: list[ModelMessage], *, system: str | None = None) -> ModelResponse:
        return ModelResponse(text="ok", model=self.name)


def _registry(*providers: FakeProvider) -> ModelRegistry:
    registry = ModelRegistry()
    for i, p in enumerate(providers):
        registry.register(p, default=(i == 0))
    return registry


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("please look at this screenshot", "vision"),
        ("what's in this diagram", "vision"),
        ("checa esta imagen", "vision"),
        ("why did we pick this architecture", "reasoning"),
        ("explica la arquitectura", "reasoning"),
        ("quick typo fix", "cheap"),
        ("arregla este typo rápido", "cheap"),
        ("implement a REST endpoint", "coding"),
        ("", "coding"),
    ],
)
def test_classify(text: str, expected: str) -> None:
    assert classify(text) == expected


def test_manual_mode_ignores_text_and_capabilities() -> None:
    registry = _registry(FakeProvider("claude", reasoning=True), FakeProvider("gemini", vision=True))
    router = ModelRouter(registry, default="claude")

    assert router.resolve("please look at this screenshot") == "claude"
    assert not router.is_auto()


def test_set_manual_switches_back_out_of_auto() -> None:
    registry = _registry(FakeProvider("claude", reasoning=True))
    router = ModelRouter(registry, default="claude")
    router.set_auto()
    assert router.is_auto()

    router.set_manual("claude")
    assert not router.is_auto()


def test_set_manual_rejects_unknown_provider() -> None:
    registry = _registry(FakeProvider("claude"))
    router = ModelRouter(registry, default="claude")
    with pytest.raises(KeyError):
        router.set_manual("nonexistent")


def test_auto_routes_vision_to_capable_provider() -> None:
    registry = _registry(FakeProvider("claude", reasoning=True), FakeProvider("gemini", vision=True))
    router = ModelRouter(registry, default="claude")
    router.set_auto()

    assert router.resolve("please look at this screenshot") == "gemini"


def test_auto_falls_back_to_manual_when_no_provider_has_the_capability() -> None:
    # Neither registered provider declares vision — auto-routing must not
    # invent a match, and must not raise; it degrades to the manual pick.
    registry = _registry(FakeProvider("claude", reasoning=True), FakeProvider("qwen-local"))
    router = ModelRouter(registry, default="claude")
    router.set_auto()

    assert router.resolve("check this screenshot") == "claude"


def test_auto_skips_first_choice_when_not_registered() -> None:
    # Rule for "vision" prefers gemini first, but only claude is registered
    # and claude has vision=True here — the router should still find it.
    registry = _registry(FakeProvider("claude", vision=True))
    router = ModelRouter(registry, default="claude")
    router.set_auto()

    assert router.resolve("look at this photo") == "claude"


def test_auto_with_no_text_uses_default_category() -> None:
    registry = _registry(FakeProvider("claude", reasoning=True), FakeProvider("gemini"))
    router = ModelRouter(registry, default="claude")
    router.set_auto()

    # DEFAULT_CATEGORY is "coding", whose rule prefers gemini/claude with no
    # capability requirement — first registered candidate wins.
    assert router.resolve(None) == "gemini"


def test_get_provider_returns_the_resolved_providers_object() -> None:
    claude = FakeProvider("claude", reasoning=True)
    gemini = FakeProvider("gemini", vision=True)
    registry = _registry(claude, gemini)
    router = ModelRouter(registry, default="claude")
    router.set_auto()

    assert router.get_provider("look at this image") is gemini
