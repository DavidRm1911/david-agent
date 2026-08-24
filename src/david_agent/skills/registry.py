"""Lightweight skill catalog — name + description only.

Fase 3 discovers and catalogs. It deliberately does not read past the
frontmatter: loading full SKILL.md bodies (instructions, resources, scripts)
into context for every skill on startup is exactly what Fase 4's lazy
loading exists to avoid. A 40-skill install should cost a few KB at boot,
not 40 full instruction sets.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class SkillSummary:
    name: str
    description: str
    path: Path  # directory containing SKILL.md — full body loads from here later
    source: Path  # which root this was discovered under


def _extract_frontmatter(text: str) -> dict | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    try:
        data = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, SkillSummary] = {}

    def discover(self, roots: list[Path]) -> None:
        for root in roots:
            for entry in sorted(p for p in root.iterdir() if p.is_dir()):
                skill_md = entry / "SKILL.md"
                if not skill_md.exists():
                    continue
                frontmatter = _extract_frontmatter(skill_md.read_text(errors="replace"))
                if not frontmatter or "name" not in frontmatter:
                    continue
                # a project root discovered later overrides a same-named skill
                # from an earlier (e.g. user-level) root
                self._skills[frontmatter["name"]] = SkillSummary(
                    name=frontmatter["name"],
                    description=frontmatter.get("description", ""),
                    path=entry,
                    source=root,
                )

    def catalog(self) -> list[SkillSummary]:
        return sorted(self._skills.values(), key=lambda s: s.name)

    def count(self) -> int:
        return len(self._skills)

    def get(self, name: str) -> SkillSummary | None:
        return self._skills.get(name)

    def load_body(self, name: str) -> str | None:
        """Read a skill's full SKILL.md — the expensive load Fase 4 defers until asked for."""
        summary = self._skills.get(name)
        if summary is None:
            return None
        return (summary.path / "SKILL.md").read_text(errors="replace")
