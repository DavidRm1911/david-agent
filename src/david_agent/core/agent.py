"""An Agent is a configuration, not a runtime. See core/loop.py for execution."""

from __future__ import annotations

from dataclasses import dataclass, field

from david_agent.memory.base import MemoryStore, NullMemoryStore
from david_agent.models.router import ModelRouter
from david_agent.permissions.engine import PermissionEngine
from david_agent.skills.registry import SkillRegistry
from david_agent.tools.registry import ToolRegistry

DEFAULT_SYSTEM_PROMPT = (
    "You are David's agent, running inside david-agent — a model-agnostic "
    "agent runtime. Answer directly and concisely."
)


@dataclass
class Agent:
    name: str
    router: ModelRouter
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    skills: SkillRegistry = field(default_factory=SkillRegistry)
    tools: ToolRegistry = field(default_factory=ToolRegistry)
    permissions: PermissionEngine = field(default_factory=PermissionEngine)
    memory: MemoryStore = field(default_factory=NullMemoryStore)
