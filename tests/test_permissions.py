"""PermissionEngine + policies: the blocklist/sensitive-path checks that
apply in every mode, and the mode-based fallback (safe/ask/auto) otherwise.
"""

from __future__ import annotations

import pytest

from david_agent.permissions.engine import PermissionEngine
from david_agent.permissions.policies import Decision, Mode, normalize_command, path_is_sensitive
from david_agent.tools.base import Tool, ToolResult


class FakeTool(Tool):
    def __init__(self, name: str = "fake.tool", dangerous: bool = False) -> None:
        self.name = name
        self.description = "a fake tool"
        self.dangerous = dangerous

    def execute(self, args: dict) -> ToolResult:
        return ToolResult(output="ok")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a  b", "a b"),
        ("rm  -rf  /", "rm -rf /"),
        ("no extra space", "no extra space"),
        ("\ttrim\tme\t", " trim me "),  # collapses runs, does not strip the ends
    ],
)
def test_normalize_command_collapses_whitespace(raw: str, expected: str) -> None:
    assert normalize_command(raw) == expected


@pytest.mark.parametrize(
    "command",
    ["rm -rf /", "rm -rf ~", "rm -rf *", "rm  -rf  /", ":(){ :|:& };:"],
)
def test_blocked_commands_are_blocked_in_every_mode(command: str) -> None:
    tool = FakeTool(dangerous=False)  # even a "safe" tool must be blocked
    for mode in Mode:
        engine = PermissionEngine(mode=mode)
        assert engine.decide(tool, {"command": command}) is Decision.BLOCK


def test_unlisted_destructive_variants_are_not_caught() -> None:
    # Documented, not a bug: the blocklist is exact-string matching, so this
    # is expected to slip through. The test pins that known limitation so a
    # future "fix" to the matching logic doesn't silently change behavior
    # without someone noticing this test flip.
    engine = PermissionEngine(mode=Mode.AUTO)
    tool = FakeTool()
    assert engine.decide(tool, {"command": "cd / && rm -rf ."}) is not Decision.BLOCK


@pytest.mark.parametrize(
    "path",
    [
        "~/.ssh/id_rsa",
        "~/.aws/credentials",
        "~/.npmrc",
        "./.env",
        "/Users/whoever/.git-credentials",
    ],
)
def test_sensitive_paths_are_detected(path: str) -> None:
    assert path_is_sensitive(path) is True


def test_ordinary_paths_are_not_sensitive() -> None:
    assert path_is_sensitive("README.md") is False
    assert path_is_sensitive("src/david_agent/core/loop.py") is False


def test_sensitive_path_blocked_in_every_mode() -> None:
    tool = FakeTool(dangerous=False)
    for mode in Mode:
        engine = PermissionEngine(mode=mode)
        assert engine.decide(tool, {"path": "~/.ssh/id_rsa"}) is Decision.BLOCK


def test_auto_mode_allows_non_blocked_dangerous_tool() -> None:
    engine = PermissionEngine(mode=Mode.AUTO)
    tool = FakeTool(dangerous=True)
    assert engine.decide(tool, {"command": "ls -la"}) is Decision.ALLOW


def test_ask_mode_asks_even_for_safe_tool() -> None:
    engine = PermissionEngine(mode=Mode.ASK)
    tool = FakeTool(dangerous=False)
    assert engine.decide(tool, {}) is Decision.ASK


def test_safe_mode_allows_safe_tool_but_asks_for_dangerous() -> None:
    engine = PermissionEngine(mode=Mode.SAFE)
    assert engine.decide(FakeTool(dangerous=False), {}) is Decision.ALLOW
    assert engine.decide(FakeTool(dangerous=True), {}) is Decision.ASK
