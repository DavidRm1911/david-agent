"""Permission modes, decisions, and the hardcoded blocklist.

See PermissionEngine (engine.py) for how these apply to an actual tool call.
"""

from __future__ import annotations

from enum import Enum


class Mode(str, Enum):
    ASK = "ask"  # confirm every tool call, even safe ones
    SAFE = "safe"  # default: safe tools run automatically, dangerous ones ask
    AUTO = "auto"  # everything runs automatically except the blocklist


class Decision(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    BLOCK = "block"


# Checked against shell-like args in every mode, including "auto" — matches
# CLAUDE.md §14's own example ("rm -rf → blocked") and is never bypassable.
BLOCKED_COMMAND_PATTERNS = ("rm -rf /", "rm -rf ~", "rm -rf *", ":(){ :|:& };:")
