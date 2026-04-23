#!/usr/bin/env python3
"""Install repo-local Claude Code hooks that enforce the coding-skill rule.

Two hook entries are merged into ``.claude/settings.local.json``:

* a ``PreToolUse`` matcher for ``Edit|Write|NotebookEdit`` that runs
  ``scripts/hooks/claude_coding_gate.py`` and blocks edits to tracked repo
  files until the ``coding`` skill has been invoked in the session;
* a ``PostToolUse`` matcher for ``Skill`` that runs
  ``scripts/hooks/claude_coding_gate_mark.py`` and writes the session marker
  when the ``coding`` skill completes.

The merge is idempotent and preserves every other key in the settings file.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

GATE_MATCHER = "Edit|Write|NotebookEdit"
MARK_MATCHER = "Skill"
GATE_COMMAND = '"$CLAUDE_PROJECT_DIR"/scripts/hooks/claude_coding_gate.py'
MARK_COMMAND = '"$CLAUDE_PROJECT_DIR"/scripts/hooks/claude_coding_gate_mark.py'
HOOK_MARKER = "claude_coding_gate"
STATUS_INSTALLED = "installed"
STATUS_ALREADY_PRESENT = "already-present"
STATUS_UPDATED = "updated"


def _load_settings(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise SystemExit(
            f"{path}: top-level JSON must be an object, got {type(data).__name__}"
        )
    return data


def _event_entries(settings: dict, event: str) -> list:
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise SystemExit("settings 'hooks' must be an object")
    entries = hooks.setdefault(event, [])
    if not isinstance(entries, list):
        raise SystemExit(f"settings 'hooks.{event}' must be a list")
    return entries


def _hook_already_present(entries: list, command_marker: str) -> bool:
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        inner = entry.get("hooks", [])
        if not isinstance(inner, list):
            continue
        for hook in inner:
            if not isinstance(hook, dict):
                continue
            command = hook.get("command", "")
            if isinstance(command, str) and command_marker in command:
                return True
    return False


def _append_entry(entries: list, matcher: str, command: str) -> None:
    entries.append(
        {
            "matcher": matcher,
            "hooks": [{"type": "command", "command": command}],
        }
    )


def install(settings_path: Path) -> str:
    settings = _load_settings(settings_path)
    pre_entries = _event_entries(settings, "PreToolUse")
    post_entries = _event_entries(settings, "PostToolUse")

    pre_present = _hook_already_present(pre_entries, "claude_coding_gate.py")
    post_present = _hook_already_present(post_entries, "claude_coding_gate_mark.py")
    if pre_present and post_present:
        return STATUS_ALREADY_PRESENT

    if not pre_present:
        _append_entry(pre_entries, GATE_MATCHER, GATE_COMMAND)
    if not post_present:
        _append_entry(post_entries, MARK_MATCHER, MARK_COMMAND)

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(settings, indent=2) + "\n", encoding="utf-8"
    )
    return STATUS_UPDATED if (pre_present or post_present) else STATUS_INSTALLED


def _default_target(root: Path) -> Path:
    return root / ".claude" / "settings.local.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=os.environ.get("JOB_AGENT_ROOT", os.getcwd()),
        help="Repo root (defaults to $JOB_AGENT_ROOT or cwd).",
    )
    parser.add_argument(
        "--target",
        default=None,
        help="Override the settings file path (defaults to ROOT/.claude/settings.local.json).",
    )
    args = parser.parse_args(argv)

    target = Path(args.target) if args.target else _default_target(Path(args.root))
    status = install(target)
    print(status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
