from __future__ import annotations

import json
from pathlib import Path

import pytest

from hooks import install_claude_coding_gate_hook as hook


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_clean_install_writes_both_hooks(tmp_case_dir: Path) -> None:
    target = tmp_case_dir / "settings.local.json"

    status = hook.install(target)

    assert status == hook.STATUS_INSTALLED
    data = _read(target)
    pre = data["hooks"]["PreToolUse"]
    post = data["hooks"]["PostToolUse"]
    assert len(pre) == 1
    assert pre[0]["matcher"] == hook.GATE_MATCHER
    assert "claude_coding_gate.py" in pre[0]["hooks"][0]["command"]
    assert len(post) == 1
    assert post[0]["matcher"] == hook.MARK_MATCHER
    assert "claude_coding_gate_mark.py" in post[0]["hooks"][0]["command"]


def test_idempotent_second_run(tmp_case_dir: Path) -> None:
    target = tmp_case_dir / "settings.local.json"

    hook.install(target)
    first = target.read_bytes()
    status = hook.install(target)

    assert status == hook.STATUS_ALREADY_PRESENT
    assert target.read_bytes() == first


def test_preserves_existing_permissions(tmp_case_dir: Path) -> None:
    target = tmp_case_dir / "settings.local.json"
    target.write_text(
        json.dumps(
            {
                "permissions": {"allow": ["Bash(ls)"]},
                "prefersReducedMotion": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    status = hook.install(target)

    assert status == hook.STATUS_INSTALLED
    data = _read(target)
    assert data["permissions"] == {"allow": ["Bash(ls)"]}
    assert data["prefersReducedMotion"] is True
    assert "PreToolUse" in data["hooks"]
    assert "PostToolUse" in data["hooks"]


def test_adds_missing_half_when_other_present(tmp_case_dir: Path) -> None:
    target = tmp_case_dir / "settings.local.json"
    target.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": hook.GATE_MATCHER,
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "/existing/path/claude_coding_gate.py",
                                }
                            ],
                        }
                    ]
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    status = hook.install(target)

    assert status == hook.STATUS_UPDATED
    data = _read(target)
    pre = data["hooks"]["PreToolUse"]
    post = data["hooks"]["PostToolUse"]
    assert len(pre) == 1
    assert "/existing/path/claude_coding_gate.py" in pre[0]["hooks"][0]["command"]
    assert len(post) == 1
    assert "claude_coding_gate_mark.py" in post[0]["hooks"][0]["command"]


def test_rejects_non_object_top_level(tmp_case_dir: Path) -> None:
    target = tmp_case_dir / "settings.local.json"
    target.write_text("[]\n", encoding="utf-8")

    with pytest.raises(SystemExit):
        hook.install(target)


def test_coexists_with_session_hook(tmp_case_dir: Path) -> None:
    target = tmp_case_dir / "settings.local.json"
    target.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python3 -c 'CLAUDE_SESSION_ID=x'",
                                }
                            ]
                        }
                    ]
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    status = hook.install(target)

    assert status == hook.STATUS_INSTALLED
    data = _read(target)
    assert "CLAUDE_SESSION_ID" in data["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert "claude_coding_gate.py" in data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
