"""Discovers configured MCP servers.

Reuses Claude Code's own `mcpServers` config (~/.claude.json) instead of
inventing a proprietary format — same principle as skill discovery in
skills/discovery.py. Only stdio servers (command + args) are supported;
http/sse-based servers are skipped for now.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MCPServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None


def default_servers(config_path: Path | None = None) -> list[MCPServerConfig]:
    config_path = config_path or Path.home() / ".claude.json"
    if not config_path.exists():
        return []
    try:
        data = json.loads(config_path.read_text())
    except (json.JSONDecodeError, OSError):
        return []

    servers = []
    for name, cfg in data.get("mcpServers", {}).items():
        command = cfg.get("command")
        if not command:
            continue  # http/sse server — not supported yet
        servers.append(MCPServerConfig(name=name, command=command, args=cfg.get("args", []), env=cfg.get("env")))
    return servers
