"""SQLiteMemoryStore: schema creation and round-trips for the four tables
the webui dashboard and /sessions command both read from."""

from __future__ import annotations

from pathlib import Path

from david_agent.memory.sqlite import SQLiteMemoryStore


def _store(tmp_path: Path) -> SQLiteMemoryStore:
    return SQLiteMemoryStore(db_path=tmp_path / "sessions.db")


def test_create_session_and_list(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create_session("s1", "default")

    sessions = store.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].id == "s1"
    assert sessions[0].agent_name == "default"


def test_create_session_is_idempotent(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create_session("s1", "default")
    store.create_session("s1", "default")  # INSERT OR IGNORE — must not raise or duplicate

    assert len(store.list_sessions()) == 1


def test_save_message_roundtrip(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create_session("s1", "default")
    store.save_message("s1", "user", "hello")
    store.save_message("s1", "assistant", "hi there")

    detail = store.get_session_detail("s1")
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert [m["content"] for m in detail["messages"]] == ["hello", "hi there"]


def test_save_model_call_roundtrip(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create_session("s1", "default")
    store.save_model_call("s1", "claude", "claude (cli default)", 10, 20, 0.05)

    detail = store.get_session_detail("s1")
    assert len(detail["model_calls"]) == 1
    call = detail["model_calls"][0]
    assert call["provider"] == "claude"
    assert call["input_tokens"] == 10
    assert call["output_tokens"] == 20
    assert call["cost_usd"] == 0.05


def test_save_tool_call_records_error_distinct_from_success(tmp_path: Path) -> None:
    # Regression test for the bug fixed in core/loop.py: the error column
    # used to be always NULL, even for real failures.
    store = _store(tmp_path)
    store.create_session("s1", "default")
    store.save_tool_call("s1", "filesystem.read", {"path": "README.md"}, "file contents", None)
    store.save_tool_call("s1", "shell.execute", {"command": "rm -rf /"}, "blocked: ...", "blocked: ...")

    detail = store.get_session_detail("s1")
    assert len(detail["tool_calls"]) == 2
    ok_call, failed_call = detail["tool_calls"]
    assert ok_call["error"] is None
    assert failed_call["error"] is not None


def test_list_sessions_respects_limit(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for i in range(5):
        store.create_session(f"s{i}", "default")

    assert len(store.list_sessions(limit=3)) == 3


def test_get_session_detail_empty_session(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create_session("s1", "default")

    detail = store.get_session_detail("s1")
    assert detail == {"messages": [], "model_calls": [], "tool_calls": []}
