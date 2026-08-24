"""Provider-agnostic model interface.

The Agent Loop only ever talks to this interface. It must never import a
concrete provider directly — that dependency runs one way, through the
ModelRegistry.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelCapabilities:
    streaming: bool = False
    tools: bool = False
    vision: bool = False
    structured_output: bool = False
    reasoning: bool = False
    context_window: int | None = None
    max_output_tokens: int | None = None


@dataclass
class ModelMessage:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class ModelResponse:
    text: str
    model: str
    stop_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    raw: dict = field(default_factory=dict)


class ModelProvider(ABC):
    """A pluggable backend. Claude, Gemini, DeepSeek, a local model — same shape."""

    name: str
    capabilities: ModelCapabilities

    @abstractmethod
    def complete(self, messages: list[ModelMessage], *, system: str | None = None) -> ModelResponse:
        """Send messages, get one response back. No streaming in Fase 1."""
        raise NotImplementedError
