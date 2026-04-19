#!/usr/bin/env python3
"""Install a repo-local Claude Code SessionStart hook that exports CLAUDE_SESSION_ID.

The hook is merged into ``.claude/settings.local.json`` (per-user, per-checkout) so the
``coding`` skill can read ``$CLAUDE_SESSION_ID`` when populating plan ``agent_id``. The
merge is idempotent and preserves every other key in the settings file.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HOOK_COMMAND = (
    "python3 -c \"import sys,json,os; d=json.load(sys.stdin); "
    "open(os.environ['CLAUDE_ENV_FILE'],'a').write("
    "'export CLAUDE_SESSION_ID=' + d['session_id'] + '\\n')\""
)
HOOK_MARKER = "CLAUDE_SESSION_ID"
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


def _session_start_entries(settings: dict) -> list:
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise SystemExit("settings 'hooks' must be an object")
    entries = hooks.setdefault("SessionStart", [])
    if not isinstance(entries, list):
        raise SystemExit("settings 'hooks.SessionStart' must be a list")
    return entries


def _hook_already_present(entries: list) -> bool:
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
            if isinstance(command, str) and HOOK_MARKER in command:
                return True
    return False


def install(settings_path: Path) -> str:
    settings = _load_settings(settings_path)
    entries = _session_start_entries(settings)
    if _hook_already_present(entries):
        return STATUS_ALREADY_PRESENT
    entries.append(
        {"hooks": [{"type": "command", "command": HOOK_COMMAND}]}
    )
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(settings, indent=2) + "\n", encoding="utf-8"
    )
    return STATUS_INSTALLED


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
