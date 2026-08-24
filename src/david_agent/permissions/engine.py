"""PermissionEngine — the single place every tool call passes through
before it runs (CLAUDE.md §14). Fase 5 had this ad-hoc: a bare `dangerous`
flag on each tool plus a raw confirm callback in the loop. This formalizes
that into modes and a real blocklist without changing how the loop calls
it — `run_turn` still just needs a decision and, sometimes, a confirmation.
"""

from __future__ import annotations

from dataclasses import dataclass

from david_agent.permissions.policies import BLOCKED_COMMAND_PATTERNS, Decision, Mode
from david_agent.tools.base import Tool


@dataclass
class PermissionEngine:
    mode: Mode = Mode.SAFE

    def decide(self, tool: Tool, args: dict) -> Decision:
        command = args.get("command") if isinstance(args, dict) else None
        if command and any(bad in command for bad in BLOCKED_COMMAND_PATTERNS):
            return Decision.BLOCK

        if self.mode == Mode.AUTO:
            return Decision.ALLOW
        if self.mode == Mode.ASK:
            return Decision.ASK
        # Mode.SAFE
        return Decision.ASK if tool.dangerous else Decision.ALLOW
