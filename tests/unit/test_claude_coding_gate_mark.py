from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


MARK_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "hooks"
    / "claude_coding_gate_mark.py"
)


def _env(marker_tmp: Path) -> dict:
    env = os.environ.copy()
    env["TMPDIR"] = str(marker_tmp)
    return env


def _run(stdin: dict, env: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MARK_SCRIPT)],
        input=json.dumps(stdin),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def _marker(marker_tmp: Path, session_id: str) -> Path:
    return marker_tmp / f"claude-coding-gate-{session_id}.flag"


def test_sets_marker_for_coding_skill(tmp_path: Path) -> None:
    marker_tmp = tmp_path / "tmp"
    marker_tmp.mkdir()

    result = _run(
        {
            "session_id": "sess-mark",
            "tool_name": "Skill",
            "tool_input": {"skill": "coding"},
        },
        env=_env(marker_tmp),
    )

    assert result.returncode == 0
    assert _marker(marker_tmp, "sess-mark").exists()


def test_sets_marker_for_plugin_namespaced_coding(tmp_path: Path) -> None:
    marker_tmp = tmp_path / "tmp"
    marker_tmp.mkdir()

    result = _run(
        {
            "session_id": "sess-plugin",
            "tool_name": "Skill",
            "tool_input": {"skill": "myplugin:coding"},
        },
        env=_env(marker_tmp),
    )

    assert result.returncode == 0
    assert _marker(marker_tmp, "sess-plugin").exists()


def test_ignores_other_skills(tmp_path: Path) -> None:
    marker_tmp = tmp_path / "tmp"
    marker_tmp.mkdir()

    result = _run(
        {
            "session_id": "sess-other",
            "tool_name": "Skill",
            "tool_input": {"skill": "find-jobs"},
        },
        env=_env(marker_tmp),
    )

    assert result.returncode == 0
    assert not _marker(marker_tmp, "sess-other").exists()


def test_ignores_non_skill_tools(tmp_path: Path) -> None:
    marker_tmp = tmp_path / "tmp"
    marker_tmp.mkdir()

    result = _run(
        {
            "session_id": "sess-bash",
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
        },
        env=_env(marker_tmp),
    )

    assert result.returncode == 0
    assert not _marker(marker_tmp, "sess-bash").exists()


def test_no_op_without_session_id(tmp_path: Path) -> None:
    marker_tmp = tmp_path / "tmp"
    marker_tmp.mkdir()

    result = _run(
        {"tool_name": "Skill", "tool_input": {"skill": "coding"}},
        env=_env(marker_tmp),
    )

    assert result.returncode == 0
    assert "session_id" in result.stderr
    assert list(marker_tmp.iterdir()) == []


def test_idempotent_multiple_invocations(tmp_path: Path) -> None:
    marker_tmp = tmp_path / "tmp"
    marker_tmp.mkdir()

    payload = {
        "session_id": "sess-idem",
        "tool_name": "Skill",
        "tool_input": {"skill": "coding"},
    }
    _run(payload, env=_env(marker_tmp))
    first_mtime = _marker(marker_tmp, "sess-idem").stat().st_mtime_ns
    _run(payload, env=_env(marker_tmp))
    marker = _marker(marker_tmp, "sess-idem")
    assert marker.exists()
    assert marker.stat().st_mtime_ns >= first_mtime
