"""Filesystem tools — read/write/list against the real filesystem the
process can see. No sandbox yet (Fase 9 adds Docker). Write is flagged
dangerous; read and list are not — but all three still refuse known
credential paths (see SENSITIVE_PATH_PATTERNS in permissions/policies.py),
checked here as a backstop in case something calls execute() directly,
bypassing PermissionEngine, which already applies the same check first.
"""

from __future__ import annotations

from pathlib import Path

from david_agent.permissions.policies import path_is_sensitive
from david_agent.tools.base import Tool, ToolResult

MAX_READ_BYTES = 200_000


class FileSystemReadTool(Tool):
    name = "filesystem.read"
    description = 'Read a text file. Args: {"path": "relative/or/absolute/path"}'
    dangerous = False

    def execute(self, args: dict) -> ToolResult:
        path = args.get("path")
        if not path:
            return ToolResult(output="", error="missing 'path' argument")
        if path_is_sensitive(path):
            return ToolResult(output="", error=f"blocked: '{path}' matches a credential path pattern")
        p = Path(path).expanduser()
        if not p.exists():
            return ToolResult(output="", error=f"'{path}' does not exist")
        if not p.is_file():
            return ToolResult(output="", error=f"'{path}' is not a file")
        data = p.read_bytes()[:MAX_READ_BYTES]
        return ToolResult(output=data.decode(errors="replace"))


class FileSystemListTool(Tool):
    name = "filesystem.list"
    description = 'List a directory. Args: {"path": "."}'
    dangerous = False

    def execute(self, args: dict) -> ToolResult:
        path = args.get("path", ".")
        if path_is_sensitive(path):
            return ToolResult(output="", error=f"blocked: '{path}' matches a credential path pattern")
        p = Path(path).expanduser()
        if not p.exists() or not p.is_dir():
            return ToolResult(output="", error=f"'{path}' is not a directory")
        entries = sorted(e.name + ("/" if e.is_dir() else "") for e in p.iterdir())
        return ToolResult(output="\n".join(entries) or "(empty)")


class FileSystemWriteTool(Tool):
    name = "filesystem.write"
    description = 'Write (overwrite) a text file. Args: {"path": "...", "content": "..."}'
    dangerous = True

    def execute(self, args: dict) -> ToolResult:
        path = args.get("path")
        content = args.get("content")
        if not path or content is None:
            return ToolResult(output="", error="requires 'path' and 'content' arguments")
        if path_is_sensitive(path):
            return ToolResult(output="", error=f"blocked: '{path}' matches a credential path pattern")
        p = Path(path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return ToolResult(output=f"wrote {len(content)} bytes to {p}")
