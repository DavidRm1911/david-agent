"""Config schema + loader: defaults with zero YAML, merge order across
layers, and that bad input (unknown keys, invalid enum values, missing
explicit paths) fails loudly instead of silently doing the wrong thing."""

from __future__ import annotations

from pathlib import Path

import pytest

from david_agent.config.loader import load_config
from david_agent.config.schema import Config, ConfigError


def test_defaults_with_empty_dict() -> None:
    config = Config.from_dict({})
    assert config.default_model == "claude"
    assert config.routing.mode == "manual"
    assert config.permissions.mode == "safe"
    assert config.sandbox.enabled is True
    assert config.memory.backend == "sqlite"
    assert config.skills.auto_discover is True
    assert config.mcp.enabled is True
    assert config.local_models.enabled is True
    assert config.local_models.model == "qwen3.5:9b"


def test_overrides_apply_and_unspecified_fields_keep_their_default() -> None:
    config = Config.from_dict({"default_model": "gemini", "routing": {"mode": "auto"}})
    assert config.default_model == "gemini"
    assert config.routing.mode == "auto"
    assert config.permissions.mode == "safe"  # untouched section keeps its default


def test_unknown_top_level_key_raises() -> None:
    with pytest.raises(ConfigError, match="unknown top-level key"):
        Config.from_dict({"totally_made_up": True})


def test_unknown_key_under_a_section_raises() -> None:
    with pytest.raises(ConfigError, match="unknown key"):
        Config.from_dict({"permissions": {"shell": "ask"}})  # not a real PermissionsConfig field


def test_invalid_routing_mode_raises() -> None:
    with pytest.raises(ConfigError, match="routing.mode"):
        Config.from_dict({"routing": {"mode": "sometimes"}})


def test_invalid_permissions_mode_raises() -> None:
    with pytest.raises(ConfigError, match="permissions.mode"):
        Config.from_dict({"permissions": {"mode": "yolo"}})


def test_invalid_memory_backend_raises() -> None:
    with pytest.raises(ConfigError, match="memory.backend"):
        Config.from_dict({"memory": {"backend": "postgres"}})


def test_non_mapping_section_raises() -> None:
    with pytest.raises(ConfigError, match="must be a mapping"):
        Config.from_dict({"sandbox": "enabled"})


def test_load_config_with_no_files_present_returns_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)  # no ./configs/default.yaml here
    monkeypatch.delenv("DAVID_AGENT_CONFIG", raising=False)
    monkeypatch.setattr("david_agent.config.loader.USER_OVERRIDE_PATH", tmp_path / "nonexistent" / "config.yaml")

    config = load_config()
    assert config == Config()


def test_load_config_reads_project_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DAVID_AGENT_CONFIG", raising=False)
    monkeypatch.setattr("david_agent.config.loader.USER_OVERRIDE_PATH", tmp_path / "nonexistent" / "config.yaml")
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "default.yaml").write_text("default_model: gemini\n")

    config = load_config()
    assert config.default_model == "gemini"


def test_explicit_path_overrides_project_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DAVID_AGENT_CONFIG", raising=False)
    monkeypatch.setattr("david_agent.config.loader.USER_OVERRIDE_PATH", tmp_path / "nonexistent" / "config.yaml")
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "default.yaml").write_text("default_model: gemini\n")
    explicit = tmp_path / "explicit.yaml"
    explicit.write_text("default_model: qwen-local\n")

    config = load_config(explicit_path=explicit)
    assert config.default_model == "qwen-local"


def test_missing_explicit_path_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DAVID_AGENT_CONFIG", raising=False)
    monkeypatch.setattr("david_agent.config.loader.USER_OVERRIDE_PATH", tmp_path / "nonexistent" / "config.yaml")

    with pytest.raises(ConfigError, match="does not exist"):
        load_config(explicit_path=tmp_path / "nope.yaml")


def test_missing_env_path_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("david_agent.config.loader.USER_OVERRIDE_PATH", tmp_path / "nonexistent" / "config.yaml")
    monkeypatch.setenv("DAVID_AGENT_CONFIG", str(tmp_path / "nope.yaml"))

    with pytest.raises(ConfigError, match="DAVID_AGENT_CONFIG"):
        load_config()


def test_malformed_yaml_raises_config_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DAVID_AGENT_CONFIG", raising=False)
    monkeypatch.setattr("david_agent.config.loader.USER_OVERRIDE_PATH", tmp_path / "nonexistent" / "config.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("default_model: [unclosed\n")

    with pytest.raises(ConfigError, match="not valid YAML"):
        load_config(explicit_path=bad)


def test_the_shipped_configs_default_yaml_is_valid() -> None:
    # Pins that configs/default.yaml (the file users are actually meant to
    # edit) parses and validates — a regression here means the repo's own
    # example config is broken, not just some test fixture.
    repo_root = Path(__file__).resolve().parent.parent
    config = load_config(explicit_path=repo_root / "configs" / "default.yaml")
    assert config == Config()  # ships with every value equal to the hardcoded defaults, by design
