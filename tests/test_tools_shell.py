"""shell.execute: the blocklist backstop (same patterns PermissionEngine
already checks before this tool is ever reached) and basic execution."""

from __future__ import annotations

import pytest

from david_agent.tools.shell import ShellExecuteTool


@pytest.mark.parametrize("command", ["rm -rf /", "rm -rf ~", "rm -rf *", "rm  -rf  /", ":(){ :|:& };:"])
def test_blocked_patterns_are_rejected(command: str) -> None:
    result = ShellExecuteTool().execute({"command": command})
    assert result.error is not None
    assert "blocked" in result.error


def test_missing_command_argument() -> None:
    result = ShellExecuteTool().execute({})
    assert result.error is not None


def test_successful_command_returns_stdout() -> None:
    result = ShellExecuteTool().execute({"command": "echo hello"})
    assert result.error is None
    assert result.output.strip() == "hello"


def test_nonzero_exit_is_reported_as_error() -> None:
    result = ShellExecuteTool().execute({"command": "exit 3"})
    assert result.error is not None
    assert "exit 3" in result.error


def test_shell_execute_is_always_dangerous() -> None:
    assert ShellExecuteTool().dangerous is True
