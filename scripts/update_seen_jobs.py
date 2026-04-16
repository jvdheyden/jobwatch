#!/usr/bin/env python3
"""Update per-track seen-jobs state from a structured digest artifact."""

from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata
import re
from datetime import date
from pathlib import Path
from typing import Any

from source_config import SourceConfigError, write_json_atomic


ROOT = Path(os.environ.get("JOB_AGENT_ROOT", Path(__file__).resolve().parents[1]))

NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return NORMALIZE_RE.sub(" ", ascii_text.lower()).strip()


def job_key(company: str, title: str, url: str) -> str:
    return f"{normalize_text(company)}|{normalize_text(title)}|{url.rstrip('/')}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", required=True, help="Track directory name under tracks/")
    parser.add_argument("--date", required=True, help="Digest date in YYYY-MM-DD format")
    parser.add_argument("--artifact", help="Digest artifact path; defaults to artifacts/digests/<track>/<date>.json")
    return parser


def load_seen_jobs(path: Path, track: str) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise SourceConfigError(f"Invalid seen_jobs file {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise SourceConfigError(f"{path} schema_version must be 1")
    payload_track = payload.get("track", "")
    if payload_track != track:
        raise SourceConfigError(f"{path} track must be {track!r}, got {payload_track!r}")
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        raise SourceConfigError(f"{path} jobs must be a list")
    return jobs


def seen_jobs_payload(track: str, jobs: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "track": track,
        "jobs": jobs,
    }


def extract_new_roles(artifact: dict[str, Any], run_date: str) -> list[dict[str, str]]:
    roles: list[dict[str, str]] = []
    for run in artifact.get("runs", []):
        for role in [*run.get("top_matches", []), *run.get("other_new_roles", [])]:
            roles.append({
                "date_seen": run_date,
                "company": role.get("company", "unknown"),
                "title": role.get("title", "unknown"),
                "location": role.get("location") or "unknown",
                "url": role.get("listing_url", ""),
            })
    return roles


def main() -> int:
    args = build_parser().parse_args()
    try:
        date.fromisoformat(args.date)
    except ValueError:
        print("update_seen_jobs.py: --date must use YYYY-MM-DD", file=sys.stderr)
        return 2

    artifact_path = (
        Path(args.artifact)
        if args.artifact
        else ROOT / "artifacts" / "digests" / args.track / f"{args.date}.json"
    )
    seen_path = ROOT / "tracks" / args.track / "seen_jobs.json"

    if not artifact_path.exists():
        print(f"No digest artifact at {artifact_path}; skipping seen-jobs update")
        return 0

    try:
        artifact = json.loads(artifact_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        print(f"update_seen_jobs.py: {exc}", file=sys.stderr)
        return 2

    try:
        existing = load_seen_jobs(seen_path, args.track)
    except SourceConfigError as exc:
        print(f"update_seen_jobs.py: {exc}", file=sys.stderr)
        return 2

    existing_keys = {job_key(j["company"], j["title"], j["url"]) for j in existing}
    new_roles = extract_new_roles(artifact, args.date)
    added = 0
    for role in new_roles:
        key = job_key(role["company"], role["title"], role["url"])
        if key not in existing_keys:
            existing.append(role)
            existing_keys.add(key)
            added += 1

    write_json_atomic(seen_path, seen_jobs_payload(args.track, existing))
    print(f"Added {added} roles to {seen_path} ({len(existing)} total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
