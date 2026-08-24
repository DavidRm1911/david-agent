"""Read-only git tools — status/diff/log. None are dangerous; none write."""

from __future__ import annotations

import subprocess

from david_agent.tools.base import Tool, ToolResult


def _run_git(*args: str) -> ToolResult:
    try:
        proc = subprocess.run(["git", *args], capture_output=True, text=True, timeout=15)
    except FileNotFoundError:
        return ToolResult(output="", error="git is not installed")
    except subprocess.TimeoutExpired:
        return ToolResult(output="", error="git command timed out")
    if proc.returncode != 0:
        return ToolResult(output="", error=proc.stderr.strip() or f"git exited {proc.returncode}")
    return ToolResult(output=proc.stdout or "(no output)")


class GitStatusTool(Tool):
    name = "git.status"
    description = "Show git working tree status. Args: {}"
    dangerous = False

    def execute(self, args: dict) -> ToolResult:
        return _run_git("status")


class GitDiffTool(Tool):
    name = "git.diff"
    description = "Show unstaged git diff. Args: {}"
    dangerous = False

    def execute(self, args: dict) -> ToolResult:
        return _run_git("diff")


class GitLogTool(Tool):
    name = "git.log"
    description = 'Show recent git log. Args: {"n": 10}'
    dangerous = False

    def execute(self, args: dict) -> ToolResult:
        n = str(args.get("n", 10))
        return _run_git("log", f"-{n}", "--oneline")
