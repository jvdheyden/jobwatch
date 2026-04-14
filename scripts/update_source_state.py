#!/usr/bin/env python3
"""Advance per-track source cadence state from a discovery artifact."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

from source_config import (
    SourceConfigError,
    load_source_state,
    load_sources_config,
    source_state_payload,
    write_json_atomic,
)


ROOT = Path(os.environ.get("JOB_AGENT_ROOT", Path(__file__).resolve().parents[1]))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", required=True, help="Track directory name under tracks/")
    parser.add_argument("--date", required=True, help="Run date in YYYY-MM-DD format")
    parser.add_argument(
        "--artifact",
        help="Discovery artifact path; defaults to artifacts/discovery/<track>/<date>.json",
    )
    return parser


def load_artifact(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise SourceConfigError(f"Missing discovery artifact: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SourceConfigError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SourceConfigError(f"{path} must contain a JSON object")
    return payload


def complete_source_ids(artifact: dict[str, Any], known_source_ids: set[str]) -> set[str]:
    raw_sources = artifact.get("sources")
    if not isinstance(raw_sources, list):
        raise SourceConfigError("Discovery artifact field sources must be a list")
    complete: set[str] = set()
    for index, raw_source in enumerate(raw_sources):
        if not isinstance(raw_source, dict):
            raise SourceConfigError(f"Discovery artifact source {index} must be an object")
        source_id = raw_source.get("source_id")
        if raw_source.get("status") != "complete":
            continue
        if not isinstance(source_id, str) or not source_id:
            raise SourceConfigError(f"Complete source record {index} is missing source_id")
        if source_id in known_source_ids:
            complete.add(source_id)
    return complete


def main() -> int:
    args = build_parser().parse_args()
    try:
        date.fromisoformat(args.date)
    except ValueError:
        print("update_source_state.py: --date must use YYYY-MM-DD", file=sys.stderr)
        return 2
    artifact_path = (
        Path(args.artifact)
        if args.artifact
        else ROOT / "artifacts" / "discovery" / args.track / f"{args.date}.json"
    )
    track_dir = ROOT / "tracks" / args.track
    state_path = track_dir / "source_state.json"

    try:
        config = load_sources_config(track_dir / "sources.json", args.track)
        state = load_source_state(state_path, args.track)
        source_ids = [source["id"] for source in config["sources"]]
        artifact = load_artifact(artifact_path)
        complete = complete_source_ids(artifact, set(source_ids))
    except SourceConfigError as exc:
        print(f"update_source_state.py: {exc}", file=sys.stderr)
        return 2

    for source_id in complete:
        state[source_id] = args.date

    write_json_atomic(state_path, source_state_payload(args.track, source_ids, state))
    print(f"Updated {len(complete)} source state entries in {state_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
