from __future__ import annotations

import json
from pathlib import Path

import pytest

from hooks import install_claude_session_hook as hook


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_clean_install_writes_hook(tmp_case_dir: Path) -> None:
    target = tmp_case_dir / ".claude" / "settings.local.json"

    status = hook.install(target)

    assert status == hook.STATUS_INSTALLED
    data = _read(target)
    entries = data["hooks"]["SessionStart"]
    assert len(entries) == 1
    command = entries[0]["hooks"][0]["command"]
    assert "CLAUDE_SESSION_ID" in command
    assert "jq" not in command


def test_idempotent_second_run(tmp_case_dir: Path) -> None:
    target = tmp_case_dir / ".claude" / "settings.local.json"

    hook.install(target)
    before = target.read_text(encoding="utf-8")

    status = hook.install(target)

    assert status == hook.STATUS_ALREADY_PRESENT
    assert target.read_text(encoding="utf-8") == before


def test_preserves_existing_permissions(tmp_case_dir: Path) -> None:
    target = tmp_case_dir / ".claude" / "settings.local.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "permissions": {"allow": ["Bash(python3 *)"]},
                "prefersReducedMotion": False,
            }
        ),
        encoding="utf-8",
    )

    status = hook.install(target)

    assert status == hook.STATUS_INSTALLED
    data = _read(target)
    assert data["permissions"]["allow"] == ["Bash(python3 *)"]
    assert data["prefersReducedMotion"] is False
    assert "SessionStart" in data["hooks"]


def test_rejects_non_object_top_level(tmp_case_dir: Path) -> None:
    target = tmp_case_dir / ".claude" / "settings.local.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[1, 2, 3]", encoding="utf-8")

    with pytest.raises(SystemExit):
        hook.install(target)


def test_detects_existing_hook_with_any_command_shape(tmp_case_dir: Path) -> None:
    target = tmp_case_dir / ".claude" / "settings.local.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "jq -r '\"export CLAUDE_SESSION_ID=\\(.session_id)\"' >> \"$CLAUDE_ENV_FILE\"",
                                }
                            ]
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    status = hook.install(target)

    assert status == hook.STATUS_ALREADY_PRESENT
    data = _read(target)
    assert len(data["hooks"]["SessionStart"]) == 1
