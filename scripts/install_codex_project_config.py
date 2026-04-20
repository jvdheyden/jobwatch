#!/usr/bin/env python3
"""Install a repo-local Codex config that prefers the project virtualenv.

The config is merged into ``.codex/config.toml`` (per-user, per-checkout) so
Codex shell commands resolve ``python`` from ``./.venv/bin`` before the ambient
system PATH. The merge is idempotent and preserves unrelated config. Existing
unmanaged ``[shell_environment_policy]`` tables are treated as user-owned and
are not overwritten.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

BEGIN_MARKER = "# BEGIN jobwatch managed shell_environment_policy"
END_MARKER = "# END jobwatch managed shell_environment_policy"
STATUS_INSTALLED = "installed"
STATUS_ALREADY_PRESENT = "already-present"
STATUS_UPDATED = "updated"
STATUS_CONFLICT = "conflict"

_MANAGED_BLOCK_RE = re.compile(
    rf"(?ms)^{re.escape(BEGIN_MARKER)}\n.*?^{re.escape(END_MARKER)}\n?"
)
_SHELL_POLICY_TABLE_RE = re.compile(
    r"(?m)^\s*\[shell_environment_policy\]\s*(?:#.*)?$"
)


def _toml_quote(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\b", "\\b")
        .replace("\f", "\\f")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def build_path(root: Path, base_path: str | None = None) -> str:
    venv_bin = str((root / ".venv" / "bin").resolve(strict=False))
    entries = [venv_bin]
    seen = {venv_bin}
    for entry in (base_path if base_path is not None else os.environ.get("PATH", "")).split(
        os.pathsep
    ):
        if not entry or entry in seen:
            continue
        seen.add(entry)
        entries.append(entry)
    return os.pathsep.join(entries)


def desired_block(root: Path, base_path: str | None = None) -> str:
    path_value = build_path(root, base_path)
    return "\n".join(
        [
            BEGIN_MARKER,
            "[shell_environment_policy]",
            'inherit = "all"',
            f"set = {{ PATH = {_toml_quote(path_value)} }}",
            END_MARKER,
            "",
        ]
    )


def _has_unmanaged_shell_policy(text: str) -> bool:
    text_without_managed = _MANAGED_BLOCK_RE.sub("", text)
    return _SHELL_POLICY_TABLE_RE.search(text_without_managed) is not None


def _append_block(text: str, block: str) -> str:
    if not text:
        return block
    separator = "" if text.endswith("\n") else "\n"
    return f"{text}{separator}\n{block}"


def install(config_path: Path, root: Path, base_path: str | None = None) -> str:
    block = desired_block(root, base_path)

    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(block, encoding="utf-8")
        return STATUS_INSTALLED

    text = config_path.read_text(encoding="utf-8")
    if _has_unmanaged_shell_policy(text):
        return STATUS_CONFLICT

    existing_match = _MANAGED_BLOCK_RE.search(text)
    if existing_match:
        if existing_match.group(0) == block:
            return STATUS_ALREADY_PRESENT
        config_path.write_text(
            _MANAGED_BLOCK_RE.sub(block, text, count=1), encoding="utf-8"
        )
        return STATUS_UPDATED

    config_path.write_text(_append_block(text, block), encoding="utf-8")
    return STATUS_UPDATED if text.strip() else STATUS_INSTALLED


def _default_target(root: Path) -> Path:
    return root / ".codex" / "config.toml"


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
        help="Override the config file path (defaults to ROOT/.codex/config.toml).",
    )
    parser.add_argument(
        "--base-path",
        default=os.environ.get("PATH", ""),
        help="Base PATH to preserve after ROOT/.venv/bin.",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve(strict=False)
    target = Path(args.target) if args.target else _default_target(root)
    status = install(target, root, args.base_path)
    print(status)
    if status == STATUS_CONFLICT:
        print(
            "Existing unmanaged [shell_environment_policy] left unchanged. "
            "Desired managed block:",
            file=sys.stderr,
        )
        print(desired_block(root, args.base_path), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
