from __future__ import annotations

import os
import shutil
import sys

from dotenv import load_dotenv

from david_agent.config.loader import load_config
from david_agent.config.schema import Config, ConfigError
from david_agent.core.agent import Agent
from david_agent.core.loop import run_turn
from david_agent.core.session import Session
from david_agent.benchmark.runner import run_benchmark
from david_agent.mcp.adapter import MCPToolAdapter
from david_agent.mcp.client import MCPClient
from david_agent.mcp.registry import default_servers
from david_agent.memory.base import MemoryStore, NullMemoryStore
from david_agent.memory.sqlite import SQLiteMemoryStore
from david_agent.models.registry import ModelRegistry
from david_agent.models.router import ModelRouter
from david_agent.permissions.engine import PermissionEngine
from david_agent.permissions.policies import Mode
from david_agent.providers.anthropic.provider import ClaudeCodeProvider
from david_agent.providers.google.provider import AntigravityProvider
from david_agent.providers.local.provider import OllamaProvider
from david_agent.providers.openai_compatible.provider import OpenAICompatibleProvider
from david_agent.skills.discovery import default_roots
from david_agent.skills.registry import SkillRegistry
from david_agent.tools.filesystem import FileSystemListTool, FileSystemReadTool, FileSystemWriteTool
from david_agent.tools.git import GitDiffTool, GitLogTool, GitStatusTool
from david_agent.tools.registry import ToolRegistry
from david_agent.tools.sandbox import SandboxExecuteTool
from david_agent.tools.shell import ShellExecuteTool

BANNER = """\
╭──────────────────────────────────────────╮
│        DAVID AGENT HARNESS                │
│                                            │
│ Model:   {model:<34}│
│ Routing: {routing:<34}│
│ Skills:  {skills:<34}│
│ Tools:   {tools:<34}│
│ Mode:    {mode:<34}│
│ MCP:     {mcp:<34}│
│ Sandbox: {sandbox:<34}│
╰──────────────────────────────────────────╯
"""


# name -> (base_url, default_model, api-key env var, model-override env var)
_OPENAI_COMPATIBLE_PRESETS = {
    "deepseek": ("https://api.deepseek.com", "deepseek-chat", "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL"),
    "openrouter": ("https://openrouter.ai/api/v1", "openrouter/auto", "OPENROUTER_API_KEY", "OPENROUTER_MODEL"),
}


def build_openai_compatible_providers() -> list[OpenAICompatibleProvider]:
    """Every one of these needs a real, paid API key — never registered
    unless the corresponding env var is already set (CLAUDE.md §39: never
    pay for an API just because it exists). A generic OPENAI_COMPATIBLE_*
    trio covers "other compatible APIs / local gateways" outside the presets.
    """
    providers: list[OpenAICompatibleProvider] = []
    for name, (base_url, default_model, key_var, model_var) in _OPENAI_COMPATIBLE_PRESETS.items():
        api_key = os.environ.get(key_var)
        if api_key:
            model = os.environ.get(model_var, default_model)
            providers.append(OpenAICompatibleProvider(name=name, base_url=base_url, api_key=api_key, model=model))

    generic_key = os.environ.get("OPENAI_COMPATIBLE_API_KEY")
    base_url = os.environ.get("OPENAI_COMPATIBLE_BASE_URL")
    model = os.environ.get("OPENAI_COMPATIBLE_MODEL")
    if generic_key and base_url and model:
        providers.append(
            OpenAICompatibleProvider(
                name=os.environ.get("OPENAI_COMPATIBLE_NAME", "openai-compatible"),
                base_url=base_url,
                api_key=generic_key,
                model=model,
            )
        )
    elif generic_key:
        print("[warn] OPENAI_COMPATIBLE_API_KEY set but BASE_URL/MODEL missing — skipping", file=sys.stderr)

    return providers


def build_registry(config: Config) -> ModelRegistry:
    registry = ModelRegistry()
    registry.register(ClaudeCodeProvider(), default=True)
    try:
        registry.register(AntigravityProvider())
    except RuntimeError as e:
        print(f"[warn] gemini provider unavailable: {e}", file=sys.stderr)
    # OllamaProvider's __init__ never starts/health-checks the server, so
    # registering it is always cheap — the local model stays off until the
    # first turn actually asks for it. local_models.enabled skips even that
    # cheap registration, e.g. on a machine that will never have Ollama.
    if config.local_models.enabled:
        registry.register(OllamaProvider(model=config.local_models.model))
    for provider in build_openai_compatible_providers():
        registry.register(provider)
    return registry


def build_skill_registry(config: Config) -> SkillRegistry:
    skills = SkillRegistry()
    if config.skills.auto_discover:
        skills.discover(default_roots())
    return skills


def build_tool_registry(config: Config) -> ToolRegistry:
    tools = ToolRegistry()
    for tool_cls in (
        FileSystemReadTool,
        FileSystemListTool,
        FileSystemWriteTool,
        ShellExecuteTool,
        GitStatusTool,
        GitDiffTool,
        GitLogTool,
    ):
        tools.register(tool_cls())
    if config.sandbox.enabled:
        tools.register(SandboxExecuteTool())
    return tools


def build_memory_store(config: Config) -> MemoryStore:
    if config.memory.backend == "none":
        return NullMemoryStore()
    return SQLiteMemoryStore()  # "sqlite" — the only other valid value, enforced by Config.from_dict


def build_mcp_tools() -> tuple[list[MCPToolAdapter], int]:
    """Best-effort per server, same pattern as build_registry(): a slow or
    broken MCP server (e.g. a docker gateway still pulling images) prints a
    warning and gets skipped rather than blocking startup for everything
    else. Discovery runs synchronously and sequentially here — fine for the
    two servers this was tested against, a known limit for many more.
    """
    tools: list[MCPToolAdapter] = []
    servers = default_servers()
    connected = 0
    for server in servers:
        client = MCPClient(server, timeout=15.0)
        try:
            mcp_tools = client.list_tools()
        except Exception as e:  # noqa: BLE001 — any server can fail in any way; never block startup
            print(f"[warn] MCP server '{server.name}' unavailable: {e}", file=sys.stderr)
            continue
        connected += 1
        for t in mcp_tools:
            tools.append(MCPToolAdapter(client, server.name, t.name, t.description or ""))
    return tools, connected


def cli_confirm(tool_name: str, args: dict) -> bool:
    print(f"\n[permission] agent wants to run '{tool_name}' with args: {args}")
    answer = input("Allow? [y/N] ").strip().lower()
    return answer == "y"


def handle_command(
    raw: str,
    router: ModelRouter,
    skills: SkillRegistry,
    tools: ToolRegistry,
    permissions: PermissionEngine,
    memory: SQLiteMemoryStore,
    registry: ModelRegistry,
) -> bool:
    """Returns True if `raw` was a slash command (handled here, no model call)."""
    if not raw.startswith("/"):
        return False

    parts = raw.split()
    cmd = parts[0]

    if cmd == "/model":
        if len(parts) == 1:
            print(f"current: {router.current()}")
            print(f"available: {', '.join(router.available())}")
        else:
            try:
                router.set_manual(parts[1])
                print(f"switched to: {router.current()}")
            except KeyError as e:
                print(f"[error] {e}")
        return True

    if cmd == "/route":
        if len(parts) == 1:
            print(f"current: {'auto' if router.is_auto() else 'manual'} ({router.current()})")
            print("usage: /route auto | /route manual <model>")
        elif parts[1] == "auto":
            router.set_auto()
            print("switched to: auto (rule-based, per-turn — see CLAUDE.md §6)")
        elif parts[1] == "manual":
            if len(parts) < 3:
                print(f"[error] usage: /route manual <model>. available: {', '.join(router.available())}")
            else:
                try:
                    router.set_manual(parts[2])
                    print(f"switched to: manual ({router.current()})")
                except KeyError as e:
                    print(f"[error] {e}")
        else:
            print(f"[error] unknown mode '{parts[1]}'. usage: /route auto | /route manual <model>")
        return True

    if cmd == "/skills":
        for s in skills.catalog():
            desc = (s.description[:80] + "…") if len(s.description) > 80 else s.description
            print(f"  {s.name:<28} {desc}")
        print(f"({skills.count()} skills discovered)")
        return True

    if cmd == "/tools":
        for t in tools.catalog():
            flag = " [dangerous]" if t.dangerous else ""
            print(f"  {t.name:<20} {t.description}{flag}")
        return True

    if cmd == "/mode":
        if len(parts) == 1:
            print(f"current: {permissions.mode.value}")
            print(f"available: {', '.join(m.value for m in Mode)}")
        else:
            try:
                permissions.mode = Mode(parts[1])
                print(f"switched to: {permissions.mode.value}")
            except ValueError:
                print(f"[error] unknown mode '{parts[1]}'. Available: {', '.join(m.value for m in Mode)}")
        return True

    if cmd == "/sessions":
        for s in memory.list_sessions():
            print(f"  {s.id}  {s.agent_name:<10} {s.created_at}")
        return True

    if cmd == "/benchmark":
        prompt = raw[len("/benchmark "):].strip()
        if not prompt:
            print("[error] usage: /benchmark <prompt>")
            return True
        print(f"Running against: {', '.join(registry.names())}\n")
        results = run_benchmark(registry, prompt)
        print(f"{'model':<14} {'latency':>8}  {'in/out tok':>12}  {'cost':>10}  status")
        for r in results:
            if r.error:
                print(f"{r.model_name:<14} {r.latency_s:>7.1f}s  {'—':>12}  {'—':>10}  ERROR: {r.error[:60]}")
            else:
                tok = f"{r.input_tokens or '?'}/{r.output_tokens or '?'}"
                cost = f"${r.cost_usd:.4f}" if r.cost_usd is not None else "n/a"
                print(f"{r.model_name:<14} {r.latency_s:>7.1f}s  {tok:>12}  {cost:>10}  ok")
        return True

    print(f"[error] unknown command: {cmd}")
    return True


def main() -> None:
    load_dotenv()  # opt-in providers (openai_compatible) read their keys from here — never committed

    try:
        config = load_config()
    except ConfigError as e:
        print(f"[error] config: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        registry = build_registry(config)
    except RuntimeError as e:
        print(f"Failed to start: {e}", file=sys.stderr)
        sys.exit(1)

    skills = build_skill_registry(config)
    tools = build_tool_registry(config)
    native_tool_count = len(tools.catalog())
    if config.mcp.enabled:
        mcp_tools, mcp_connected = build_mcp_tools()
    else:
        mcp_tools, mcp_connected = [], 0
    for t in mcp_tools:
        tools.register(t)
    permissions = PermissionEngine(mode=Mode(config.permissions.mode))
    memory = build_memory_store(config)

    # config.default_model is user-editable text — unlike the old hardcoded
    # "claude" literal (always safely registered, see ClaudeCodeProvider),
    # it can name a provider that never actually registered (e.g. its CLI
    # isn't logged in). Same best-effort fallback build_registry() already
    # uses for individual providers, applied here to the router's starting pick.
    default_model = config.default_model
    if default_model not in registry.names():
        fallback = registry.names()[0]
        print(f"[warn] configured default_model '{default_model}' is not registered — using '{fallback}'", file=sys.stderr)
        default_model = fallback
    router = ModelRouter(registry, default=default_model)
    if config.routing.mode == "auto":
        router.set_auto()

    agent = Agent(name="default", router=router, skills=skills, tools=tools, permissions=permissions, memory=memory)
    session = Session()
    memory.create_session(session.id, agent.name)

    print(
        BANNER.format(
            model=router.current(),
            routing="auto (rule-based)" if router.is_auto() else "manual",
            skills=f"{skills.count()} discovered",
            tools=f"{native_tool_count} native + {len(mcp_tools)} MCP",
            mode=permissions.mode.value,
            mcp=f"{mcp_connected} server(s) connected",
            sandbox="Docker (lazy, sandbox.execute)" if shutil.which("docker") else "unavailable (docker not found)",
        )
    )
    memory_location = memory.db_path if isinstance(memory, SQLiteMemoryStore) else "nowhere (memory.backend: none)"
    print(f"session: {session.id}  (persisted to {memory_location})")
    print(
        "Commands: /model [name], /route [auto|manual <name>], /skills, /tools, "
        "/mode [name], /sessions, /benchmark <prompt>, exit, quit\n"
    )

    while True:
        try:
            user_input = input("agent> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input in ("exit", "quit"):
            break
        if handle_command(user_input, router, skills, tools, permissions, memory, registry):
            continue

        try:
            response = run_turn(agent, session, user_input, confirm=cli_confirm)
        except RuntimeError as e:
            print(f"[error] {e}\n")
            continue

        print(f"\n{response.text}\n")


if __name__ == "__main__":
    main()
