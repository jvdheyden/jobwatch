from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


GATE_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "hooks"
    / "claude_coding_gate.py"
)


def _run(stdin: dict, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GATE_SCRIPT)],
        input=json.dumps(stdin),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


@pytest.fixture
def repo_fixture(tmp_case_dir: Path) -> Path:
    subprocess.run(
        ["git", "init", "-q", str(tmp_case_dir)],
        check=True,
        capture_output=True,
    )
    (tmp_case_dir / ".gitignore").write_text("private/\n", encoding="utf-8")
    (tmp_case_dir / "tracked.md").write_text("tracked\n", encoding="utf-8")
    private = tmp_case_dir / "private"
    private.mkdir(parents=True, exist_ok=True)
    (private / "secret.md").write_text("secret\n", encoding="utf-8")
    return tmp_case_dir


def _payload(**overrides) -> dict:
    base = {
        "session_id": "sess-test",
        "tool_name": "Edit",
        "tool_input": {"file_path": "tracked.md"},
        "cwd": "/nonexistent",
    }
    base.update(overrides)
    return base


def _env(repo: Path, marker_tmp: Path) -> dict:
    import os

    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(repo)
    env["TMPDIR"] = str(marker_tmp)
    return env


def _marker(marker_tmp: Path, session_id: str) -> Path:
    return marker_tmp / f"claude-coding-gate-{session_id}.flag"


def test_blocks_tracked_edit_without_marker(repo_fixture: Path, tmp_path: Path) -> None:
    marker_tmp = tmp_path / "tmp"
    marker_tmp.mkdir()

    result = _run(
        _payload(tool_input={"file_path": str(repo_fixture / "tracked.md")}),
        env=_env(repo_fixture, marker_tmp),
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "coding" in payload["hookSpecificOutput"]["permissionDecisionReason"]


def test_allows_gitignored_path(repo_fixture: Path, tmp_path: Path) -> None:
    marker_tmp = tmp_path / "tmp"
    marker_tmp.mkdir()

    result = _run(
        _payload(tool_input={"file_path": str(repo_fixture / "private" / "secret.md")}),
        env=_env(repo_fixture, marker_tmp),
    )

    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_allows_when_marker_present(repo_fixture: Path, tmp_path: Path) -> None:
    marker_tmp = tmp_path / "tmp"
    marker_tmp.mkdir()
    _marker(marker_tmp, "sess-test").touch()

    result = _run(
        _payload(tool_input={"file_path": str(repo_fixture / "tracked.md")}),
        env=_env(repo_fixture, marker_tmp),
    )

    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_allows_outside_repo(repo_fixture: Path, tmp_path: Path) -> None:
    marker_tmp = tmp_path / "tmp"
    marker_tmp.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("x\n", encoding="utf-8")

    result = _run(
        _payload(tool_input={"file_path": str(outside)}),
        env=_env(repo_fixture, marker_tmp),
    )

    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_allows_non_gated_tool(repo_fixture: Path, tmp_path: Path) -> None:
    marker_tmp = tmp_path / "tmp"
    marker_tmp.mkdir()

    result = _run(
        _payload(tool_name="Bash", tool_input={"command": "ls"}),
        env=_env(repo_fixture, marker_tmp),
    )

    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_fails_open_on_missing_session_id(repo_fixture: Path, tmp_path: Path) -> None:
    marker_tmp = tmp_path / "tmp"
    marker_tmp.mkdir()

    payload = _payload(tool_input={"file_path": str(repo_fixture / "tracked.md")})
    payload.pop("session_id")

    result = _run(payload, env=_env(repo_fixture, marker_tmp))

    assert result.returncode == 0
    assert result.stdout.strip() == ""
    assert "session_id" in result.stderr


def test_gates_notebook_edit(repo_fixture: Path, tmp_path: Path) -> None:
    marker_tmp = tmp_path / "tmp"
    marker_tmp.mkdir()

    result = _run(
        _payload(
            tool_name="NotebookEdit",
            tool_input={"notebook_path": str(repo_fixture / "tracked.md")},
        ),
        env=_env(repo_fixture, marker_tmp),
    )

    payload = json.loads(result.stdout)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_fails_open_on_non_json_stdin() -> None:
    result = subprocess.run(
        [sys.executable, str(GATE_SCRIPT)],
        input="not json",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "invalid JSON" in result.stderr
