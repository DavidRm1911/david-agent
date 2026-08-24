"""Permission modes, decisions, and the hardcoded blocklist.

See PermissionEngine (engine.py) for how these apply to an actual tool call.
"""

from __future__ import annotations

import re
from enum import Enum


class Mode(str, Enum):
    ASK = "ask"  # confirm every tool call, even safe ones
    SAFE = "safe"  # default: safe tools run automatically, dangerous ones ask
    AUTO = "auto"  # everything runs automatically except the blocklist


class Decision(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    BLOCK = "block"


# Checked against shell-like args in every mode, including "auto", after
# whitespace normalization (normalize_command below) — but this is exact
# matching on 4 literal patterns, not a general defense against destructive
# commands. It does NOT catch `x=/; rm -rf $x`, `cd / && rm -rf .`,
# different flags, or anything outside these specific strings. In `safe`/
# `ask` mode the real protection is the human approving each dangerous
# call; in `auto` mode this blocklist is the *only* thing standing between
# the model and the shell for shell.execute — do not oversell it as more
# than that in docs.
BLOCKED_COMMAND_PATTERNS = ("rm -rf /", "rm -rf ~", "rm -rf *", ":(){ :|:& };:")


def normalize_command(command: str) -> str:
    """Collapse whitespace runs to one space so `rm  -rf  /` still matches
    the same pattern as `rm -rf /` — a cheap partial mitigation, not a fix
    for the deeper bypasses documented above."""
    return re.sub(r"\s+", " ", command)
