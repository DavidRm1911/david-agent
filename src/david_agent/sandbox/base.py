"""Sandbox interface — code execution isolated from the host, scoped to a
workspace directory. Docker (docker.py) is Fase 9's implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from david_agent.tools.base import ToolResult


class Sandbox(ABC):
    @abstractmethod
    def run(self, command: str, *, workspace: Path) -> ToolResult:
        raise NotImplementedError
