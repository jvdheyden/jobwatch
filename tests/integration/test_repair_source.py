from __future__ import annotations

import json
import os
import repair_source
import subprocess
import time
from pathlib import Path


def write_stub_discover_script(root: Path) -> None:
    scripts_dir = root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    script_path = scripts_dir / "discover_jobs.py"
    script_path.write_text(
        """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--track", required=True)
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--today", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--timeout-seconds")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    fixed_marker = root / "fixed.marker"
    if fixed_marker.exists():
        title = "Privacy Engineer"
        url = "https://jobs.example.com/jobs/999"
    else:
        title = "Security Engineer"
        url = "https://jobs.example.com/jobs/123"

    payload = {
        "schema_version": 1,
        "track": args.track,
        "today": args.today,
        "sources": [
            {
                "source": args.source[0] if args.source else "Example Source",
                "source_url": "https://jobs.example.com/search",
                "discovery_mode": "html",
                "cadence_group": "every_run",
                "last_checked": None,
                "due_today": True,
                "status": "complete",
                "listing_pages_scanned": 1,
                "search_terms_tried": ["security"],
                "result_pages_scanned": "cards=1",
                "direct_job_pages_opened": 0,
                "enumerated_jobs": 1,
                "matched_jobs": 1,
                "limitations": [],
                "candidates": [
                    {
                        "employer": "Example Source",
                        "title": title,
                        "url": url,
                        "source_url": "https://jobs.example.com/search",
                        "location": "Berlin",
                        "remote": "unknown",
                        "matched_terms": ["security"],
                        "notes": "Tasks: Build secure systems for public-sector services. Profile: security engineering background.",
                    }
                ],
            }
        ],
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""
    )


def write_example_artifact(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "track": "public_service",
                "today": "2026-04-02",
                "sources": [
                    {
                        "source": "Example Source",
                        "source_url": "https://jobs.example.com/search",
                        "discovery_mode": "html",
                        "cadence_group": "every_run",
                        "last_checked": None,
                        "due_today": True,
                        "status": "complete",
                        "listing_pages_scanned": 1,
                        "search_terms_tried": ["security"],
                        "result_pages_scanned": "cards=1",
                        "direct_job_pages_opened": 0,
                        "enumerated_jobs": 1,
                        "matched_jobs": 1,
                        "limitations": [],
                        "candidates": [
                            {
                                "employer": "Example Source",
                                "title": "Security Engineer",
                                "url": "https://jobs.example.com/jobs/123",
                                "source_url": "https://jobs.example.com/search",
                                "location": "Berlin",
                                "remote": "unknown",
                                "matched_terms": ["security"],
                                "notes": "Tasks: Build secure systems for public-sector services. Profile: security engineering background.",
                            }
                        ],
                    }
                ],
            },
            indent=2,
        )
        + "\n"
    )


def test_repair_source_default_timeout_seconds_is_120():
    assert repair_source.DEFAULT_REVIEW_TIMEOUT_SECONDS == 120


def test_repair_source_runs_coder_and_reaches_pass(tmp_job_agent_root: Path, run_cmd, repo_root: Path):
    write_stub_discover_script(tmp_job_agent_root)
    artifact_path = tmp_job_agent_root / "artifacts" / "discovery" / "public_service" / "2026-04-02.json"
    write_example_artifact(artifact_path)

    coder_script = tmp_job_agent_root / "fake_repair_coder.sh"
    coder_script.write_text(
        """#!/bin/bash
set -euo pipefail
cat >"$JOB_AGENT_ROOT/prompt.txt"
echo '{"type":"status","message":"touching fix marker"}'
touch "$JOB_AGENT_ROOT/fixed.marker"
"""
    )
    coder_script.chmod(0o755)

    eval_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.json"
    summary_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.repair_loop.json"
    env = os.environ.copy()
    env["JOB_AGENT_ROOT"] = str(tmp_job_agent_root)

    result = run_cmd(
        "python3",
        str(repo_root / "scripts" / "repair_source.py"),
        "--track",
        "public_service",
        "--source",
        "Example Source",
        "--today",
        "2026-04-02",
        "--artifact-path",
        str(artifact_path),
        "--canary-title",
        "Privacy Engineer",
        "--canary-url",
        "https://jobs.example.com/jobs/999",
        "--reviewer",
        "off",
        "--coder-bin",
        str(coder_script),
        "--eval-output",
        str(eval_output),
        "--summary-output",
        str(summary_output),
        env=env,
        cwd=tmp_job_agent_root,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(summary_output.read_text())
    prompt_text = (tmp_job_agent_root / "prompt.txt").read_text()
    assert summary["final_status"] == "pass"
    assert summary["repair_attempts_used"] == 1
    assert len(summary["attempts"]) == 2
    assert summary["attempts"][0]["eval_final_status"] == "repair_needed"
    assert summary["attempts"][0]["coding_invoked"] is True
    assert summary["attempts"][0]["rediscovery_invoked"] is True
    assert summary["attempts"][0]["coding_last_event_type"] == "status"
    assert "touching fix marker" in summary["attempts"][0]["coding_last_event_excerpt"]
    assert summary["attempts"][1]["eval_final_status"] == "pass"
    assert summary["active_artifact_path"].endswith("2026-04-02.discovery.json")
    assert json.loads(eval_output.read_text())["final_status"] == "pass"
    assert "make the functional fix in scripts/discover_jobs.py" in prompt_text
    assert "Start by inspecting the source-specific parser path in scripts/discover_jobs.py and any existing source-specific tests before broader investigation." in prompt_text
    assert "look first for source-specific functions or helpers named after Example Source" in prompt_text
    assert "If no source-specific path exists yet, implement the minimal source-specific parser or strategy needed in scripts/discover_jobs.py" in prompt_text
    assert "Your first concrete step must be either updating/adding a focused test for the source path or patching the source-specific parser/helper in scripts/discover_jobs.py." in prompt_text
    assert "Do not use external web search or raw HTTP/network probes unless local code, existing tests, and the eval artifact are insufficient to design the first patch." in prompt_text
    assert "If the failing check is detail_depth, prefer source-specific detail-page enrichment for already-kept candidates and append substantive role detail to existing extracted notes or fields." in prompt_text
    assert "Do not run bash scripts/test.sh or scripts/test_track_workflow.sh as part of this repair." in prompt_text
    assert "Do not debug unrelated e2e, workflow, or repo-wide test failures after the focused source validation succeeds." in prompt_text
    assert "Stop as soon as the focused validation command completes; do not continue into broader verification after that point." in prompt_text
    assert "The orchestrator owns rediscovery and final eval." in prompt_text
    assert "Use the repo-local virtualenv for Python tests and helper scripts" in prompt_text
    assert "./.venv/bin/python scripts/discover_jobs.py --track public_service --source \"Example Source\" --today 2026-04-02 --pretty" in prompt_text


def test_repair_source_stops_at_retry_limit(tmp_job_agent_root: Path, run_cmd, repo_root: Path):
    write_stub_discover_script(tmp_job_agent_root)
    artifact_path = tmp_job_agent_root / "artifacts" / "discovery" / "public_service" / "2026-04-02.json"
    write_example_artifact(artifact_path)

    coder_script = tmp_job_agent_root / "fake_noop_coder.sh"
    coder_script.write_text(
        """#!/bin/bash
set -euo pipefail
cat >/dev/null
"""
    )
    coder_script.chmod(0o755)

    eval_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.json"
    summary_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.repair_loop.json"
    env = os.environ.copy()
    env["JOB_AGENT_ROOT"] = str(tmp_job_agent_root)

    result = run_cmd(
        "python3",
        str(repo_root / "scripts" / "repair_source.py"),
        "--track",
        "public_service",
        "--source",
        "Example Source",
        "--today",
        "2026-04-02",
        "--artifact-path",
        str(artifact_path),
        "--canary-title",
        "Privacy Engineer",
        "--canary-url",
        "https://jobs.example.com/jobs/999",
        "--reviewer",
        "off",
        "--coder-bin",
        str(coder_script),
        "--max-attempts",
        "1",
        "--eval-output",
        str(eval_output),
        "--summary-output",
        str(summary_output),
        env=env,
        cwd=tmp_job_agent_root,
    )

    assert result.returncode == 1
    summary = json.loads(summary_output.read_text())
    assert summary["final_status"] == "retry_limit"
    assert summary["repair_attempts_used"] == 1
    assert len(summary["attempts"]) == 2
    assert summary["attempts"][0]["coding_invoked"] is True
    assert summary["attempts"][0]["rediscovery_invoked"] is True
    assert summary["attempts"][1]["eval_final_status"] == "repair_needed"


def test_repair_source_retries_blocked_coder_with_postmortem_context(tmp_job_agent_root: Path, run_cmd, repo_root: Path):
    write_stub_discover_script(tmp_job_agent_root)
    artifact_path = tmp_job_agent_root / "artifacts" / "discovery" / "public_service" / "2026-04-02.json"
    write_example_artifact(artifact_path)

    coder_script = tmp_job_agent_root / "fake_retrying_coder.sh"
    coder_script.write_text(
        """#!/bin/bash
set -euo pipefail
count_file="$JOB_AGENT_ROOT/coder-count.txt"
count=0
if [ -f "$count_file" ]; then
  count="$(cat "$count_file")"
fi
count=$((count + 1))
echo "$count" >"$count_file"
cat >"$JOB_AGENT_ROOT/prompt-$count.txt"
if [ "$count" -eq 1 ]; then
  echo '{"type":"status","message":"first attempt will idle"}'
  trap 'exit 0' TERM
  sleep 30
else
  echo '{"type":"status","message":"second attempt uses postmortem"}'
  touch "$JOB_AGENT_ROOT/fixed.marker"
fi
"""
    )
    coder_script.chmod(0o755)

    eval_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.json"
    summary_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.repair_loop.json"
    env = os.environ.copy()
    env["JOB_AGENT_ROOT"] = str(tmp_job_agent_root)

    result = run_cmd(
        "python3",
        str(repo_root / "scripts" / "repair_source.py"),
        "--track",
        "public_service",
        "--source",
        "Example Source",
        "--today",
        "2026-04-02",
        "--artifact-path",
        str(artifact_path),
        "--canary-title",
        "Privacy Engineer",
        "--canary-url",
        "https://jobs.example.com/jobs/999",
        "--reviewer",
        "off",
        "--coder-bin",
        str(coder_script),
        "--idle-timeout-seconds",
        "1",
        "--repair-timeout-seconds",
        "10",
        "--max-attempts",
        "2",
        "--eval-output",
        str(eval_output),
        "--summary-output",
        str(summary_output),
        env=env,
        cwd=tmp_job_agent_root,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(summary_output.read_text())
    first_prompt = (tmp_job_agent_root / "prompt-1.txt").read_text()
    second_prompt = (tmp_job_agent_root / "prompt-2.txt").read_text()
    first_postmortem_path = Path(summary["attempts"][0]["coding_postmortem_path"])
    first_postmortem = json.loads(first_postmortem_path.read_text())

    assert summary["final_status"] == "pass"
    assert summary["repair_attempts_used"] == 2
    assert len(summary["attempts"]) == 3
    assert summary["attempts"][0]["coding_error"] == "repair run went idle after 1s without new output"
    assert first_postmortem_path.exists()
    assert first_postmortem["failure_class"] == "idle"
    assert "coder-count.txt" in first_postmortem["files_touched"]
    assert "prompt-1.txt" in first_postmortem["files_touched"]
    assert first_postmortem["tests_touched_or_run"] == []
    assert first_postmortem["runtime_error_signatures"] == []
    assert first_postmortem["likely_next_step"] == (
        "Resume in scripts/discover_jobs.py and make a focused patch or focused test update before more investigation."
    )
    assert "Prior blocked attempt context:" not in first_prompt
    assert "Prior blocked attempt context:" in second_prompt
    assert "repair run went idle after 1s without new output" in second_prompt
    assert summary["attempts"][1]["coding_invoked"] is True
    assert summary["attempts"][1]["rediscovery_invoked"] is True
    assert summary["attempts"][2]["eval_final_status"] == "pass"


def test_repair_source_proceeds_to_rediscovery_after_idle_with_success_signals(tmp_job_agent_root: Path, run_cmd, repo_root: Path):
    write_stub_discover_script(tmp_job_agent_root)
    artifact_path = tmp_job_agent_root / "artifacts" / "discovery" / "public_service" / "2026-04-02.json"
    write_example_artifact(artifact_path)

    coder_script = tmp_job_agent_root / "fake_success_then_idle_coder.sh"
    coder_script.write_text(
        """#!/bin/bash
set -euo pipefail
cat >/dev/null
touch "$JOB_AGENT_ROOT/fixed.marker"
touch "$JOB_AGENT_ROOT/scripts/discover_jobs.py"
echo '{"type":"item.completed","item":{"id":"item_1","type":"command_execution","command":"/bin/zsh -lc '\''python3 scripts/discover_jobs.py --track public_service --source \"Example Source\" --today 2026-04-02 --pretty'\''","aggregated_output":"ok","exit_code":0,"status":"completed"}}'
trap 'exit 0' TERM
sleep 30
"""
    )
    coder_script.chmod(0o755)

    eval_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.json"
    summary_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.repair_loop.json"
    env = os.environ.copy()
    env["JOB_AGENT_ROOT"] = str(tmp_job_agent_root)

    result = run_cmd(
        "python3",
        str(repo_root / "scripts" / "repair_source.py"),
        "--track",
        "public_service",
        "--source",
        "Example Source",
        "--today",
        "2026-04-02",
        "--artifact-path",
        str(artifact_path),
        "--canary-title",
        "Privacy Engineer",
        "--canary-url",
        "https://jobs.example.com/jobs/999",
        "--reviewer",
        "off",
        "--coder-bin",
        str(coder_script),
        "--idle-timeout-seconds",
        "1",
        "--repair-timeout-seconds",
        "10",
        "--max-attempts",
        "1",
        "--eval-output",
        str(eval_output),
        "--summary-output",
        str(summary_output),
        env=env,
        cwd=tmp_job_agent_root,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(summary_output.read_text())
    assert summary["final_status"] == "pass"
    assert summary["repair_attempts_used"] == 1
    assert summary["attempts"][0]["coding_completion_state"] == "ready_for_rediscovery_idle"
    assert summary["attempts"][0]["rediscovery_invoked"] is True
    assert summary["attempts"][0]["coding_success_signals"]["ready_for_rediscovery"] is True
    assert summary["attempts"][0]["coding_success_signals"]["touched_likely_file"] is True
    assert summary["attempts"][0]["coding_success_signals"]["source_scoped_discovery_commands"]
    assert "coding_postmortem_path" not in summary["attempts"][0]
    assert summary["attempts"][1]["eval_final_status"] == "pass"


def test_repair_source_aborts_idle_coder(tmp_job_agent_root: Path, run_cmd, repo_root: Path):
    write_stub_discover_script(tmp_job_agent_root)
    artifact_path = tmp_job_agent_root / "artifacts" / "discovery" / "public_service" / "2026-04-02.json"
    write_example_artifact(artifact_path)

    coder_script = tmp_job_agent_root / "fake_idle_coder.sh"
    coder_script.write_text(
        """#!/bin/bash
set -euo pipefail
trap 'exit 0' TERM
cat >/dev/null
sleep 30
"""
    )
    coder_script.chmod(0o755)

    eval_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.json"
    summary_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.repair_loop.json"
    env = os.environ.copy()
    env["JOB_AGENT_ROOT"] = str(tmp_job_agent_root)

    result = run_cmd(
        "python3",
        str(repo_root / "scripts" / "repair_source.py"),
        "--track",
        "public_service",
        "--source",
        "Example Source",
        "--today",
        "2026-04-02",
        "--artifact-path",
        str(artifact_path),
        "--canary-title",
        "Privacy Engineer",
        "--canary-url",
        "https://jobs.example.com/jobs/999",
        "--reviewer",
        "off",
        "--coder-bin",
        str(coder_script),
        "--idle-timeout-seconds",
        "1",
        "--repair-timeout-seconds",
        "10",
        "--max-attempts",
        "1",
        "--eval-output",
        str(eval_output),
        "--summary-output",
        str(summary_output),
        env=env,
        cwd=tmp_job_agent_root,
    )

    assert result.returncode == 1
    summary = json.loads(summary_output.read_text())
    assert summary["final_status"] == "blocked"
    assert summary["attempts"][0]["coding_invoked"] is True
    assert summary["attempts"][0]["coding_completion_state"] == "blocked_idle_no_progress"
    assert "went idle after 1s" in summary["attempts"][0]["coding_error"]
    postmortem = json.loads(Path(summary["attempts"][0]["coding_postmortem_path"]).read_text())
    assert postmortem["failure_class"] == "idle"
    assert postmortem["files_touched"] == []
    assert postmortem["tests_touched_or_run"] == []
    assert postmortem["runtime_error_signatures"] == []
    assert postmortem["likely_next_step"] == (
        "Resume in scripts/discover_jobs.py and make a focused patch or focused test update before more investigation."
    )


def test_repair_source_updates_summary_while_repairing(tmp_job_agent_root: Path, repo_root: Path):
    write_stub_discover_script(tmp_job_agent_root)
    artifact_path = tmp_job_agent_root / "artifacts" / "discovery" / "public_service" / "2026-04-02.json"
    write_example_artifact(artifact_path)

    coder_script = tmp_job_agent_root / "fake_progress_coder.sh"
    coder_script.write_text(
        """#!/bin/bash
set -euo pipefail
cat >/dev/null
echo '{"type":"status","message":"starting focused repair"}'
sleep 2
touch "$JOB_AGENT_ROOT/fixed.marker"
"""
    )
    coder_script.chmod(0o755)

    eval_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.json"
    summary_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.repair_loop.json"
    env = os.environ.copy()
    env["JOB_AGENT_ROOT"] = str(tmp_job_agent_root)

    process = subprocess.Popen(
        [
            "python3",
            str(repo_root / "scripts" / "repair_source.py"),
            "--track",
            "public_service",
            "--source",
            "Example Source",
            "--today",
            "2026-04-02",
            "--artifact-path",
            str(artifact_path),
            "--canary-title",
            "Privacy Engineer",
            "--canary-url",
            "https://jobs.example.com/jobs/999",
            "--reviewer",
            "off",
            "--coder-bin",
            str(coder_script),
            "--eval-output",
            str(eval_output),
            "--summary-output",
            str(summary_output),
        ],
        cwd=tmp_job_agent_root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        for _ in range(20):
            if summary_output.exists():
                summary = json.loads(summary_output.read_text())
                if summary.get("phase") == "repairing":
                    assert summary["attempts"][0]["coding_invoked"] is True
                    assert summary["attempts"][0]["coding_last_event_type"] in {"launched", "status"}
                    break
            time.sleep(0.2)
        else:
            raise AssertionError("repair loop never exposed repairing state in summary")
        stdout, stderr = process.communicate(timeout=15)
        assert process.returncode == 0, stderr
        assert stdout
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
