#!/usr/bin/env python3
"""Refresh a source-quality canary for a configured track source."""

from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from source_config import (
    SourceConfigError,
    load_source_state,
    load_sources_config,
    source_state_payload,
    slugify_source_id,
    write_json_atomic,
)


ROOT = Path(os.environ.get("JOB_AGENT_ROOT", Path(__file__).resolve().parents[1]))


def source_slug(source: str) -> str:
    return slugify_source_id(source)


def default_discovery_output(root: Path, track: str, source: str, today: str) -> Path:
    return root / "artifacts" / "evals" / track / source_slug(source) / f"{today}.canary_discovery.json"


def find_source(config: dict[str, Any], source_query: str) -> dict[str, Any]:
    wanted = source_query.lower()
    for source in config["sources"]:
        if source["name"].lower() == wanted or source["id"].lower() == wanted:
            return source
    raise SourceConfigError(f"source {source_query!r} not found in track {config['track']!r}")


def load_candidates(path: Path, source_name: str) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text())
    for source_payload in payload.get("sources", []):
        if str(source_payload.get("source", "")).lower() == source_name.lower():
            candidates = source_payload.get("candidates", [])
            if isinstance(candidates, list):
                return [item for item in candidates if isinstance(item, dict)]
    return []


def candidate_score(candidate: dict[str, Any], source_url: str) -> tuple[int, str, str]:
    title = str(candidate.get("title") or "").strip()
    url = str(candidate.get("url") or "").strip()
    lowered_url = url.lower()
    score = 0
    if title:
        score += 2
    if url and url != source_url:
        score += 2
    if any(marker in lowered_url for marker in ("/job", "jobs/", "jobid", "requisition", "posting", "apply")):
        score += 2
    if str(candidate.get("notes") or "").strip():
        score += 1
    return (-score, title.lower(), url)


def pick_canary(candidates: list[dict[str, Any]], source_url: str) -> dict[str, str] | None:
    usable = [
        candidate
        for candidate in candidates
        if str(candidate.get("title") or "").strip() and str(candidate.get("url") or "").strip()
    ]
    if not usable:
        return None
    selected = sorted(usable, key=lambda item: candidate_score(item, source_url))[0]
    return {
        "title": str(selected.get("title") or "").strip(),
        "url": str(selected.get("url") or "").strip(),
    }


def append_canary_history(integration: dict[str, Any], old_canary: Any, today: str, reason: str) -> None:
    if not isinstance(old_canary, dict):
        return
    title = str(old_canary.get("title") or "").strip()
    url = str(old_canary.get("url") or "").strip()
    if not title and not url:
        return
    history = integration.get("canary_history")
    if not isinstance(history, list):
        history = []
    archived = dict(old_canary)
    archived["replaced_at"] = today
    archived["reason"] = reason
    history.append(archived)
    integration["canary_history"] = history


def run_discovery(root: Path, track: str, source_name: str, today: str, output: Path) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(root / "scripts" / "discover_jobs.py"),
        "--track",
        track,
        "--source",
        source_name,
        "--today",
        today,
        "--output",
        str(output),
        "--pretty",
    ]
    env = os.environ.copy()
    env["JOB_AGENT_ROOT"] = str(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.run(command, text=True, capture_output=True, cwd=root, env=env)


def refresh_canary(
    *,
    root: Path,
    track: str,
    source_query: str,
    today: str,
    discovery_output: Path | None = None,
) -> tuple[bool, dict[str, Any]]:
    track_dir = root / "tracks" / track
    config = load_sources_config(track_dir / "sources.json", track)
    source = find_source(config, source_query)
    source_name = source["name"]
    source_id = source["id"]
    output = discovery_output or default_discovery_output(root, track, source_name, today)
    discovery = run_discovery(root, track, source_name, today, output)
    if discovery.returncode != 0:
        return False, {
            "status": "discovery_failed",
            "source": source_name,
            "output": str(output),
            "stderr": discovery.stderr.strip(),
        }

    candidates = load_candidates(output, source_name)
    selected = pick_canary(candidates, source["url"])
    state_path = track_dir / "source_state.json"
    state = load_source_state(state_path, track)
    source_ids = [item["id"] for item in config["sources"]]
    state_entry = dict(state.get(source_id) or {"last_checked": None})
    integration = dict(state_entry.get("integration") or {})
    old_canary = integration.get("canary")

    if not selected:
        append_canary_history(integration, old_canary, today, "refresh_found_no_replacement")
        integration["canary"] = {"status": "missing", "checked_at": today}
        integration["status"] = integration.get("status") or "pending"
        integration["next_action"] = "Find a current canary posting before the next source-quality check."
        state_entry["integration"] = integration
        state[source_id] = state_entry
        write_json_atomic(state_path, source_state_payload(track, source_ids, state))
        return False, {
            "status": "missing",
            "source": source_name,
            "output": str(output),
            "candidates_seen": len(candidates),
        }

    new_canary = {
        "status": "selected",
        "title": selected["title"],
        "url": selected["url"],
        "selected_at": today,
    }
    if old_canary != new_canary:
        append_canary_history(integration, old_canary, today, "refresh_replaced")
    integration["canary"] = new_canary
    integration["next_action"] = integration.get("next_action") or "Run source-quality evaluation with the refreshed canary."
    state_entry["integration"] = integration
    state[source_id] = state_entry
    write_json_atomic(state_path, source_state_payload(track, source_ids, state))
    return True, {
        "status": "updated",
        "source": source_name,
        "output": str(output),
        "canary": new_canary,
        "candidates_seen": len(candidates),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", required=True, help="Track slug")
    parser.add_argument("--source", required=True, help="Source name or source id")
    parser.add_argument("--today", default=date.today().isoformat(), help="Date stamp in YYYY-MM-DD format")
    parser.add_argument("--output", help="Optional discovery output path")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print result JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        ok, payload = refresh_canary(
            root=ROOT,
            track=args.track,
            source_query=args.source,
            today=args.today,
            discovery_output=Path(args.output) if args.output else None,
        )
    except (SourceConfigError, OSError, json.JSONDecodeError) as exc:
        print(f"update_source_canary.py: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=2 if args.pretty else None, ensure_ascii=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
