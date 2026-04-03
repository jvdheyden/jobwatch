from __future__ import annotations

import os
from pathlib import Path


def _write_executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o755)


def _bootstrap_runner_root(root: Path, discover_script: str) -> None:
    (root / "tracks" / "demo" / "digests").mkdir(parents=True, exist_ok=True)
    (root / "artifacts" / "discovery" / "demo").mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)

    _write_executable(root / "scripts" / "discover_jobs.py", discover_script)
    _write_executable(
        root / "scripts" / "sync_to_logseq.sh",
        """#!/bin/bash
set -euo pipefail
ROOT="${JOB_AGENT_ROOT:?missing JOB_AGENT_ROOT}"
echo "sync $*" >> "$ROOT/sync.log"
""",
    )
    _write_executable(
        root / "fake_codex.sh",
        """#!/bin/bash
set -euo pipefail
ROOT="${JOB_AGENT_ROOT:?missing JOB_AGENT_ROOT}"
TRACK="${JOB_AGENT_TRACK:?missing JOB_AGENT_TRACK}"
TODAY="${JOB_AGENT_TODAY:?missing JOB_AGENT_TODAY}"
cat > "$ROOT/codex-prompt.txt"
mkdir -p "$ROOT/tracks/$TRACK/digests"
printf '# Demo digest\\n' > "$ROOT/tracks/$TRACK/digests/$TODAY.md"
""",
    )


def _write_fake_caffeinate(root: Path) -> None:
    _write_executable(
        root / "bin" / "caffeinate",
        """#!/bin/bash
set -euo pipefail
ROOT="${JOB_AGENT_ROOT:?missing JOB_AGENT_ROOT}"
printf '%s\\n' "$@" > "$ROOT/caffeinate-args.txt"
while [[ $# -gt 0 ]]; do
  if [[ "$1" == -* ]]; then
    shift
    continue
  fi
  break
done
exec "$@"
""",
    )


def _successful_discovery_script() -> str:
    return """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--track", required=True)
parser.add_argument("--today", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--latest-output")
parser.add_argument("--due-only", action="store_true")
parser.add_argument("--pretty", action="store_true")
parser.add_argument("--progress", action="store_true")
args = parser.parse_args()

if args.progress:
    print("[progress] Discovering source 1/1: Example Source (mode=html)", file=sys.stderr, flush=True)

payload = {
    "schema_version": 1,
    "track": args.track,
    "today": args.today,
    "generated_at": f"{args.today}T08:00:00Z",
    "mode": "discover",
    "sources": [
        {
            "source": "Example Source",
            "source_url": "https://example.com/jobs",
            "discovery_mode": "html",
            "cadence_group": "every_run",
            "last_checked": None,
            "due_today": True,
            "status": "complete",
            "listing_pages_scanned": 1,
            "search_terms_tried": ["cryptography"],
            "result_pages_scanned": "local_filter=1",
            "direct_job_pages_opened": 0,
            "enumerated_jobs": 1,
            "matched_jobs": 1,
            "limitations": [],
            "candidates": [
                {
                    "employer": "Example Co",
                    "title": "Cryptography Engineer",
                    "url": "https://example.com/jobs/1",
                    "source_url": "https://example.com/jobs",
                    "alternate_url": "",
                    "location": "Remote",
                    "remote": "remote",
                    "matched_terms": ["cryptography"],
                    "notes": "fixture",
                }
            ],
        }
    ],
}

output_path = Path(args.output)
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(json.dumps(payload, indent=2 if args.pretty else None) + "\\n")
if args.latest_output:
    Path(args.latest_output).write_text(json.dumps(payload, indent=2 if args.pretty else None) + "\\n")

if args.progress:
    print(
        "[progress] Completed source 1/1: Example Source (status=complete, matched=1, candidates=1)",
        file=sys.stderr,
        flush=True,
    )
"""


def _slow_discovery_script() -> str:
    return """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import signal
import sys
import time


parser = argparse.ArgumentParser()
parser.add_argument("--track", required=True)
parser.add_argument("--today", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--latest-output")
parser.add_argument("--due-only", action="store_true")
parser.add_argument("--pretty", action="store_true")
parser.add_argument("--progress", action="store_true")
args = parser.parse_args()

def _handle_term(_signum, _frame):
    raise SystemExit(124)


signal.signal(signal.SIGTERM, _handle_term)
if args.progress:
    print("[progress] Discovering source 1/1: Slow Source (mode=html)", file=sys.stderr, flush=True)
time.sleep(5)
"""


def test_run_track_uses_caffeinate_and_logs_phase_markers(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    _bootstrap_runner_root(tmp_job_agent_root, _successful_discovery_script())
    _write_fake_caffeinate(tmp_job_agent_root)

    env = os.environ | {
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_TODAY": "2030-01-15",
        "CODEX_BIN": str(tmp_job_agent_root / "fake_codex.sh"),
        "PATH": f"{tmp_job_agent_root / 'bin'}:{os.environ['PATH']}",
    }

    result = run_cmd(
        "bash",
        str(repo_root / "scripts" / "run_track.sh"),
        "--track",
        "demo",
        "--timeout-secs",
        "120",
        "--discovery-timeout-secs",
        "30",
        env=env,
        cwd=repo_root,
    )

    assert result.returncode == 0, result.stderr

    log_text = (tmp_job_agent_root / "logs" / "demo-2030-01-15.log").read_text()
    assert "Re-executing demo run under caffeinate" in log_text
    assert "Wake prevention active via caffeinate" in log_text
    assert "Discovery phase started" in log_text
    assert "Discovery phase finished successfully" in log_text
    assert "Wrote discovery artifact" in log_text
    assert "Codex phase started" in log_text
    assert "Codex phase finished successfully" in log_text
    assert "Sync phase started" in log_text
    assert "Sync phase finished successfully" in log_text
    assert "Finished demo daily run" in log_text

    caffeinate_args = (tmp_job_agent_root / "caffeinate-args.txt").read_text()
    assert "-dimsu" in caffeinate_args
    assert "--discovery-timeout-secs" in caffeinate_args


def test_run_track_times_out_discovery_and_continues_to_codex_fallback(
    tmp_job_agent_root: Path, repo_root: Path, run_cmd
) -> None:
    _bootstrap_runner_root(tmp_job_agent_root, _slow_discovery_script())
    _write_fake_caffeinate(tmp_job_agent_root)

    env = os.environ | {
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_TODAY": "2030-01-15",
        "CODEX_BIN": str(tmp_job_agent_root / "fake_codex.sh"),
        "PATH": f"{tmp_job_agent_root / 'bin'}:{os.environ['PATH']}",
    }

    result = run_cmd(
        "bash",
        str(repo_root / "scripts" / "run_track.sh"),
        "--track",
        "demo",
        "--timeout-secs",
        "120",
        "--discovery-timeout-secs",
        "1",
        env=env,
        cwd=repo_root,
    )

    assert result.returncode == 0, result.stderr

    log_text = (tmp_job_agent_root / "logs" / "demo-2030-01-15.log").read_text()
    prompt_text = (tmp_job_agent_root / "codex-prompt.txt").read_text()

    assert "Discovery exceeded 1s; terminating" in log_text
    assert "Discovery phase timed out after 1s; Codex will fall back to live discovery as needed" in log_text
    assert "Codex phase started" in log_text
    assert "Codex phase finished successfully" in log_text
    assert "No fresh discovery artifact is available for today's scheduled run because artifact generation timed out." in prompt_text
    assert "A discovery artifact for today's scheduled run has already been written" not in prompt_text
    assert not (tmp_job_agent_root / "artifacts" / "discovery" / "demo" / "2030-01-15.json").exists()
