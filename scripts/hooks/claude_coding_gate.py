#!/usr/bin/env python3
"""Claude Code ``PreToolUse`` gate that enforces the repo's coding-skill rule.

``AGENTS.md`` requires that the ``coding`` skill be invoked before any
edit in repo-development mode. This gate blocks ``Edit``/``Write``/``NotebookEdit``
calls against tracked files in ``$CLAUDE_PROJECT_DIR`` until a session marker
shows the ``coding`` skill has been loaded. Gitignored paths stay editable so
personal state (``profile/``, ``tracks/<slug>/``, ``docs/plans/``, etc.) never
deadlocks.

Block output targets the current Claude Code contract documented at
https://code.claude.com/docs/en/hooks (JSON on stdout, exit 0, using
``hookSpecificOutput.permissionDecision = "deny"``).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

GATED_TOOLS = frozenset({"Edit", "Write", "NotebookEdit"})


def _marker_path(session_id: str) -> Path:
    return Path(tempfile.gettempdir()) / f"claude-coding-gate-{session_id}.flag"


def _target_path(tool_name: str, tool_input: dict) -> str | None:
    if not isinstance(tool_input, dict):
        return None
    if tool_name == "NotebookEdit":
        candidate = tool_input.get("notebook_path") or tool_input.get("file_path")
    else:
        candidate = tool_input.get("file_path")
    if isinstance(candidate, str) and candidate:
        return candidate
    return None


def _is_inside(repo_root: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(repo_root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _is_gitignored(repo_root: Path, target: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "check-ignore", "-q", str(target)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0


def _block(path: str) -> dict:
    reason = (
        f"Edit of tracked repo file '{path}' is blocked: invoke the `coding` "
        "skill first (run /coding), then retry. The skill explains the "
        "project's public/private split, style rules, and testing contract. "
        "Gitignored paths (profile/, tracks/<slug>/, docs/plans/, .env.local, "
        "artifacts/, logs/) are exempt and do not require the skill."
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as err:
        print(f"claude_coding_gate: invalid JSON on stdin ({err}); allowing", file=sys.stderr)
        return 0

    if not isinstance(payload, dict):
        print("claude_coding_gate: non-object payload; allowing", file=sys.stderr)
        return 0

    tool_name = payload.get("tool_name")
    if tool_name not in GATED_TOOLS:
        return 0

    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        print("claude_coding_gate: missing session_id; failing open", file=sys.stderr)
        return 0

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd")
    if not project_dir:
        print("claude_coding_gate: no CLAUDE_PROJECT_DIR or cwd; failing open", file=sys.stderr)
        return 0
    repo_root = Path(project_dir)

    target_raw = _target_path(tool_name, payload.get("tool_input", {}))
    if not target_raw:
        return 0
    target = Path(target_raw)
    if not target.is_absolute():
        target = repo_root / target

    if not _is_inside(repo_root, target):
        return 0

    if _is_gitignored(repo_root, target):
        return 0

    if _marker_path(session_id).exists():
        return 0

    json.dump(_block(str(target)), sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
