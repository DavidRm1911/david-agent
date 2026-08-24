# david-agent

Runtime de agentes de IA agnóstico de modelo. El modelo es un backend intercambiable, no el núcleo del sistema — el Agent Loop nunca sabe si está hablando con Claude, Gemini, un modelo local o una API OpenAI-compatible, solo con la interfaz `ModelProvider`.

## Qué hace

- **4 tipos de model provider**, todos reales y probados:
  - `claude` — vía el CLI de Claude Code (`claude -p`), reutiliza tu login, sin API key.
  - `gemini` — vía Antigravity CLI (`agy -p`), reutiliza tu login de Google, sin API key.
  - `qwen-local` — Ollama local (`qwen3.5:9b`), arranque perezoso (no toca el sistema hasta el primer uso real), coste $0.
  - `openai_compatible` — DeepSeek/OpenRouter/cualquier endpoint compatible, opt-in solo si hay API key en `.env` (nunca se activa solo).
- **Router manual** (`/model <nombre>`) — cambia de provider sin tocar el Agent Loop.
- **25 skills de Claude Code descubiertas automáticamente** con *lazy loading*: el modelo solo ve nombre+descripción; el cuerpo completo (`SKILL.md`) se carga bajo demanda solo si el modelo lo pide.
- **7 tools nativas** (filesystem read/write/list, shell.execute, sandbox.execute, git status/diff/log) + **tools MCP** vía la SDK oficial (`mcp/`), reutilizando tu `~/.claude.json` — mismo `Tool` interface para nativas y MCP, el loop no distingue.
- **PermissionEngine** con 3 modos (`safe`/`ask`/`auto`) y un blocklist de 4 patrones exactos que nunca se saltan — pero es matching literal, no una defensa general contra comandos destructivos (`x=/; rm -rf $x` o `cd / && rm -rf .` no matchean). En modo `auto`, este blocklist es la única protección real para `shell.execute`.
- **Memoria persistente en SQLite** (`~/.david-agent/sessions.db`) — sessions, messages, model_calls, tool_calls.
- **Sandbox Docker** (`sandbox.execute`) — contenedor efímero, sin red, solo ve el workspace montado.
- **Benchmark objetivo** (`/benchmark <prompt>`) — latencia/tokens/coste reales medidos contra todos los modelos, nunca un "quality score" inventado.

## Cómo correrlo

```bash
cd david-agent
uv run david-agent
```

Requiere: `claude` CLI logueado (Claude Code), `agy` CLI logueado (Antigravity, opcional), Ollama instalado (opcional, se auto-arranca al primer uso), Docker corriendo (opcional, para `sandbox.execute`). Nada de esto es obligatorio individualmente — el registro de cada provider/tool es best-effort.

Comandos dentro de la sesión: `/model [nombre]`, `/skills`, `/tools`, `/mode [safe|ask|auto]`, `/sessions`, `/benchmark <prompt>`, `exit`/`quit`.

## Archivos clave

```
src/david_agent/
├── core/loop.py           # el Agent Loop — protocolo de texto LOAD_SKILL:/TOOL_CALL:
├── core/agent.py           # Agent = configuración (router, skills, tools, permissions, memory)
├── models/router.py         # ModelRouter — selección manual de provider
├── providers/               # anthropic/ google/ local/ openai_compatible/
├── skills/registry.py       # discovery + lazy loading de SKILL.md
├── tools/                   # filesystem, shell, git, sandbox
├── mcp/                     # registry + client (SDK oficial) + adapter
├── permissions/engine.py    # PermissionEngine (safe/ask/auto + blocklist)
├── memory/sqlite.py         # persistencia de sessions/messages/tool_calls/model_calls
├── sandbox/docker.py        # DockerSandbox — aislado, --network none
├── benchmark/runner.py      # medición objetiva multi-provider
└── cli/main.py              # REPL, wiring de todo lo anterior
```

## Sugerencias de mejora

- **Caching en `AntigravityProvider`**: el benchmark reveló que Gemini reenvía ~13K tokens de system prompt en cada llamada (vs. ~2 de Claude, que sí cachea) — vale la pena investigar si `agy` soporta algo equivalente a prompt caching.
- **`--strict-mcp-config` fue un fix real, no cosmético**: sin él, `ClaudeCodeProvider` filtraba el entorno MCP ambiente (Figma/Gmail/etc.) hacia el subproceso. Si se agregan más providers basados en CLI, revisar el mismo tipo de fuga.
- **Reconexión MCP por llamada**: `MCPClient` abre/cierra conexión en cada `list_tools()`/`call_tool()` — simple pero caro para servidores lentos (el gateway Docker tardó ~25s en frío). Si se agregan más servidores MCP, considerar una sesión persistente.
- **`ClaudeCodeProvider`/`AntigravityProvider` no soportan streaming** — ambos son `capabilities.streaming=False`; si la UX interactiva importa, valdría la pena investigar si sus CLIs exponen un modo streaming en headless.
- **Sin tests automatizados todavía** — todo lo validado en este proyecto fue con pruebas manuales end-to-end reales (documentadas en el historial de conversación), no hay suite de `pytest`. Antes de escalar el proyecto, vale la pena formalizar al menos los casos ya probados a mano.
