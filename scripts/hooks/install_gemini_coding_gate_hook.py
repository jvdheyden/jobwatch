#!/usr/bin/env python3
"""Install repo-local Gemini CLI hooks that enforce the coding-skill rule.

Two hook entries are merged into ``.gemini/settings.json``:

* a ``BeforeTool`` matcher for ``write_file|replace`` that runs
  ``scripts/hooks/gemini_coding_gate.py`` and blocks edits to tracked repo
  files until the ``coding`` skill has been invoked in the session;
* an ``AfterTool`` matcher for ``activate_skill`` that runs
  ``scripts/hooks/gemini_coding_gate_mark.py`` and writes the session marker
  when the ``coding`` skill is activated.

The merge is idempotent and preserves every other key in the settings file.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

GATE_MATCHER = "write_file|replace"
MARK_MATCHER = "activate_skill"
GATE_COMMAND = '"$GEMINI_PROJECT_DIR"/scripts/hooks/gemini_coding_gate.py'
MARK_COMMAND = '"$GEMINI_PROJECT_DIR"/scripts/hooks/gemini_coding_gate_mark.py'
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


def _append_entry(entries: list, matcher: str, command: str, name: str) -> None:
    entries.append(
        {
            "matcher": matcher,
            "hooks": [{"name": name, "type": "command", "command": command}],
        }
    )


def install(settings_path: Path) -> str:
    settings = _load_settings(settings_path)
    before_entries = _event_entries(settings, "BeforeTool")
    after_entries = _event_entries(settings, "AfterTool")

    before_present = _hook_already_present(before_entries, "gemini_coding_gate.py")
    after_present = _hook_already_present(after_entries, "gemini_coding_gate_mark.py")
    if before_present and after_present:
        return STATUS_ALREADY_PRESENT

    if not before_present:
        _append_entry(before_entries, GATE_MATCHER, GATE_COMMAND, "gemini-coding-gate")
    if not after_present:
        _append_entry(after_entries, MARK_MATCHER, MARK_COMMAND, "gemini-coding-gate-mark")

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(settings, indent=2) + "\n", encoding="utf-8"
    )
    return STATUS_UPDATED if (before_present or after_present) else STATUS_INSTALLED


def _default_target(root: Path) -> Path:
    return root / ".gemini" / "settings.json"


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
        help="Override the settings file path (defaults to ROOT/.gemini/settings.json).",
    )
    args = parser.parse_args(argv)

    target = Path(args.target) if args.target else _default_target(Path(args.root))
    status = install(target)
    print(status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
