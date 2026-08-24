"""OpenAICompatibleProvider: talks to any OpenAI Chat Completions-compatible
API — DeepSeek, OpenRouter, local gateways, etc. — via base_url + api_key.

Unlike the other three providers (Claude/Gemini via CLI subscriptions, Qwen
via local Ollama), this one costs real money per call and needs a real
credential. It is never auto-registered on its own — cli/main.py only wires
it in when the corresponding API key is already present in the environment
(CLAUDE.md §39: never pay for an API just because it exists). The key is
read from an env var, never hardcoded, never written to this repo (§24).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from david_agent.models.base import ModelCapabilities, ModelMessage, ModelProvider, ModelResponse


class OpenAICompatibleProvider(ModelProvider):
    capabilities = ModelCapabilities(streaming=False, tools=False, structured_output=True, reasoning=False)

    def __init__(self, *, name: str, base_url: str, api_key: str, model: str, timeout: int = 120) -> None:
        self.name = name
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    def complete(self, messages: list[ModelMessage], *, system: str | None = None) -> ModelResponse:
        chat_messages = []
        if system:
            chat_messages.append({"role": "system", "content": system})
        chat_messages.extend({"role": m.role, "content": m.content} for m in messages)

        payload = json.dumps({"model": self._model, "messages": chat_messages}).encode()
        req = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._api_key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:300]
            raise RuntimeError(f"{self.name} API returned {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"{self.name} request failed: {e}") from e

        choice = data["choices"][0]
        usage = data.get("usage", {})
        return ModelResponse(
            text=choice["message"]["content"],
            model=data.get("model", self._model),
            stop_reason=choice.get("finish_reason"),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            cost_usd=None,  # unknown without a per-model pricing table — never invent one
            raw=data,
        )
