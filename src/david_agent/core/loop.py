"""The Agent Loop.

None of the three providers expose native tool-calling in how we invoke them
(ClaudeCodeProvider disables Claude Code's own tools; AntigravityProvider
and OllamaProvider are plain chat). So both skill-loading and tool-calling
use the same lightweight text protocol: the model answers with a fixed
marker line, the loop parses it, acts, and feeds the result back — bounded
by MAX_ITERATIONS so nothing can loop forever (CLAUDE.md §7).

Every tool call is routed through the Agent's PermissionEngine, which
returns ALLOW / ASK / BLOCK. Only ASK ever touches the `confirm` callback —
BLOCK is final and never prompts, ALLOW never prompts either. `confirm`
itself stays interface-agnostic (the CLI supplies a terminal prompt; a
future Web UI would supply its own), so the loop never does I/O directly.
"""

from __future__ import annotations

import json
import re
from typing import Callable

from david_agent.core.agent import Agent
from david_agent.core.session import Session
from david_agent.models.base import ModelResponse
from david_agent.permissions.policies import Decision

MAX_ITERATIONS = 6  # covers both skill loads and tool calls in a single turn

_LOAD_SKILL_RE = re.compile(r"^LOAD_SKILL:\s*(\S+)\s*$")
_TOOL_CALL_RE = re.compile(r"^TOOL_CALL:\s*(\S+)\s+(\{.*\})\s*$", re.DOTALL)

ConfirmFn = Callable[[str, dict], bool]


def _deny_all(_tool_name: str, _args: dict) -> bool:
    return False


def _build_system_prompt(agent: Agent) -> str:
    prompt = agent.system_prompt

    catalog = agent.skills.catalog()
    if catalog:
        lines = [f"- {s.name}: {s.description}" for s in catalog]
        prompt += (
            "\n\nAvailable skills (only name + description are loaded — not "
            "their full instructions):\n" + "\n".join(lines) + "\n\n"
            "If one is relevant, respond with EXACTLY:\nLOAD_SKILL: <skill-name>\n"
            "and nothing else. You'll receive its full instructions and be asked again."
        )

    tools = agent.tools.catalog()
    if tools:
        lines = [f"- {t.name}: {t.description}" for t in tools]
        prompt += (
            "\n\nAvailable tools:\n" + "\n".join(lines) + "\n\n"
            "To call one, respond with EXACTLY:\nTOOL_CALL: <tool-name> <json-args>\n"
            "e.g. TOOL_CALL: filesystem.read {\"path\": \"README.md\"}\n"
            "and nothing else. You'll receive the result and be asked again."
        )

    return prompt


def _parse_skill_request(text: str) -> str | None:
    match = _LOAD_SKILL_RE.match(text.strip())
    return match.group(1) if match else None


def _parse_tool_call(text: str) -> tuple[str, dict] | None:
    match = _TOOL_CALL_RE.match(text.strip())
    if not match:
        return None
    try:
        args = json.loads(match.group(2))
    except json.JSONDecodeError:
        return None
    return match.group(1), args


def _execute_tool(agent: Agent, name: str, args: dict, confirm: ConfirmFn) -> tuple[str, str | None]:
    """Returns (text shown to the model, error for memory.save_tool_call).
    The two used to be folded into one string, which meant the error column
    in tool_calls was always NULL — even for real failures, so the webui
    dashboard could never distinguish a failed call from a successful one."""
    tool = agent.tools.get(name)
    if tool is None:
        error = f"Unknown tool '{name}'."
        return error, error

    decision = agent.permissions.decide(tool, args)
    if decision is Decision.BLOCK:
        error = f"Blocked by policy: '{name}' matches a disallowed pattern."
        return error, error
    if decision is Decision.ASK and not confirm(name, args):
        error = f"Denied by user: '{name}' was not executed."
        return error, error

    result = tool.execute(args)
    if result.error:
        return f"Error: {result.error}", result.error
    return result.output, None


def run_turn(
    agent: Agent, session: Session, user_input: str, *, confirm: ConfirmFn = _deny_all
) -> ModelResponse:
    session.add_user(user_input)
    agent.memory.save_message(session.id, "user", user_input)

    provider = agent.router.get_provider()
    system = _build_system_prompt(agent)

    for attempt in range(MAX_ITERATIONS):
        response = provider.complete(session.messages, system=system)
        session.add_assistant(response.text)
        agent.memory.save_message(session.id, "assistant", response.text)
        agent.memory.save_model_call(
            session.id, agent.router.resolve(), response.model, response.input_tokens,
            response.output_tokens, response.cost_usd,
        )

        last_attempt = attempt == MAX_ITERATIONS - 1
        skill_name = _parse_skill_request(response.text)
        tool_call = _parse_tool_call(response.text)

        if last_attempt or (skill_name is None and tool_call is None):
            return response

        if skill_name is not None:
            body = agent.skills.load_body(skill_name)
            if body is None:
                session.add_user(f"[system] Unknown skill '{skill_name}'. Answer the original question directly.")
            else:
                session.add_user(
                    f"[system] Full instructions for skill '{skill_name}':\n\n{body}\n\n"
                    "Now answer the original question using these instructions."
                )
        else:
            name, args = tool_call
            result_text, tool_error = _execute_tool(agent, name, args, confirm)
            session.add_user(f"[system] Tool '{name}' result:\n\n{result_text}")
            agent.memory.save_tool_call(session.id, name, args, result_text, tool_error)

    raise AssertionError("unreachable")  # loop always returns within MAX_ITERATIONS attempts
