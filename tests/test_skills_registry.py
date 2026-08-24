"""SkillRegistry: frontmatter parsing, catalog vs. lazy body loading, and
the override rule (a later root wins over an earlier one for the same
skill name — how project-level skills are meant to shadow user-level ones).
"""

from __future__ import annotations

from pathlib import Path

from david_agent.skills.registry import SkillRegistry


def _make_skill(root: Path, dirname: str, name: str, description: str, body_extra: str = "") -> None:
    skill_dir = root / dirname
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\nFull instructions here.{body_extra}\n"
    )


def test_discover_and_catalog(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    root.mkdir()
    _make_skill(root, "gcp", "gcp-architecture", "Review GCP architectures")
    _make_skill(root, "aws", "aws-security", "Review AWS security posture")

    registry = SkillRegistry()
    registry.discover([root])

    assert registry.count() == 2
    names = [s.name for s in registry.catalog()]
    assert names == ["aws-security", "gcp-architecture"]  # sorted by name


def test_catalog_does_not_include_full_body(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    root.mkdir()
    _make_skill(root, "gcp", "gcp-architecture", "Review GCP architectures", body_extra="SECRET_INSTRUCTION_TEXT")

    registry = SkillRegistry()
    registry.discover([root])

    summary = registry.get("gcp-architecture")
    assert summary is not None
    assert summary.description == "Review GCP architectures"
    # the summary object itself never carries body text — only a path to load it from
    assert not hasattr(summary, "body")


def test_load_body_reads_full_skill_md(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    root.mkdir()
    _make_skill(root, "gcp", "gcp-architecture", "Review GCP architectures", body_extra="SECRET_INSTRUCTION_TEXT")

    registry = SkillRegistry()
    registry.discover([root])

    body = registry.load_body("gcp-architecture")
    assert body is not None
    assert "SECRET_INSTRUCTION_TEXT" in body


def test_load_body_unknown_skill_returns_none() -> None:
    registry = SkillRegistry()
    assert registry.load_body("nonexistent") is None


def test_directory_without_skill_md_is_ignored(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    root.mkdir()
    (root / "not-a-skill").mkdir()

    registry = SkillRegistry()
    registry.discover([root])

    assert registry.count() == 0


def test_skill_md_missing_frontmatter_name_is_ignored(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    root.mkdir()
    skill_dir = root / "broken"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\ndescription: no name field\n---\nBody.\n")

    registry = SkillRegistry()
    registry.discover([root])

    assert registry.count() == 0


def test_later_root_overrides_same_named_skill(tmp_path: Path) -> None:
    user_root = tmp_path / "user_skills"
    user_root.mkdir()
    _make_skill(user_root, "shared", "shared-skill", "user-level version")

    project_root = tmp_path / "project_skills"
    project_root.mkdir()
    _make_skill(project_root, "shared", "shared-skill", "project-level version")

    registry = SkillRegistry()
    registry.discover([user_root, project_root])

    assert registry.count() == 1
    assert registry.get("shared-skill").description == "project-level version"
