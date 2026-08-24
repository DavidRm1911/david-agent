"""Filesystem tools: the sensitive-path backstop (same check PermissionEngine
already applies before these ever run — here in case execute() is called
directly) and basic read/write/list correctness."""

from __future__ import annotations

from pathlib import Path

from david_agent.tools.filesystem import FileSystemListTool, FileSystemReadTool, FileSystemWriteTool


def test_read_blocks_sensitive_path(tmp_path: Path) -> None:
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir()
    key = ssh_dir / "id_rsa"
    key.write_text("not a real key")

    result = FileSystemReadTool().execute({"path": str(key)})
    assert result.output == ""
    assert result.error is not None
    assert "blocked" in result.error


def test_read_roundtrip(tmp_path: Path) -> None:
    f = tmp_path / "note.txt"
    f.write_text("hello world")

    result = FileSystemReadTool().execute({"path": str(f)})
    assert result.error is None
    assert result.output == "hello world"


def test_read_missing_path_argument() -> None:
    result = FileSystemReadTool().execute({})
    assert result.error is not None


def test_read_nonexistent_file(tmp_path: Path) -> None:
    result = FileSystemReadTool().execute({"path": str(tmp_path / "nope.txt")})
    assert result.error is not None
    assert "does not exist" in result.error


def test_list_blocks_sensitive_path(tmp_path: Path) -> None:
    aws_dir = tmp_path / ".aws"
    aws_dir.mkdir()
    (aws_dir / "credentials").write_text("[default]")

    result = FileSystemListTool().execute({"path": str(aws_dir / "credentials")})
    assert result.error is not None
    assert "blocked" in result.error


def test_list_directory(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("")
    (tmp_path / "sub").mkdir()

    result = FileSystemListTool().execute({"path": str(tmp_path)})
    assert result.error is None
    assert "a.txt" in result.output
    assert "sub/" in result.output


def test_write_blocks_sensitive_path(tmp_path: Path) -> None:
    target = tmp_path / ".env"
    result = FileSystemWriteTool().execute({"path": str(target), "content": "SECRET=1"})
    assert result.error is not None
    assert "blocked" in result.error
    assert not target.exists()


def test_write_creates_file_and_parents(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "dir" / "out.txt"
    result = FileSystemWriteTool().execute({"path": str(target), "content": "data"})
    assert result.error is None
    assert target.read_text() == "data"


def test_write_is_flagged_dangerous() -> None:
    assert FileSystemWriteTool().dangerous is True
    assert FileSystemReadTool().dangerous is False
    assert FileSystemListTool().dangerous is False
