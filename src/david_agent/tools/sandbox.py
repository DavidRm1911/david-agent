"""sandbox.execute — same shape as shell.execute, but runs inside an
isolated Docker container instead of directly on the host (Fase 9). Marked
not-dangerous: the isolation itself (no network, only `workspace` mounted)
is the safety property that lets this skip the confirmation shell.execute
needs — a concrete, visible payoff for building the sandbox at all.
"""

from __future__ import annotations

from pathlib import Path

from david_agent.sandbox.docker import DockerSandbox
from david_agent.tools.base import Tool, ToolResult


class SandboxExecuteTool(Tool):
    name = "sandbox.execute"
    description = (
        'Run a shell command inside an isolated Docker container (no network, '
        'only the workspace directory visible). Args: {"command": "python script.py"}'
    )
    dangerous = False

    def __init__(self, sandbox: DockerSandbox | None = None, workspace: Path | None = None) -> None:
        self._sandbox = sandbox or DockerSandbox()
        self._workspace = workspace or Path.cwd()

    def execute(self, args: dict) -> ToolResult:
        command = args.get("command")
        if not command:
            return ToolResult(output="", error="missing 'command' argument")
        return self._sandbox.run(command, workspace=self._workspace)
