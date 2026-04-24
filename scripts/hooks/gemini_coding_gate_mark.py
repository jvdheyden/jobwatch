#!/usr/bin/env python3
"""Gemini CLI ``AfterTool`` marker for the coding-skill gate.

Invoked after the ``activate_skill`` tool runs. When the skill is ``coding``,
touch a session-scoped marker at ``/tmp/gemini-coding-gate-<session_id>.flag``
so that subsequent ``write_file``/``replace`` calls pass the ``BeforeTool`` gate
in ``gemini_coding_gate.py``.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


def _marker_path(session_id: str) -> Path:
    return Path(tempfile.gettempdir()) / f"gemini-coding-gate-{session_id}.flag"


def _skill_name(tool_input: dict) -> str | None:
    if not isinstance(tool_input, dict):
        return None
    name = tool_input.get("name")
    if isinstance(name, str) and name:
        return name
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as err:
        print(f"gemini_coding_gate_mark: invalid JSON on stdin ({err}); ignoring", file=sys.stderr)
        return 0

    if not isinstance(payload, dict):
        return 0
    if payload.get("tool_name") != "activate_skill":
        return 0

    skill = _skill_name(payload.get("tool_input", {}))
    if skill is None:
        return 0
    if skill != "coding":
        return 0

    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        print("gemini_coding_gate_mark: missing session_id; cannot set marker", file=sys.stderr)
        return 0

    _marker_path(session_id).touch()
    return 0


if __name__ == "__main__":
    sys.exit(main())
