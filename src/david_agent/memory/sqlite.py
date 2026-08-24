"""SQLite-backed MemoryStore. One file at ~/.david-agent/sessions.db, shared
across every project this runtime is used from — no vector DB, no RAG yet
(CLAUDE.md §22 explicitly defers those).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from david_agent.memory.base import MemoryStore, SessionRecord

DEFAULT_DB_PATH = Path.home() / ".david-agent" / "sessions.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS model_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    tool_name TEXT NOT NULL,
    args_json TEXT NOT NULL,
    result TEXT,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class SQLiteMemoryStore(MemoryStore):
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def create_session(self, session_id: str, agent_name: str) -> None:
        self._conn.execute("INSERT OR IGNORE INTO sessions (id, agent_name) VALUES (?, ?)", (session_id, agent_name))
        self._conn.commit()

    def save_message(self, session_id: str, role: str, content: str) -> None:
        self._conn.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)", (session_id, role, content)
        )
        self._conn.commit()

    def save_model_call(
        self,
        session_id: str,
        provider: str,
        model: str,
        input_tokens: int | None,
        output_tokens: int | None,
        cost_usd: float | None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO model_calls (session_id, provider, model, input_tokens, output_tokens, cost_usd) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, provider, model, input_tokens, output_tokens, cost_usd),
        )
        self._conn.commit()

    def save_tool_call(self, session_id: str, tool_name: str, args: dict, result: str, error: str | None) -> None:
        self._conn.execute(
            "INSERT INTO tool_calls (session_id, tool_name, args_json, result, error) VALUES (?, ?, ?, ?, ?)",
            (session_id, tool_name, json.dumps(args), result, error),
        )
        self._conn.commit()

    def list_sessions(self, limit: int = 20) -> list[SessionRecord]:
        rows = self._conn.execute(
            "SELECT id, agent_name, created_at FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [SessionRecord(id=r[0], agent_name=r[1], created_at=r[2]) for r in rows]

    def get_session_detail(self, session_id: str) -> dict:
        self._conn.row_factory = sqlite3.Row
        try:
            messages = self._conn.execute(
                "SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY id", (session_id,)
            ).fetchall()
            model_calls = self._conn.execute(
                "SELECT provider, model, input_tokens, output_tokens, cost_usd, created_at "
                "FROM model_calls WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
            tool_calls = self._conn.execute(
                "SELECT tool_name, args_json, result, error, created_at FROM tool_calls WHERE session_id = ? "
                "ORDER BY id",
                (session_id,),
            ).fetchall()
            return {
                "messages": [dict(r) for r in messages],
                "model_calls": [dict(r) for r in model_calls],
                "tool_calls": [dict(r) for r in tool_calls],
            }
        finally:
            self._conn.row_factory = None
