"""Tool interface. Native tools and future MCP tools (Fase 7) will both
implement this — the Agent Loop should never need to know which is which.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ToolResult:
    output: str
    error: str | None = None


class Tool(ABC):
    name: str
    description: str
    dangerous: bool = False  # dangerous tools go through confirmation before running

    @abstractmethod
    def execute(self, args: dict) -> ToolResult:
        raise NotImplementedError
