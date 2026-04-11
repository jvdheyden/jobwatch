#!/usr/bin/env python3
"""Sync Claude Code skill mirrors from canonical project skills."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


HEADER_TEMPLATE = """<!-- GENERATED FILE: source of truth is .agents/skills/{skill}/SKILL.md -->
<!-- Do not edit here directly. After changing the source, resync mirrored skills. -->

"""


def default_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if Claude skill mirrors are missing, stale, or include stale skill dirs.",
    )
    return parser.parse_args(argv)


def canonical_skill_files(root: Path) -> dict[str, Path]:
    skills_dir = root / ".agents" / "skills"
    return {
        skill_dir.name: skill_dir / "SKILL.md"
        for skill_dir in sorted(skills_dir.iterdir())
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").is_file()
    }


def expected_mirror_text(skill: str, source_path: Path) -> str:
    return HEADER_TEMPLATE.format(skill=skill) + source_path.read_text(encoding="utf-8")


def mirror_path(root: Path, skill: str) -> Path:
    return root / ".claude" / "skills" / skill / "SKILL.md"


def stale_mirror_dirs(root: Path, canonical_skills: set[str]) -> list[Path]:
    mirrors_dir = root / ".claude" / "skills"
    if not mirrors_dir.exists():
        return []
    return [
        path
        for path in sorted(mirrors_dir.iterdir())
        if path.is_dir() and path.name not in canonical_skills
    ]


def check(root: Path) -> int:
    canonical_files = canonical_skill_files(root)
    errors: list[str] = []

    for skill, source_path in canonical_files.items():
        expected = expected_mirror_text(skill, source_path)
        destination = mirror_path(root, skill)
        if not destination.exists():
            errors.append(f"missing mirror: {destination.relative_to(root)}")
            continue
        actual = destination.read_text(encoding="utf-8")
        if actual != expected:
            errors.append(f"stale mirror: {destination.relative_to(root)}")

    for path in stale_mirror_dirs(root, set(canonical_files)):
        errors.append(f"stale mirror directory: {path.relative_to(root)}")

    if errors:
        print("Claude skill mirrors are out of sync:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        print("Run: ./.venv/bin/python scripts/sync_claude_skills.py", file=sys.stderr)
        return 1

    print("Claude skill mirrors are up to date.")
    return 0


def sync(root: Path) -> int:
    canonical_files = canonical_skill_files(root)
    for skill, source_path in canonical_files.items():
        destination = mirror_path(root, skill)
        destination.parent.mkdir(parents=True, exist_ok=True)
        expected = expected_mirror_text(skill, source_path)
        if not destination.exists() or destination.read_text(encoding="utf-8") != expected:
            destination.write_text(expected, encoding="utf-8")
            print(f"synced {destination.relative_to(root)}")
    return check(root)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = default_root()
    if args.check:
        return check(root)
    return sync(root)


if __name__ == "__main__":
    raise SystemExit(main())
