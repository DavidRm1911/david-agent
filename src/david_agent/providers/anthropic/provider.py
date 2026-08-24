"""ClaudeCodeProvider: talks to Claude by shelling out to the `claude` CLI.

This reuses the existing Claude Code login (OAuth session) through the real,
sanctioned client binary in headless mode (`claude -p`) — no credential file
is read or extracted, and no separate ANTHROPIC_API_KEY is required. If a
direct Anthropic API key is ever wanted instead, that becomes a second,
separate provider — never a silent fallback here.

`--tools ''` only disables Claude Code's own built-in tools — it does NOT
stop the subprocess from loading MCP servers configured in the ambient
~/.claude.json (found by testing: a nested call was answering with the
*outer* session's real MCP/tool list instead of following our own
TOOL_CALL protocol). `--strict-mcp-config` with no --mcp-config fully
isolates the subprocess, so this provider is a clean, capability-free text
completion regardless of what's configured globally.
"""

from __future__ import annotations

import json
import shutil
import subprocess

from david_agent.models.base import ModelCapabilities, ModelMessage, ModelProvider, ModelResponse


class ClaudeCodeProvider(ModelProvider):
    name = "claude"
    capabilities = ModelCapabilities(
        streaming=False,
        tools=True,
        vision=True,
        structured_output=False,
        reasoning=True,
        context_window=1_000_000,
        max_output_tokens=64_000,
    )

    def __init__(
        self,
        *,
        model: str | None = None,
        effort: str | None = None,
        binary: str | None = None,
        timeout: int = 120,
    ) -> None:
        self._model = model
        self._effort = effort
        self._timeout = timeout
        self._binary = binary or shutil.which("claude")
        if self._binary is None:
            raise RuntimeError(
                "The `claude` CLI was not found on PATH. Install Claude Code "
                "and run `claude login` before using the claude provider."
            )

    def complete(self, messages: list[ModelMessage], *, system: str | None = None) -> ModelResponse:
        prompt = self._render_transcript(messages)
        cmd = [
            self._binary,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--tools",
            "",  # no built-in tools — the Agent Loop owns tool-calling (Fase 5)
            "--strict-mcp-config",  # and no ambient MCP servers either — see module docstring
        ]
        if system:
            cmd += ["--system-prompt", system]
        if self._model:
            cmd += ["--model", self._model]
        if self._effort:
            cmd += ["--effort", self._effort]

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
        if proc.returncode != 0:
            raise RuntimeError(f"claude CLI exited {proc.returncode}: {proc.stderr.strip()}")

        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"claude CLI returned non-JSON output: {proc.stdout[:500]!r}") from e

        if data.get("is_error"):
            raise RuntimeError(f"claude CLI reported an error: {data.get('result')}")

        usage = data.get("usage", {})
        model_label = self._model or "claude (cli default)"
        if self._effort:
            model_label += f" [{self._effort}]"
        return ModelResponse(
            text=data.get("result", ""),
            model=model_label,
            stop_reason=data.get("stop_reason"),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            cost_usd=data.get("total_cost_usd"),
            raw=data,
        )

    @staticmethod
    def _render_transcript(messages: list[ModelMessage]) -> str:
        if len(messages) == 1:
            return messages[0].content
        lines = [f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}" for m in messages]
        return "\n\n".join(lines)
