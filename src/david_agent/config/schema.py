"""Declarative config shape (CLAUDE.md §24).

Every field here already has a real switch somewhere in the codebase —
this is not a config surface for features that don't exist yet. Notably
absent: per-tool permission overrides (`shell: ask`, `git_commit: ask`,
etc., as sketched in the original §24 example) and `local_models.
max_memory_gb` — PermissionEngine only has one global Mode, and nothing
in this project measures or caps Ollama's memory use. Adding those keys
here would make the config lie about what the runtime actually does.

Secrets never belong in this file or in configs/default.yaml: `.env`, the
OS keychain, or a provider's own credential store only (§24, §39).
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields


class ConfigError(Exception):
    pass


ROUTING_MODES = ("manual", "auto")
PERMISSION_MODES = ("safe", "ask", "auto")
MEMORY_BACKENDS = ("sqlite", "none")


@dataclass(frozen=True)
class RoutingConfig:
    mode: str = "manual"


@dataclass(frozen=True)
class PermissionsConfig:
    mode: str = "safe"


@dataclass(frozen=True)
class SandboxConfig:
    enabled: bool = True


@dataclass(frozen=True)
class MemoryConfig:
    backend: str = "sqlite"


@dataclass(frozen=True)
class SkillsConfig:
    auto_discover: bool = True


@dataclass(frozen=True)
class MCPConfig:
    enabled: bool = True


@dataclass(frozen=True)
class LocalModelsConfig:
    enabled: bool = True
    model: str = "qwen3.5:9b"


@dataclass(frozen=True)
class Config:
    default_model: str = "claude"
    routing: RoutingConfig = field(default_factory=RoutingConfig)
    permissions: PermissionsConfig = field(default_factory=PermissionsConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    local_models: LocalModelsConfig = field(default_factory=LocalModelsConfig)

    @classmethod
    def from_dict(cls, data: dict) -> Config:
        known_top = {f.name for f in fields(cls)}
        unknown_top = set(data) - known_top
        if unknown_top:
            raise ConfigError(f"unknown top-level key(s): {', '.join(sorted(unknown_top))}. expected: {', '.join(sorted(known_top))}")

        default_model = data.get("default_model", cls.default_model)
        if not isinstance(default_model, str):
            raise ConfigError(f"'default_model' must be a string, got {type(default_model).__name__}")

        routing = _build_section(data, "routing", RoutingConfig)
        if routing.mode not in ROUTING_MODES:
            raise ConfigError(f"'routing.mode' must be one of {ROUTING_MODES}, got '{routing.mode}'")

        permissions = _build_section(data, "permissions", PermissionsConfig)
        if permissions.mode not in PERMISSION_MODES:
            raise ConfigError(f"'permissions.mode' must be one of {PERMISSION_MODES}, got '{permissions.mode}'")

        memory = _build_section(data, "memory", MemoryConfig)
        if memory.backend not in MEMORY_BACKENDS:
            raise ConfigError(f"'memory.backend' must be one of {MEMORY_BACKENDS}, got '{memory.backend}'")

        return cls(
            default_model=default_model,
            routing=routing,
            permissions=permissions,
            sandbox=_build_section(data, "sandbox", SandboxConfig),
            memory=memory,
            skills=_build_section(data, "skills", SkillsConfig),
            mcp=_build_section(data, "mcp", MCPConfig),
            local_models=_build_section(data, "local_models", LocalModelsConfig),
        )


def _build_section(data: dict, key: str, section_cls: type) -> object:
    raw = data.get(key, {})
    if not isinstance(raw, dict):
        raise ConfigError(f"'{key}' must be a mapping, got {type(raw).__name__}")

    known = {f.name for f in fields(section_cls)}
    unknown = set(raw) - known
    if unknown:
        raise ConfigError(f"unknown key(s) under '{key}': {', '.join(sorted(unknown))}. expected: {', '.join(sorted(known))}")

    try:
        return section_cls(**raw)
    except TypeError as e:
        raise ConfigError(f"invalid value under '{key}': {e}") from e
