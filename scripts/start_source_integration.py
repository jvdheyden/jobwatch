#!/usr/bin/env python3
"""Start a background source integration job for a track."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(os.environ.get("JOB_AGENT_ROOT", Path(__file__).resolve().parents[1]))

sys.path.insert(0, str(ROOT / "scripts"))
try:
    from integrate_next_source import PENDING_STATUSES, _integration_state, _priority
    from source_config import load_source_state, load_sources_config
except ImportError:
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", required=True, help="Track directory name under tracks/")
    parser.add_argument("--source", help="Limit integration to a source name or id")
    parser.add_argument("--limit", type=int, help="Start at most N eligible queued sources")
    parser.add_argument("--all-eligible", action="store_true", help="Start all currently eligible queued sources")
    parser.add_argument("--today", help="Pass through date to integrate_next_source.py")
    parser.add_argument("--timeout-seconds", type=int, help="Pass through timeout to integrate_next_source.py")
    parser.add_argument("--max-attempts", type=int, help="Pass through max attempts to integrate_next_source.py")
    parser.add_argument("--reviewer", default="auto", help="LLM reviewer mode")
    return parser


def resolve_repo_python() -> str:
    venv_python = ROOT / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def get_eligible_sources(
    track: str,
    source_query: str | None,
    limit: int | None,
    all_eligible: bool,
    today: str,
) -> list[str]:
    try:
        config = load_sources_config(ROOT / "tracks" / track / "sources.json", track)
        state = load_source_state(ROOT / "tracks" / track / "source_state.json", track)
    except Exception as exc:
        print(f"Failed to load config/state for {track}: {exc}", file=sys.stderr)
        return []

    requested = source_query.lower() if source_query else None
    candidates = []
    
    for source in config.get("sources", []):
        state_entry = state.setdefault(source["id"], {"last_checked": None})
        integration = _integration_state(state_entry)
        
        if requested and requested not in {source["id"].lower(), source["name"].lower()}:
            continue
            
        status = str(integration.get("status", "") or "")
        if not requested and status not in PENDING_STATUSES:
            continue
            
        if requested and not status:
            status = "pending"
            
        if integration.get("last_attempted") == today:
            continue
            
        candidates.append((_priority(integration.get("priority")), source["name"], source["id"]))

    if not candidates:
        return []
        
    candidates.sort(key=lambda item: (-item[0], item[1].lower()))
    
    selected_ids = [c[2] for c in candidates]
    
    if source_query and not all_eligible and limit is None:
        return selected_ids[:1]
        
    if not all_eligible and limit is not None:
        return selected_ids[:limit]
        
    if not all_eligible and limit is None and not source_query:
        # Default behavior if nothing specified? The prompt says:
        # "Existing --source behavior must remain."
        # If --source is given without --limit or --all-eligible, it's 1.
        # If nothing is given, it used to be 1. Let's keep it 1.
        return selected_ids[:1]
        
    return selected_ids


def main() -> int:
    args = build_parser().parse_args()
    today_str = args.today or date.today().isoformat()
    
    source_ids = get_eligible_sources(args.track, args.source, args.limit, args.all_eligible, today_str)
    
    if not source_ids:
        print("No eligible source found")
        return 0
    
    print("Started source integration jobs:")
    print(f"{'source_id':<20} {'pid':<10} {'log'}")
    
    jobs_log = ROOT / "logs" / "source-integration" / "jobs.jsonl"
    jobs_log.parent.mkdir(parents=True, exist_ok=True)
    
    python_bin = resolve_repo_python()
    script_path = str(ROOT / "scripts" / "integrate_next_source.py")
    
    for source_id in source_ids:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_dir = ROOT / "logs" / "source-integration" / args.track
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{timestamp}-{source_id}.log"
        
        command = [
            python_bin,
            script_path,
            "--track", args.track,
            "--source", source_id,
            "--reviewer", args.reviewer,
        ]
        if args.today:
            command.extend(["--today", args.today])
        if args.timeout_seconds:
            command.extend(["--timeout-seconds", str(args.timeout_seconds)])
        if args.max_attempts:
            command.extend(["--max-attempts", str(args.max_attempts)])
        
        with open(log_path, "w") as log_file:
            process = subprocess.Popen(
                command,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=ROOT,
                start_new_session=True,
            )
        
        job_record = {
            "pid": process.pid,
            "track": args.track,
            "source_id": source_id,
            "command": command,
            "status": "started",
            "start_time": datetime.now().isoformat(),
            "log_path": str(log_path.relative_to(ROOT)),
        }
        
        with open(jobs_log, "a") as f:
            f.write(json.dumps(job_record) + "\n")
            
        print(f"{source_id:<20} {process.pid:<10} {log_path.relative_to(ROOT)}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
