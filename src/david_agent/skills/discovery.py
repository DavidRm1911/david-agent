"""Where skills live. Claude Code's own roots, plus this project's.

Symlinks (e.g. ~/.claude/skills/foo -> ~/.agents/skills/foo, how Claude Code
itself stores most skills) are followed transparently by pathlib — nothing
special needed here.
"""

from __future__ import annotations

from pathlib import Path


def default_roots(project_dir: Path | None = None) -> list[Path]:
    project_dir = project_dir or Path.cwd()
    candidates = [
        Path.home() / ".claude" / "skills",
        project_dir / ".claude" / "skills",
        project_dir / "skills",
    ]
    roots: list[Path] = []
    for c in candidates:
        if c.exists() and c not in roots:
            roots.append(c)
    return roots
