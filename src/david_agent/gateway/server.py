"""OpenAI-compatible HTTP gateway in front of our own ModelRegistry.

Why this exists: DSH's "Custom provider" settings screen expects an HTTP
endpoint speaking the openai-completions protocol plus a real API key. Our
ClaudeCodeProvider and AntigravityProvider don't have an API key — they
shell out to CLIs that reuse existing subscription logins, which is the
whole point (CLAUDE.md §19: never fake a subscription into an API). This
server is the bridge: DSH sends it normal-looking OpenAI chat completion
requests, and it serves them for real using our zero-cost providers.

Not a general-purpose OpenAI server — just enough of the protocol
(POST /v1/chat/completions, GET /v1/models) for DSH's custom-provider client
to work against.

No CORS headers, deliberately: DSH's own backend calls this server-to-server,
which browsers' CORS rules don't apply to anyway. A wildcard
Access-Control-Allow-Origin here would let any webpage open in the same
browser call this gateway cross-origin and silently spend the user's
subscription — this used to have exactly that header; removed once someone
pointed out what it actually exposed.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from david_agent.cli.main import build_registry
from david_agent.models.base import ModelMessage, ModelProvider
from david_agent.models.registry import ModelRegistry
from david_agent.providers.anthropic.provider import ClaudeCodeProvider
from david_agent.providers.google.provider import AntigravityProvider

DEFAULT_PORT = 8899

# Model IDs exposed to DSH beyond the registry's coarse "claude"/"gemini" —
# each maps to a concrete (model, effort) combination on the real CLI, so
# DSH's model picker shows actual variants instead of one opaque default.
# Claude: --model + --effort are independent flags (CLAUDE_MODELS is base
# model only; any id below can carry an -<effort> suffix, parsed generically
# since claude's own effort levels are a small fixed set).
_CLAUDE_EFFORTS = ("low", "medium", "high", "xhigh", "max")
_CLAUDE_BASE_MODELS = {
    "claude": None,
    "claude-haiku": "haiku",
    "claude-sonnet": "sonnet",
    "claude-opus": "opus",
    "claude-fable": "fable",
}

# Gemini: agy bakes the effort tier into the model *name* itself, so there's
# no separate effort axis here — each id is one real `agy models` entry.
_GEMINI_MODELS = {
    "gemini": "Gemini 3.5 Flash (Medium)",
    "gemini-flash-low": "Gemini 3.5 Flash (Low)",
    "gemini-flash-medium": "Gemini 3.5 Flash (Medium)",
    "gemini-flash-high": "Gemini 3.5 Flash (High)",
    "gemini-flash36-low": "Gemini 3.6 Flash (Low)",
    "gemini-flash36-medium": "Gemini 3.6 Flash (Medium)",
    "gemini-flash36-high": "Gemini 3.6 Flash (High)",
    "gemini-pro-low": "Gemini 3.1 Pro (Low)",
    "gemini-pro-high": "Gemini 3.1 Pro (High)",
}


def _resolve_claude(model_id: str) -> ModelProvider | None:
    effort = None
    base = model_id
    for e in _CLAUDE_EFFORTS:
        if model_id.endswith(f"-{e}"):
            effort, base = e, model_id[: -(len(e) + 1)]
            break
    if base not in _CLAUDE_BASE_MODELS:
        return None
    return ClaudeCodeProvider(model=_CLAUDE_BASE_MODELS[base], effort=effort)


def resolve_provider(registry: ModelRegistry, model_id: str) -> ModelProvider:
    """Every extra id (claude-opus-max, gemini-flash-high, ...) constructs a
    fresh provider on demand — cheap, since none of our providers do I/O
    until complete() is actually called. Falls back to the plain registry
    for "qwen-local" and anything else already registered.
    """
    if model_id in _GEMINI_MODELS:
        return AntigravityProvider(model=_GEMINI_MODELS[model_id])
    claude_provider = _resolve_claude(model_id)
    if claude_provider is not None:
        return claude_provider
    return registry.get(model_id)


def all_model_ids(registry: ModelRegistry) -> list[str]:
    ids = set(registry.names()) | set(_CLAUDE_BASE_MODELS) | set(_GEMINI_MODELS)
    ids |= {f"{base}-{e}" for base in _CLAUDE_BASE_MODELS for e in _CLAUDE_EFFORTS}
    return sorted(ids)

# Our providers return each backend's native stop reason ("end_turn" from
# Claude, etc.) — OpenAI-compatible clients validate finish_reason against a
# fixed enum, so anything not already one of those values normalizes to the
# closest match here rather than being passed through as-is.
_FINISH_REASON_MAP = {
    "end_turn": "stop",
    "stop": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "length": "length",
}


def _normalize_finish_reason(reason: str | None) -> str:
    return _FINISH_REASON_MAP.get(reason or "stop", "stop")


def _make_handler(registry: ModelRegistry) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:  # quieter default logging
            print(f"[gateway] {self.address_string()} - {fmt % args}")

        def _send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_sse_completion(self, completion_id: str, model: str, response) -> None:
            """None of our providers stream token-by-token, so this sends the
            full text as one SSE delta chunk followed by the finish_reason
            chunk — satisfies clients that require SSE framing (CLAUDE_CODE
            "stream ended without finish_reason") without pretending we have
            real incremental streaming.
            """
            self.close_connection = True  # tell the client the stream is really over, not stalled
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()

            created = int(time.time())

            def chunk(delta: dict, finish_reason: str | None) -> dict:
                return {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
                }

            events = [
                chunk({"role": "assistant", "content": response.text}, None),
                chunk({}, _normalize_finish_reason(response.stop_reason)),
            ]
            for event in events:
                self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

        def do_GET(self) -> None:
            if self.path.rstrip("/") == "/v1/models":
                data = [{"id": name, "object": "model", "owned_by": "david-agent"} for name in all_model_ids(registry)]
                self._send_json(200, {"object": "list", "data": data})
                return
            self._send_json(404, {"error": {"message": "not found"}})

        def do_POST(self) -> None:
            if self.path.rstrip("/") != "/v1/chat/completions":
                self._send_json(404, {"error": {"message": "not found"}})
                return

            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length))
                model_name = body.get("model")
                raw_messages = body.get("messages", [])
                system = next((m["content"] for m in raw_messages if m.get("role") == "system"), None)
                messages = [
                    ModelMessage(role=m["role"], content=m["content"])
                    for m in raw_messages
                    if m.get("role") != "system"
                ]
            except (ValueError, TypeError, KeyError) as e:
                # ValueError: bad Content-Length or invalid JSON. KeyError: a
                # message dict missing "role"/"content". All three used to
                # crash the request thread with no response instead of a
                # clean 400 — found while reviewing security-sensitive edges.
                self._send_json(400, {"error": {"message": f"malformed request body: {e}"}})
                return

            try:
                provider = resolve_provider(registry, model_name)
                response = provider.complete(messages, system=system)
            except (KeyError, RuntimeError) as e:
                self._send_json(502, {"error": {"message": str(e)}})
                return

            completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"

            if body.get("stream"):
                self._send_sse_completion(completion_id, response.model, response)
                return

            self._send_json(
                200,
                {
                    "id": completion_id,
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": response.model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": response.text},
                            "finish_reason": _normalize_finish_reason(response.stop_reason),
                        }
                    ],
                    "usage": {
                        "prompt_tokens": response.input_tokens or 0,
                        "completion_tokens": response.output_tokens or 0,
                        "total_tokens": (response.input_tokens or 0) + (response.output_tokens or 0),
                    },
                },
            )

    return Handler


def main() -> None:
    try:
        registry = build_registry()
    except RuntimeError as e:
        print(f"Failed to start: {e}", file=sys.stderr)
        sys.exit(1)

    server = ThreadingHTTPServer(("127.0.0.1", DEFAULT_PORT), _make_handler(registry))
    print(f"david-agent gateway: http://127.0.0.1:{DEFAULT_PORT}/v1")
    print(f"models: {', '.join(all_model_ids(registry))}")
    print("Point DSH's Custom provider Base URL here, API protocol openai-completions, any API key text.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
