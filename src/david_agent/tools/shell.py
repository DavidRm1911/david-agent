"""shell.execute — arbitrary shell commands. The single most dangerous tool
in this system: always flagged dangerous (goes through confirmation, see
core/loop.py's confirm callback).

The blocklist below catches exact-string matches of a few catastrophic
patterns after whitespace normalization — it is NOT a general defense
against destructive commands, and never claim otherwise in docs: it doesn't
catch `x=/; rm -rf $x`, `cd / && rm -rf .`, different flag spellings, or any
destructive command outside these specific patterns. In `safe`/`ask` mode
the real protection is the human approving each call; in `auto` mode this
blocklist is the *only* thing standing between the model and the shell —
know that before relying on `auto` with this tool enabled.
"""

from __future__ import annotations

import subprocess

from david_agent.permissions.policies import BLOCKED_COMMAND_PATTERNS, normalize_command
from david_agent.tools.base import Tool, ToolResult


class ShellExecuteTool(Tool):
    name = "shell.execute"
    description = 'Run a shell command. Args: {"command": "ls -la"}'
    dangerous = True

    def execute(self, args: dict) -> ToolResult:
        command = args.get("command")
        if not command:
            return ToolResult(output="", error="missing 'command' argument")
        # Same check PermissionEngine already applies before this tool is
        # ever called — repeated here as a backstop in case something calls
        # execute() directly, bypassing the engine. See policies.py for what
        # this blocklist actually does and doesn't catch.
        if any(bad in normalize_command(command) for bad in BLOCKED_COMMAND_PATTERNS):
            return ToolResult(output="", error="blocked: command matches a destructive pattern")
        try:
            proc = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            return ToolResult(output="", error="command timed out after 30s")
        if proc.returncode != 0:
            return ToolResult(output=proc.stdout, error=f"exit {proc.returncode}: {proc.stderr.strip()}")
        return ToolResult(output=proc.stdout or "(no output)")
