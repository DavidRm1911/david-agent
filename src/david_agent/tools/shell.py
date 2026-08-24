"""shell.execute — arbitrary shell commands. The single most dangerous tool
in this system: always flagged dangerous (goes through confirmation, see
core/loop.py's confirm callback), plus a hardcoded blocklist for a few
catastrophic patterns as defense in depth ahead of Fase 6's real
PermissionEngine (config-driven modes, full policy).
"""

from __future__ import annotations

import subprocess

from david_agent.tools.base import Tool, ToolResult

_BLOCKED_SUBSTRINGS = ("rm -rf /", "rm -rf ~", "rm -rf *", ":(){ :|:& };:")


class ShellExecuteTool(Tool):
    name = "shell.execute"
    description = 'Run a shell command. Args: {"command": "ls -la"}'
    dangerous = True

    def execute(self, args: dict) -> ToolResult:
        command = args.get("command")
        if not command:
            return ToolResult(output="", error="missing 'command' argument")
        if any(bad in command for bad in _BLOCKED_SUBSTRINGS):
            return ToolResult(output="", error="blocked: command matches a destructive pattern")
        try:
            proc = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            return ToolResult(output="", error="command timed out after 30s")
        if proc.returncode != 0:
            return ToolResult(output=proc.stdout, error=f"exit {proc.returncode}: {proc.stderr.strip()}")
        return ToolResult(output=proc.stdout or "(no output)")
