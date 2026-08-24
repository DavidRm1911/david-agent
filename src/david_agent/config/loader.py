"""Declarative config loading (CLAUDE.md §24).

Layers merge in this order, each overriding the previous — the app works
with zero YAML present at all, since every field in Config already has a
default matching current hardcoded behavior:

1. Config() dataclass defaults.
2. ./configs/default.yaml, if the cwd has one (the repo ships one).
3. ~/.david-agent/config.yaml, if present (per-machine override).
4. $DAVID_AGENT_CONFIG, if set — an explicit path.
5. `explicit_path` argument, if given (e.g. a future --config flag).

A path that's explicitly named (env var or argument) and doesn't exist is
an error, not a silent skip — the user pointed at something specific.
./configs/default.yaml and the per-machine override are optional and
silently skipped if absent, since most runs won't have created them.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from david_agent.config.schema import Config, ConfigError

PROJECT_DEFAULT_PATH = Path("configs/default.yaml")
USER_OVERRIDE_PATH = Path.home() / ".david-agent" / "config.yaml"


def _read_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise ConfigError(f"'{path}' is not valid YAML: {e}") from e
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"'{path}' must be a YAML mapping at the top level, got {type(data).__name__}")
    return data


def _merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(explicit_path: Path | None = None) -> Config:
    merged: dict = {}

    for optional_path in (PROJECT_DEFAULT_PATH, USER_OVERRIDE_PATH):
        if optional_path.exists():
            merged = _merge(merged, _read_yaml(optional_path))

    env_value = os.environ.get("DAVID_AGENT_CONFIG")
    if env_value:
        env_path = Path(env_value)
        if not env_path.exists():
            raise ConfigError(f"DAVID_AGENT_CONFIG points to '{env_path}', which does not exist")
        merged = _merge(merged, _read_yaml(env_path))

    if explicit_path is not None:
        if not explicit_path.exists():
            raise ConfigError(f"config file '{explicit_path}' does not exist")
        merged = _merge(merged, _read_yaml(explicit_path))

    return Config.from_dict(merged)
