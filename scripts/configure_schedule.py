#!/usr/bin/env python3
"""Create or update one track entry in the machine-local schedule file."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import sys
from pathlib import Path


TIME_RE = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
TRACK_RE = re.compile(r"^[A-Za-z0-9._-]+$")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DEFAULT_HEADER = """# Machine-local scheduler entries.
# Generated or updated by scripts/configure_schedule.py.
# Formats:
# daily HH:MM track <track-slug> [--delivery logseq|email|telegram]...
# weekly mon HH:MM track <track-slug> [--delivery logseq|email|telegram]...
# monthly 1 HH:MM track <track-slug> [--delivery logseq|email|telegram]...
"""


def default_root() -> Path:
    return Path(os.environ.get("JOB_AGENT_ROOT", Path(__file__).resolve().parents[1]))


def default_schedule_file(root: Path) -> Path:
    return Path(os.environ.get("JOB_AGENT_SCHEDULE_FILE", root / ".schedule.local"))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", required=True, help="Track slug to schedule")
    parser.add_argument("--cadence", required=True, choices=("daily", "weekly", "monthly"))
    parser.add_argument("--time", required=True, help="Local run time in HH:MM")
    parser.add_argument("--weekday", choices=WEEKDAYS, help="Weekly run day, for example mon")
    parser.add_argument("--month-day", type=int, help="Monthly run day, 1 through 31")
    parser.add_argument("--delivery", action="append", choices=("logseq", "email", "telegram"), default=[])
    parser.add_argument("--schedule-file", type=Path, help="Override .schedule.local path")
    return parser.parse_args(argv)


def validate_args(args: argparse.Namespace) -> None:
    if not TRACK_RE.fullmatch(args.track):
        raise ValueError("--track must contain only letters, digits, dot, underscore, or dash")
    if not TIME_RE.fullmatch(args.time):
        raise ValueError("--time must use HH:MM in 24-hour time")

    if args.cadence == "daily":
        if args.weekday or args.month_day is not None:
            raise ValueError("daily schedules must not include --weekday or --month-day")
    elif args.cadence == "weekly":
        if not args.weekday:
            raise ValueError("weekly schedules require --weekday")
        if args.month_day is not None:
            raise ValueError("weekly schedules must not include --month-day")
    elif args.cadence == "monthly":
        if args.weekday:
            raise ValueError("monthly schedules must not include --weekday")
        if args.month_day is None:
            raise ValueError("monthly schedules require --month-day")
        if not 1 <= args.month_day <= 31:
            raise ValueError("--month-day must be between 1 and 31")


def entry_for_args(args: argparse.Namespace) -> str:
    if args.cadence == "daily":
        parts = ["daily", args.time, "track", args.track]
    elif args.cadence == "weekly":
        parts = ["weekly", args.weekday, args.time, "track", args.track]
    else:
        parts = ["monthly", str(args.month_day), args.time, "track", args.track]

    for delivery_target in args.delivery:
        parts.extend(["--delivery", delivery_target])
    return " ".join(parts)


def track_for_schedule_line(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    try:
        fields = shlex.split(stripped)
    except ValueError:
        return None

    if len(fields) >= 4 and fields[0] == "daily" and fields[2] == "track":
        return fields[3]
    if len(fields) >= 5 and fields[0] in {"weekly", "monthly"} and fields[3] == "track":
        return fields[4]
    return None


def upsert_schedule(schedule_file: Path, track: str, entry: str) -> None:
    if schedule_file.exists():
        lines = schedule_file.read_text().splitlines()
    else:
        lines = DEFAULT_HEADER.rstrip("\n").splitlines()

    filtered = [line for line in lines if track_for_schedule_line(line) != track]
    while filtered and filtered[-1] == "":
        filtered.pop()
    if filtered:
        filtered.append("")
    filtered.append(entry)

    schedule_file.parent.mkdir(parents=True, exist_ok=True)
    schedule_file.write_text("\n".join(filtered) + "\n")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        validate_args(args)
    except ValueError as exc:
        print(f"configure_schedule.py: {exc}", file=sys.stderr)
        return 2

    root = default_root()
    schedule_file = args.schedule_file or default_schedule_file(root)
    entry = entry_for_args(args)
    upsert_schedule(schedule_file, args.track, entry)
    print(f"Wrote schedule entry to {schedule_file}: {entry}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
