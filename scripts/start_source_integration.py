#!/usr/bin/env python3
"""Start a background source integration job for a track."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(os.environ.get("JOB_AGENT_ROOT", Path(__file__).resolve().parents[1]))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", required=True, help="Track directory name under tracks/")
    parser.add_argument("--source", help="Limit integration to a source name or id")
    parser.add_argument("--reviewer", default="auto", help="LLM reviewer mode")
    return parser


def resolve_repo_python() -> str:
    venv_python = ROOT / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def get_selected_source(track: str, source_query: str | None) -> str | None:
    command = [resolve_repo_python(), str(ROOT / "scripts" / "integrate_next_source.py"), "--track", track, "--dry-run"]
    if source_query:
        command.extend(["--source", source_query])
    
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    
    # Expected output: "Selected source: Name (id)"
    for line in result.stdout.splitlines():
        if line.startswith("Selected source:"):
            # Return the id in parentheses
            return line.split("(")[-1].rstrip(")")
    return None


def main() -> int:
    args = build_parser().parse_args()
    
    source_id = get_selected_source(args.track, args.source)
    if not source_id:
        print(f"No eligible source found for track {args.track}", file=sys.stderr)
        return 1
    
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_dir = ROOT / "logs" / "source-integration" / args.track
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{timestamp}-{source_id}.log"
    
    command = [
        resolve_repo_python(),
        str(ROOT / "scripts" / "integrate_next_source.py"),
        "--track", args.track,
        "--source", source_id,
        "--reviewer", args.reviewer,
    ]
    
    # Start detached
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
        "log_path": str(log_path),
    }
    
    jobs_log = ROOT / "logs" / "source-integration" / "jobs.jsonl"
    with open(jobs_log, "a") as f:
        f.write(json.dumps(job_record) + "\n")
    
    print(f"Started integration for {source_id} (pid: {process.pid})")
    print(f"Log: {log_path}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
