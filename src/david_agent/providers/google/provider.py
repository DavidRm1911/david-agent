"""AntigravityProvider: talks to Gemini (and other models it hosts) via
Google's Antigravity CLI (`agy`) in headless print mode.

Google discontinued free-tier access through the standalone `gemini` CLI's
OAuth "Code Assist for individuals" tier (IneligibleTierError as of this
writing) and now serves the same free personal access through Antigravity
instead. `agy` was already installed and logged in on this machine from a
prior session — this provider reuses that login the same way
ClaudeCodeProvider reuses the `claude` CLI's: by shelling out to the real,
authenticated client, never by reading its credential file directly.
"""

from __future__ import annotations

import json
import shutil
import subprocess

from david_agent.models.base import ModelCapabilities, ModelMessage, ModelProvider, ModelResponse

DEFAULT_MODEL = "Gemini 3.5 Flash (Medium)"


class AntigravityProvider(ModelProvider):
    name = "gemini"
    capabilities = ModelCapabilities(
        streaming=False,
        tools=True,
        vision=True,
        structured_output=True,
        reasoning=True,
    )

    def __init__(self, *, model: str = DEFAULT_MODEL, binary: str | None = None, timeout: int = 330) -> None:
        self._model = model
        self._timeout = timeout
        self._binary = binary or shutil.which("agy")
        if self._binary is None:
            raise RuntimeError(
                "The `agy` (Antigravity) CLI was not found on PATH. Install it "
                "and log in before using the gemini provider."
            )

    def complete(self, messages: list[ModelMessage], *, system: str | None = None) -> ModelResponse:
        prompt = self._render_prompt(messages, system)
        cmd = [
            self._binary,
            "-p",
            prompt,
            "--model",
            self._model,
            "--output-format",
            "json",
            "--disable-slash-commands",
        ]

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
        if proc.returncode != 0:
            raise RuntimeError(f"agy CLI exited {proc.returncode}: {proc.stderr.strip()}")

        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"agy CLI returned non-JSON output: {proc.stdout[:500]!r}") from e

        if data.get("status") != "SUCCESS":
            raise RuntimeError(f"agy CLI reported failure: {data}")

        usage = data.get("usage", {})
        return ModelResponse(
            text=data.get("response", "").rstrip("\n"),
            model=self._model,
            stop_reason=data.get("status"),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            cost_usd=None,  # agy does not report a dollar cost
            raw=data,
        )

    @staticmethod
    def _render_prompt(messages: list[ModelMessage], system: str | None) -> str:
        parts: list[str] = []
        if system:
            parts.append(f"System: {system}")
        if len(messages) == 1:
            parts.append(messages[0].content)
        else:
            parts.extend(f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}" for m in messages)
        return "\n\n".join(parts)
