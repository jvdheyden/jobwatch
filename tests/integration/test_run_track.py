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
        root / "scripts" / "send_digest_email.py",
        """#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path


root = Path(os.environ["JOB_AGENT_ROOT"])
(root / "email.log").write_text("email " + " ".join(sys.argv[1:]) + "\\n")
raise SystemExit(int(os.environ.get("JOB_AGENT_FAKE_EMAIL_STATUS", "0")))
""",
    )
    _write_executable(
        root / "scripts" / "update_source_state.py",
        """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--track", required=True)
parser.add_argument("--date", required=True)
parser.add_argument("--artifact", required=True)
args = parser.parse_args()

root = Path(os.environ["JOB_AGENT_ROOT"])
artifact = json.loads(Path(args.artifact).read_text())
state_path = root / "tracks" / args.track / "source_state.json"
state_path.parent.mkdir(parents=True, exist_ok=True)
if state_path.exists():
    state = json.loads(state_path.read_text())
else:
    state = {"schema_version": 1, "track": args.track, "sources": {}}
for source in artifact.get("sources", []):
    if source.get("status") == "complete":
        state["sources"].setdefault(source["source_id"], {})["last_checked"] = args.date
state_path.write_text(json.dumps(state, indent=2) + "\\n")
(root / "source-state-updated.txt").write_text(args.date + "\\n")
""",
    )
    _write_executable(
        root / "scripts" / "render_digest.py",
        """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--track", required=True)
parser.add_argument("--date", required=True)
args = parser.parse_args()

root = Path(os.environ["JOB_AGENT_ROOT"])
digest_json = root / "artifacts" / "digests" / args.track / f"{args.date}.json"
output_md = root / "tracks" / args.track / "digests" / f"{args.date}.md"
output_md.parent.mkdir(parents=True, exist_ok=True)
output_md.write_text(f"# Rendered digest for {args.track} {args.date}\\n")
(root / "render-digest-ran.txt").write_text(f"{args.track} {args.date}\\n")
""",
    )
    _write_executable(
        root / "scripts" / "update_seen_jobs.py",
        """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--track", required=True)
parser.add_argument("--date", required=True)
args = parser.parse_args()

root = Path(os.environ["JOB_AGENT_ROOT"])
(root / "seen-jobs-ran.txt").write_text(f"{args.track} {args.date}\\n")
""",
    )
    _write_executable(
        root / "scripts" / "update_ranked_overview.py",
        """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--track", required=True)
args = parser.parse_args()

root = Path(os.environ["JOB_AGENT_ROOT"])
(root / "ranked-overview-ran.txt").write_text(f"{args.track}\\n")
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
mkdir -p "$ROOT/artifacts/digests/$TRACK"
printf '# Demo digest\\n' > "$ROOT/tracks/$TRACK/digests/$TODAY.md"
printf '{"schema_version":1,"track":"%s","date":"%s","runs":[]}\\n' "$TRACK" "$TODAY" > "$ROOT/artifacts/digests/$TRACK/$TODAY.json"
""",
    )
    _write_executable(
        root / "fake_claude.sh",
        """#!/bin/bash
set -euo pipefail
ROOT="${JOB_AGENT_ROOT:?missing JOB_AGENT_ROOT}"
TRACK="${JOB_AGENT_TRACK:?missing JOB_AGENT_TRACK}"
TODAY="${JOB_AGENT_TODAY:?missing JOB_AGENT_TODAY}"
printf '%s\\n' "$@" > "$ROOT/claude-args.txt"
pwd > "$ROOT/claude-cwd.txt"
cat > "$ROOT/claude-prompt.txt"
mkdir -p "$ROOT/tracks/$TRACK/digests"
mkdir -p "$ROOT/artifacts/digests/$TRACK"
printf '# Demo digest\\n' > "$ROOT/tracks/$TRACK/digests/$TODAY.md"
printf '{"schema_version":1,"track":"%s","date":"%s","runs":[]}\\n' "$TRACK" "$TODAY" > "$ROOT/artifacts/digests/$TRACK/$TODAY.json"
printf '{"type":"result","subtype":"success","result":"done"}\\n'
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


def _write_path_codex(root: Path) -> None:
    _write_executable(
        root / "bin" / "codex",
        """#!/bin/bash
set -euo pipefail
ROOT="${JOB_AGENT_ROOT:?missing JOB_AGENT_ROOT}"
exec "$ROOT/fake_codex.sh" "$@"
""",
    )


def _write_symlink_codex(root: Path, target: Path) -> None:
    path = root / "bin" / "codex"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        path.unlink()
    path.symlink_to(target)


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
                "source_id": "example_source",
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


def _slow_codex_exit_zero_on_term_script() -> str:
    return """#!/bin/bash
set -euo pipefail
trap 'exit 0' TERM
cat >/dev/null
echo "codex starting long run"
sleep 30
"""


def _idle_codex_script() -> str:
    return """#!/bin/bash
set -euo pipefail
trap 'exit 0' TERM
cat >/dev/null
echo "codex emitted one line"
sleep 30
"""


def test_run_track_uses_caffeinate_and_logs_phase_markers(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    _bootstrap_runner_root(tmp_job_agent_root, _successful_discovery_script())
    _write_fake_caffeinate(tmp_job_agent_root)

    env = os.environ | {
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_TODAY": "2030-01-15",
        "JOB_AGENT_BIN": str(tmp_job_agent_root / "fake_codex.sh"),
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
    assert "Source state update finished successfully" in log_text
    assert "Markdown digest rendered successfully" in log_text
    assert "Seen jobs updated successfully" in log_text
    assert "Ranked overview rebuilt successfully" in log_text
    assert (tmp_job_agent_root / "render-digest-ran.txt").read_text() == "demo 2030-01-15\n"
    assert (tmp_job_agent_root / "seen-jobs-ran.txt").read_text() == "demo 2030-01-15\n"
    assert (tmp_job_agent_root / "ranked-overview-ran.txt").read_text() == "demo\n"
    assert "No delivery targets requested; leaving local artifacts only" in log_text
    assert "Delivery phase started" not in log_text
    assert "Finished demo daily run" in log_text
    assert not (tmp_job_agent_root / "sync.log").exists()
    assert not (tmp_job_agent_root / "email.log").exists()
    assert (tmp_job_agent_root / "source-state-updated.txt").read_text() == "2030-01-15\n"

    caffeinate_args = (tmp_job_agent_root / "caffeinate-args.txt").read_text()
    assert "-dimsu" in caffeinate_args
    assert "--discovery-timeout-secs" in caffeinate_args
    assert "--delivery" not in caffeinate_args


def test_run_track_logseq_delivery_runs_sync_and_preserves_caffeinate_args(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    _bootstrap_runner_root(tmp_job_agent_root, _successful_discovery_script())
    _write_fake_caffeinate(tmp_job_agent_root)

    env = os.environ | {
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_TODAY": "2030-01-15",
        "JOB_AGENT_BIN": str(tmp_job_agent_root / "fake_codex.sh"),
        "PATH": f"{tmp_job_agent_root / 'bin'}:{os.environ['PATH']}",
    }

    result = run_cmd(
        "bash",
        str(repo_root / "scripts" / "run_track.sh"),
        "--track",
        "demo",
        "--delivery",
        "logseq",
        "--timeout-secs",
        "120",
        "--discovery-timeout-secs",
        "30",
        env=env,
        cwd=repo_root,
    )

    assert result.returncode == 0, result.stderr

    log_text = (tmp_job_agent_root / "logs" / "demo-2030-01-15.log").read_text()
    assert "Delivery phase started: logseq" in log_text
    assert "Delivery phase finished successfully: logseq" in log_text
    assert "No delivery targets requested" not in log_text
    assert (tmp_job_agent_root / "sync.log").read_text() == "sync --track demo\n"

    caffeinate_args = (tmp_job_agent_root / "caffeinate-args.txt").read_text()
    assert "--delivery" in caffeinate_args
    assert "logseq" in caffeinate_args


def test_run_track_email_delivery_invokes_email_sender(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    _bootstrap_runner_root(tmp_job_agent_root, _successful_discovery_script())
    _write_fake_caffeinate(tmp_job_agent_root)

    env = os.environ | {
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_TODAY": "2030-01-15",
        "JOB_AGENT_BIN": str(tmp_job_agent_root / "fake_codex.sh"),
        "PATH": f"{tmp_job_agent_root / 'bin'}:{os.environ['PATH']}",
    }

    result = run_cmd(
        "bash",
        str(repo_root / "scripts" / "run_track.sh"),
        "--track",
        "demo",
        "--delivery",
        "email",
        "--timeout-secs",
        "120",
        "--discovery-timeout-secs",
        "30",
        env=env,
        cwd=repo_root,
    )

    assert result.returncode == 0, result.stderr

    log_text = (tmp_job_agent_root / "logs" / "demo-2030-01-15.log").read_text()
    assert "Delivery phase started: email" in log_text
    assert "Delivery phase finished successfully: email" in log_text
    assert (tmp_job_agent_root / "email.log").read_text() == "email --track demo --date 2030-01-15\n"
    assert not (tmp_job_agent_root / "sync.log").exists()


def test_run_track_runs_multiple_deliveries_in_cli_order(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    _bootstrap_runner_root(tmp_job_agent_root, _successful_discovery_script())
    _write_fake_caffeinate(tmp_job_agent_root)

    env = os.environ | {
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_TODAY": "2030-01-15",
        "JOB_AGENT_BIN": str(tmp_job_agent_root / "fake_codex.sh"),
        "PATH": f"{tmp_job_agent_root / 'bin'}:{os.environ['PATH']}",
    }

    result = run_cmd(
        "bash",
        str(repo_root / "scripts" / "run_track.sh"),
        "--track",
        "demo",
        "--delivery",
        "email",
        "--delivery",
        "logseq",
        "--timeout-secs",
        "120",
        "--discovery-timeout-secs",
        "30",
        env=env,
        cwd=repo_root,
    )

    assert result.returncode == 0, result.stderr

    log_text = (tmp_job_agent_root / "logs" / "demo-2030-01-15.log").read_text()
    assert log_text.index("Delivery phase started: email") < log_text.index("Delivery phase started: logseq")
    assert (tmp_job_agent_root / "email.log").exists()
    assert (tmp_job_agent_root / "sync.log").exists()


def test_run_track_rejects_unknown_delivery(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    result = run_cmd(
        "bash",
        str(repo_root / "scripts" / "run_track.sh"),
        "--track",
        "demo",
        "--delivery",
        "slack",
        env=os.environ | {"JOB_AGENT_ROOT": str(tmp_job_agent_root)},
        cwd=repo_root,
    )

    assert result.returncode == 2
    assert "Usage:" in result.stderr


def test_run_track_fails_when_requested_delivery_fails(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    _bootstrap_runner_root(tmp_job_agent_root, _successful_discovery_script())
    _write_fake_caffeinate(tmp_job_agent_root)

    env = os.environ | {
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_TODAY": "2030-01-15",
        "JOB_AGENT_BIN": str(tmp_job_agent_root / "fake_codex.sh"),
        "JOB_AGENT_FAKE_EMAIL_STATUS": "17",
        "PATH": f"{tmp_job_agent_root / 'bin'}:{os.environ['PATH']}",
    }

    result = run_cmd(
        "bash",
        str(repo_root / "scripts" / "run_track.sh"),
        "--track",
        "demo",
        "--delivery",
        "email",
        "--timeout-secs",
        "120",
        "--discovery-timeout-secs",
        "30",
        env=env,
        cwd=repo_root,
    )

    assert result.returncode == 17, result.stderr

    log_text = (tmp_job_agent_root / "logs" / "demo-2030-01-15.log").read_text()
    assert "Codex phase finished successfully" in log_text
    assert "Delivery phase started: email" in log_text
    assert "Delivery phase failed: email status 17" in log_text
    assert "Finished demo daily run" not in log_text


def test_run_track_resolves_codex_from_path(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    _bootstrap_runner_root(tmp_job_agent_root, _successful_discovery_script())
    _write_fake_caffeinate(tmp_job_agent_root)
    _write_path_codex(tmp_job_agent_root)

    env = os.environ | {
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_TODAY": "2030-01-15",
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
    assert (tmp_job_agent_root / "codex-prompt.txt").exists()


def test_run_track_invokes_claude_provider_with_same_prompt(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    _bootstrap_runner_root(tmp_job_agent_root, _successful_discovery_script())
    _write_fake_caffeinate(tmp_job_agent_root)

    env = os.environ | {
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_TODAY": "2030-01-15",
        "JOB_AGENT_PROVIDER": "claude",
        "JOB_AGENT_BIN": str(tmp_job_agent_root / "fake_claude.sh"),
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
    args_text = (tmp_job_agent_root / "claude-args.txt").read_text()
    prompt_text = (tmp_job_agent_root / "claude-prompt.txt").read_text()
    log_text = (tmp_job_agent_root / "logs" / "demo-2030-01-15.log").read_text()

    assert "-p" in args_text
    assert "--output-format" in args_text
    assert "stream-json" in args_text
    assert "--verbose" in args_text
    assert "--allowedTools" in args_text
    assert (tmp_job_agent_root / "claude-cwd.txt").read_text().strip() == str(tmp_job_agent_root)
    assert "Run today's demo workflow from the repository root in mode: track_run." in prompt_text
    assert "A discovery artifact for today's scheduled run has already been written" in prompt_text
    assert "Claude phase started" in log_text
    assert "Claude phase finished successfully" in log_text


def test_run_track_prefers_repo_venv_python_for_discovery(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    _bootstrap_runner_root(tmp_job_agent_root, _successful_discovery_script())
    _write_fake_caffeinate(tmp_job_agent_root)
    _write_executable(
        tmp_job_agent_root / ".venv" / "bin" / "python",
        """#!/bin/bash
set -euo pipefail
ROOT="${JOB_AGENT_ROOT:?missing JOB_AGENT_ROOT}"
printf '%s\n' "$0 $*" > "$ROOT/python-invoked.txt"
exec python3 "$@"
""",
    )

    env = os.environ | {
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_TODAY": "2030-01-15",
        "JOB_AGENT_BIN": str(tmp_job_agent_root / "fake_codex.sh"),
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
    assert str(tmp_job_agent_root / ".venv" / "bin" / "python") in (tmp_job_agent_root / "python-invoked.txt").read_text().strip()
    log_text = (tmp_job_agent_root / "logs" / "demo-2030-01-15.log").read_text()
    assert f"Using discovery Python interpreter: {tmp_job_agent_root / '.venv' / 'bin' / 'python'}" in log_text


def test_run_track_canonicalizes_codex_bin_on_linux(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    _bootstrap_runner_root(tmp_job_agent_root, _successful_discovery_script())
    _write_fake_caffeinate(tmp_job_agent_root)
    canonical_codex = tmp_job_agent_root / "tools" / "codex" / "bin" / "codex.js"
    _write_executable(
        canonical_codex,
        """#!/bin/bash
set -euo pipefail
ROOT="${JOB_AGENT_ROOT:?missing JOB_AGENT_ROOT}"
printf '%s\\n' "$0" > "$ROOT/codex-invoked-as.txt"
exec "$ROOT/fake_codex.sh" "$@"
""",
    )
    symlink_codex = tmp_job_agent_root / "bin" / "codex"
    _write_symlink_codex(tmp_job_agent_root, canonical_codex)

    env = os.environ | {
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_TODAY": "2030-01-15",
        "JOB_AGENT_PLATFORM": "Linux",
        "JOB_AGENT_BIN": str(symlink_codex),
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
    assert (tmp_job_agent_root / "codex-invoked-as.txt").read_text().strip() == str(canonical_codex)


def test_run_track_keeps_codex_bin_path_on_non_linux(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    _bootstrap_runner_root(tmp_job_agent_root, _successful_discovery_script())
    _write_fake_caffeinate(tmp_job_agent_root)
    canonical_codex = tmp_job_agent_root / "tools" / "codex" / "bin" / "codex.js"
    _write_executable(
        canonical_codex,
        """#!/bin/bash
set -euo pipefail
ROOT="${JOB_AGENT_ROOT:?missing JOB_AGENT_ROOT}"
printf '%s\\n' "$0" > "$ROOT/codex-invoked-as.txt"
exec "$ROOT/fake_codex.sh" "$@"
""",
    )
    symlink_codex = tmp_job_agent_root / "bin" / "codex"
    _write_symlink_codex(tmp_job_agent_root, canonical_codex)

    env = os.environ | {
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_TODAY": "2030-01-15",
        "JOB_AGENT_PLATFORM": "Darwin",
        "JOB_AGENT_BIN": str(symlink_codex),
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
    assert (tmp_job_agent_root / "codex-invoked-as.txt").read_text().strip() == str(symlink_codex)


def test_run_track_times_out_discovery_and_continues_to_codex_fallback(
    tmp_job_agent_root: Path, repo_root: Path, run_cmd
) -> None:
    _bootstrap_runner_root(tmp_job_agent_root, _slow_discovery_script())
    _write_fake_caffeinate(tmp_job_agent_root)

    env = os.environ | {
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_TODAY": "2030-01-15",
        "JOB_AGENT_BIN": str(tmp_job_agent_root / "fake_codex.sh"),
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


def test_run_track_fails_when_codex_times_out_even_if_codex_exits_zero_on_term(
    tmp_job_agent_root: Path, repo_root: Path, run_cmd
) -> None:
    _bootstrap_runner_root(tmp_job_agent_root, _successful_discovery_script())
    _write_fake_caffeinate(tmp_job_agent_root)
    _write_executable(tmp_job_agent_root / "fake_codex.sh", _slow_codex_exit_zero_on_term_script())

    env = os.environ | {
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_TODAY": "2030-01-15",
        "JOB_AGENT_BIN": str(tmp_job_agent_root / "fake_codex.sh"),
        "AGENT_IDLE_TIMEOUT_SECS": "30",
        "PATH": f"{tmp_job_agent_root / 'bin'}:{os.environ['PATH']}",
    }

    result = run_cmd(
        "bash",
        str(repo_root / "scripts" / "run_track.sh"),
        "--track",
        "demo",
        "--timeout-secs",
        "1",
        "--discovery-timeout-secs",
        "30",
        env=env,
        cwd=repo_root,
    )

    assert result.returncode == 124, result.stderr

    log_text = (tmp_job_agent_root / "logs" / "demo-2030-01-15.log").read_text()
    assert "Codex exceeded 1s; terminating" in log_text
    assert "Codex phase timed out after 1s" in log_text
    assert "Codex phase finished successfully" not in log_text
    assert not (tmp_job_agent_root / "tracks" / "demo" / "digests" / "2030-01-15.md").exists()
    assert not (tmp_job_agent_root / "sync.log").exists()


def test_run_track_aborts_idle_codex_and_logs_heartbeat(tmp_job_agent_root: Path, repo_root: Path, run_cmd) -> None:
    _bootstrap_runner_root(tmp_job_agent_root, _successful_discovery_script())
    _write_fake_caffeinate(tmp_job_agent_root)
    _write_executable(tmp_job_agent_root / "fake_codex.sh", _idle_codex_script())

    env = os.environ | {
        "JOB_AGENT_ROOT": str(tmp_job_agent_root),
        "JOB_AGENT_TODAY": "2030-01-15",
        "JOB_AGENT_BIN": str(tmp_job_agent_root / "fake_codex.sh"),
        "AGENT_HEARTBEAT_SECS": "1",
        "AGENT_IDLE_TIMEOUT_SECS": "1",
        "PATH": f"{tmp_job_agent_root / 'bin'}:{os.environ['PATH']}",
    }

    result = run_cmd(
        "bash",
        str(repo_root / "scripts" / "run_track.sh"),
        "--track",
        "demo",
        "--timeout-secs",
        "30",
        "--discovery-timeout-secs",
        "30",
        env=env,
        cwd=repo_root,
    )

    assert result.returncode == 125, result.stderr

    log_text = (tmp_job_agent_root / "logs" / "demo-2030-01-15.log").read_text()
    assert "Codex still running after 1s" in log_text
    assert "Codex went idle after 1s without new output; terminating" in log_text
    assert "Codex phase went idle after 1s without new output" in log_text
    assert "Codex phase finished successfully" not in log_text
    assert not (tmp_job_agent_root / "tracks" / "demo" / "digests" / "2030-01-15.md").exists()
    assert not (tmp_job_agent_root / "sync.log").exists()
