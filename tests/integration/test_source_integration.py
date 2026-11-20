from __future__ import annotations

import json
import os
import source_integration
import subprocess
import time
from pathlib import Path

import pytest


GENERIC_HTML_PROVIDER = "scripts/discover/sources/generic_html.py"


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
                        "description": "Tasks: Build secure systems for public-sector services. Profile: security engineering background.",
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
                                "description": "Tasks: Build secure systems for public-sector services. Profile: security engineering background.",
                            }
                        ],
                    }
                ],
            },
            indent=2,
        )
        + "\n"
    )


def test_source_integration_runs_coder_and_reaches_pass(tmp_job_agent_root: Path, run_cmd, repo_root: Path):
    write_stub_discover_script(tmp_job_agent_root)
    artifact_path = tmp_job_agent_root / "artifacts" / "discovery" / "public_service" / "2026-04-02.json"
    write_example_artifact(artifact_path)

    coder_script = tmp_job_agent_root / "fake_source_integration_coder.sh"
    coder_script.write_text(
        """#!/bin/bash
set -euo pipefail
printf '%s\\n' "$@" >"$JOB_AGENT_ROOT/coder-args.txt"
cat >"$JOB_AGENT_ROOT/prompt.txt"
echo '{"type":"status","message":"touching fix marker"}'
touch "$JOB_AGENT_ROOT/fixed.marker"
"""
    )
    coder_script.chmod(0o755)

    eval_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.json"
    summary_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.source_integration_loop.json"
    env = os.environ.copy()
    env["JOB_AGENT_ROOT"] = str(tmp_job_agent_root)

    result = run_cmd(
        "python3",
        str(repo_root / "scripts" / "source_integration.py"),
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
    args = (tmp_job_agent_root / "coder-args.txt").read_text().splitlines()
    assert args[args.index("-m") + 1] == "gpt-6.2-sol"
    assert args[args.index("-s") + 1] == "workspace-write"
    assert 'model_reasoning_effort="medium"' in args
    assert "gpt-6.2-sol (tier=workhorse-latest, reasoning effort=medium)" in result.stderr
    summary = json.loads(summary_output.read_text())
    prompt_text = (tmp_job_agent_root / "prompt.txt").read_text()
    assert summary["final_status"] == "pass"
    assert summary["integration_attempts_used"] == 1
    assert len(summary["attempts"]) == 2
    assert summary["attempts"][0]["eval_final_status"] == "integration_needed"
    assert summary["attempts"][0]["coding_invoked"] is True
    assert summary["attempts"][0]["rediscovery_invoked"] is True
    assert summary["attempts"][0]["coding_last_event_type"] == "status"
    assert "touching fix marker" in summary["attempts"][0]["coding_last_event_excerpt"]
    assert summary["attempts"][1]["eval_final_status"] == "pass"
    assert summary["active_artifact_path"].endswith("2026-04-02.discovery.json")
    assert json.loads(eval_output.read_text())["final_status"] == "pass"
    # Preserve task evidence and the machine-readable handoff interface without
    # freezing instructional prose or headings.
    assert GENERIC_HTML_PROVIDER in prompt_text
    assert "Privacy Engineer" in prompt_text
    assert "https://jobs.example.com/jobs/999" in prompt_text
    assert "SOURCE_INTEGRATION_HANDOFF:" in prompt_text
    assert "tracks/public_service/sources.json" in prompt_text


def test_source_integration_runs_claude_coder_with_stream_json(tmp_job_agent_root: Path, run_cmd, repo_root: Path):
    write_stub_discover_script(tmp_job_agent_root)
    artifact_path = tmp_job_agent_root / "artifacts" / "discovery" / "public_service" / "2026-04-02.json"
    write_example_artifact(artifact_path)

    coder_script = tmp_job_agent_root / "fake_claude_coder.sh"
    coder_script.write_text(
        """#!/bin/bash
set -euo pipefail
printf '%s\\n' "$@" >"$JOB_AGENT_ROOT/claude-coder-args.txt"
cat >"$JOB_AGENT_ROOT/claude-prompt.txt"
touch "$JOB_AGENT_ROOT/fixed.marker"
cat <<'JSON'
{"type":"assistant","message":{"content":[{"type":"text","text":"touching fix marker"}]}}
{"type":"result","subtype":"success","result":"done"}
JSON
"""
    )
    coder_script.chmod(0o755)

    eval_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.json"
    summary_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.source_integration_loop.json"
    env = os.environ.copy()
    env["JOB_AGENT_ROOT"] = str(tmp_job_agent_root)
    env["JOB_AGENT_PROVIDER"] = "claude"

    result = run_cmd(
        "python3",
        str(repo_root / "scripts" / "source_integration.py"),
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
    args_text = (tmp_job_agent_root / "claude-coder-args.txt").read_text()
    assert summary["final_status"] == "pass"
    assert summary["attempts"][0]["coding_provider"] == "claude"
    assert summary["attempts"][0]["coding_last_event_type"] == "result"
    assert "done" in summary["attempts"][0]["coding_last_event_excerpt"]
    assert "-p" in args_text
    assert "stream-json" in args_text
    assert "--verbose" in args_text
    assert "Privacy Engineer" in (tmp_job_agent_root / "claude-prompt.txt").read_text()
    args = args_text.splitlines()
    assert args[args.index("--model") + 1] == "sonnet"
    assert args[args.index("--effort") + 1] == "medium"


def test_source_integration_runs_gemini_coder_with_stream_json(tmp_job_agent_root: Path, run_cmd, repo_root: Path):
    write_stub_discover_script(tmp_job_agent_root)
    artifact_path = tmp_job_agent_root / "artifacts" / "discovery" / "public_service" / "2026-04-02.json"
    write_example_artifact(artifact_path)

    coder_script = tmp_job_agent_root / "fake_gemini_coder.sh"
    coder_script.write_text(
        """#!/bin/bash
set -euo pipefail
printf '%s\\n' "$@" >"$JOB_AGENT_ROOT/gemini-coder-args.txt"
printf '%s\\n' "${GEMINI_SANDBOX-}" >"$JOB_AGENT_ROOT/gemini-sandbox.txt"
cat >"$JOB_AGENT_ROOT/gemini-prompt.txt"
touch "$JOB_AGENT_ROOT/fixed.marker"
cat <<'JSON'
{"type":"message","message":"touching fix marker"}
{"type":"result","result":"done"}
JSON
"""
    )
    coder_script.chmod(0o755)

    eval_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.json"
    summary_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.source_integration_loop.json"
    env = os.environ.copy()
    env["JOB_AGENT_ROOT"] = str(tmp_job_agent_root)
    env["JOB_AGENT_PROVIDER"] = "gemini"

    result = run_cmd(
        "python3",
        str(repo_root / "scripts" / "source_integration.py"),
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
    args_text = (tmp_job_agent_root / "gemini-coder-args.txt").read_text()
    assert summary["final_status"] == "pass"
    assert summary["attempts"][0]["coding_provider"] == "gemini"
    assert summary["attempts"][0]["coding_last_event_type"] == "result"
    assert "done" in summary["attempts"][0]["coding_last_event_excerpt"]
    assert "--skip-trust" in args_text
    assert "stream-json" in args_text
    assert "--approval-mode" in args_text
    assert "yolo" in args_text
    assert (tmp_job_agent_root / "gemini-sandbox.txt").read_text() == "false\n"
    assert "Privacy Engineer" in (tmp_job_agent_root / "gemini-prompt.txt").read_text()
    args = args_text.splitlines()
    assert args[args.index("--model") + 1] == "flash"


def test_source_integration_stops_at_retry_limit(tmp_job_agent_root: Path, run_cmd, repo_root: Path):
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
    summary_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.source_integration_loop.json"
    env = os.environ.copy()
    env["JOB_AGENT_ROOT"] = str(tmp_job_agent_root)

    result = run_cmd(
        "python3",
        str(repo_root / "scripts" / "source_integration.py"),
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
    assert summary["integration_attempts_used"] == 1
    assert len(summary["attempts"]) == 2
    assert summary["attempts"][0]["coding_invoked"] is True
    assert summary["attempts"][0]["rediscovery_invoked"] is True
    assert summary["attempts"][1]["eval_final_status"] == "integration_needed"


def test_source_integration_retries_blocked_coder_with_postmortem_context(tmp_job_agent_root: Path, run_cmd, repo_root: Path):
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
    summary_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.source_integration_loop.json"
    env = os.environ.copy()
    env["JOB_AGENT_ROOT"] = str(tmp_job_agent_root)

    result = run_cmd(
        "python3",
        str(repo_root / "scripts" / "source_integration.py"),
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
        "--integration-timeout-seconds",
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
    assert summary["integration_attempts_used"] == 2
    assert len(summary["attempts"]) == 3
    assert summary["attempts"][0]["coding_error"] == "integration run went idle after 1s without new output"
    assert first_postmortem_path.exists()
    assert first_postmortem["failure_class"] == "idle"
    assert "coder-count.txt" in first_postmortem["files_touched"]
    assert "prompt-1.txt" in first_postmortem["files_touched"]
    assert first_postmortem["tests_touched_or_run"] == []
    assert first_postmortem["runtime_error_signatures"] == []
    assert first_postmortem["likely_next_step"] == (
        f"Resume in {GENERIC_HTML_PROVIDER} and make a focused patch or focused test update before more investigation."
    )
    assert "Prior blocked attempt context:" not in first_prompt
    assert "Prior blocked attempt context:" in second_prompt
    assert "integration run went idle after 1s without new output" in second_prompt
    assert summary["attempts"][1]["coding_invoked"] is True
    assert summary["attempts"][1]["rediscovery_invoked"] is True
    assert summary["attempts"][2]["eval_final_status"] == "pass"


def test_source_integration_proceeds_to_rediscovery_after_idle_with_success_signals(tmp_job_agent_root: Path, run_cmd, repo_root: Path):
    write_stub_discover_script(tmp_job_agent_root)
    artifact_path = tmp_job_agent_root / "artifacts" / "discovery" / "public_service" / "2026-04-02.json"
    write_example_artifact(artifact_path)

    coder_script = tmp_job_agent_root / "fake_success_then_idle_coder.sh"
    coder_script.write_text(
        """#!/bin/bash
set -euo pipefail
cat >/dev/null
touch "$JOB_AGENT_ROOT/fixed.marker"
mkdir -p "$JOB_AGENT_ROOT/scripts/discover/sources"
touch "$JOB_AGENT_ROOT/scripts/discover/sources/generic_html.py"
echo '{"type":"item.completed","item":{"id":"item_1","type":"command_execution","command":"/bin/zsh -lc '\''python3 scripts/discover_jobs.py --track public_service --source \"Example Source\" --today 2026-04-02 --pretty'\''","aggregated_output":"ok","exit_code":0,"status":"completed"}}'
trap 'exit 0' TERM
sleep 30
"""
    )
    coder_script.chmod(0o755)

    eval_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.json"
    summary_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.source_integration_loop.json"
    env = os.environ.copy()
    env["JOB_AGENT_ROOT"] = str(tmp_job_agent_root)

    result = run_cmd(
        "python3",
        str(repo_root / "scripts" / "source_integration.py"),
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
        "--integration-timeout-seconds",
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
    assert summary["integration_attempts_used"] == 1
    assert summary["attempts"][0]["coding_completion_state"] == "ready_for_rediscovery_idle"
    assert summary["attempts"][0]["rediscovery_invoked"] is True
    assert summary["attempts"][0]["coding_success_signals"]["ready_for_rediscovery"] is True
    assert summary["attempts"][0]["coding_success_signals"]["touched_likely_file"] is True
    assert summary["attempts"][0]["coding_success_signals"]["source_scoped_discovery_commands"]
    assert "coding_postmortem_path" not in summary["attempts"][0]
    assert summary["attempts"][1]["eval_final_status"] == "pass"


def test_source_integration_aborts_idle_coder(tmp_job_agent_root: Path, run_cmd, repo_root: Path):
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
    summary_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.source_integration_loop.json"
    env = os.environ.copy()
    env["JOB_AGENT_ROOT"] = str(tmp_job_agent_root)

    result = run_cmd(
        "python3",
        str(repo_root / "scripts" / "source_integration.py"),
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
        "--integration-timeout-seconds",
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
        f"Resume in {GENERIC_HTML_PROVIDER} and make a focused patch or focused test update before more investigation."
    )


def test_source_integration_records_structured_handoff_without_rediscovery(tmp_job_agent_root: Path, run_cmd, repo_root: Path):
    write_stub_discover_script(tmp_job_agent_root)
    artifact_path = tmp_job_agent_root / "artifacts" / "discovery" / "public_service" / "2026-04-02.json"
    write_example_artifact(artifact_path)

    coder_script = tmp_job_agent_root / "fake_handoff_coder.sh"
    coder_script.write_text(
        """#!/bin/bash
set -euo pipefail
cat >/dev/null
cat <<'JSON'
{"type":"item.completed","item":{"id":"item_1","type":"agent_message","text":"SOURCE_INTEGRATION_HANDOFF: {\\"reason\\":\\"No credible focused fix yet\\",\\"likely_file\\":\\"scripts/discover_jobs.py\\",\\"hypothesis\\":\\"The source-specific keep logic is still too broad for this source\\",\\"next_edit\\":\\"Tighten the source-specific keep logic in scripts/discover_jobs.py and add a focused regression in tests/integration/test_discover_followup_sources.py.\\",\\"test_hint\\":\\"tests/integration/test_discover_followup_sources.py\\",\\"evidence\\":[\\"The source still surfaces noisy candidates\\",\\"No focused regression exists yet\\"]}"}}
JSON
"""
    )
    coder_script.chmod(0o755)

    eval_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.json"
    summary_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.source_integration_loop.json"
    env = os.environ.copy()
    env["JOB_AGENT_ROOT"] = str(tmp_job_agent_root)

    result = run_cmd(
        "python3",
        str(repo_root / "scripts" / "source_integration.py"),
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
    assert summary["final_status"] == "blocked"
    assert summary["attempts"][0]["coding_completion_state"] == "blocked_handoff"
    assert summary["attempts"][0]["rediscovery_invoked"] is False
    assert summary["attempts"][0]["coding_handoff"]["likely_file"] == "scripts/discover_jobs.py"
    postmortem = json.loads(Path(summary["attempts"][0]["coding_postmortem_path"]).read_text())
    assert postmortem["failure_class"] == "needs_handoff"
    assert postmortem["structured_handoff"]["test_hint"] == "tests/integration/test_discover_followup_sources.py"
    assert postmortem["likely_next_step"] == (
        "Tighten the source-specific keep logic in scripts/discover_jobs.py and add a focused regression in tests/integration/test_discover_followup_sources.py."
    )


def test_source_integration_updates_summary_while_integrating(tmp_job_agent_root: Path, repo_root: Path):
    write_stub_discover_script(tmp_job_agent_root)
    artifact_path = tmp_job_agent_root / "artifacts" / "discovery" / "public_service" / "2026-04-02.json"
    write_example_artifact(artifact_path)

    coder_script = tmp_job_agent_root / "fake_progress_coder.sh"
    coder_script.write_text(
        """#!/bin/bash
set -euo pipefail
cat >/dev/null
echo '{"type":"status","message":"starting focused source integration"}'
sleep 2
touch "$JOB_AGENT_ROOT/fixed.marker"
"""
    )
    coder_script.chmod(0o755)

    eval_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.json"
    summary_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.source_integration_loop.json"
    env = os.environ.copy()
    env["JOB_AGENT_ROOT"] = str(tmp_job_agent_root)

    process = subprocess.Popen(
        [
            "python3",
            str(repo_root / "scripts" / "source_integration.py"),
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
                if summary.get("phase") == "integrating":
                    assert summary["attempts"][0]["coding_invoked"] is True
                    assert summary["attempts"][0]["coding_last_event_type"] in {"launched", "status"}
                    break
            time.sleep(0.2)
        else:
            raise AssertionError("source integration loop never exposed integrating state in summary")
        stdout, stderr = process.communicate(timeout=15)
        assert process.returncode == 0, stderr
        assert stdout
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def write_description_discovery_stub(root: Path, repo_root: Path, artifact: Path) -> Path:
    """Keep discovery inputs fixed while coder doubles edit the provider module."""
    scripts = root / "scripts"
    scripts.mkdir()
    provider = scripts / "example_provider.py"
    (scripts / "discover_jobs.py").write_text(
        f"""import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, {str(repo_root / 'scripts')!r})
from discover.core import Candidate
from example_provider import populate_descriptions

payload = json.loads(Path({str(artifact)!r}).read_text())
source = payload["sources"][0]
candidates = [Candidate(**item) for item in source["candidates"]]
source["candidates"] = [asdict(item) for item in populate_descriptions(candidates)]
output = Path(sys.argv[sys.argv.index("--output") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(payload))
"""
    )
    return provider


def description_loop_command(
    root: Path, repo_root: Path, artifact: Path, coder: Path, *, reviewer: str = "off",
) -> list[str]:
    return [
        "python3", str(repo_root / "scripts" / "source_integration.py"),
        "--track", "public_service", "--source", "Example Source", "--today", "2026-04-02",
        "--artifact-path", str(artifact), "--reviewer", reviewer, "--coder-bin", str(coder),
        "--summary-output", str(root / "summary.json"), "--timeout-seconds", "1",
    ]


def test_description_loop_reevaluates_provider_edit_and_preserves_floor(
    tmp_job_agent_root, run_cmd, repo_root,
):
    root = tmp_job_agent_root
    artifact = root / "discovery.json"
    write_example_artifact(artifact)
    payload = json.loads(artifact.read_text())
    [source] = payload["sources"]
    [candidate] = source["candidates"]
    body = candidate["description"]
    candidate.update(description="", notes=body)
    source["candidates"].append({
        **candidate, "title": "Systems Engineer", "url": "https://jobs.example.com/jobs/456", "notes": "",
    })
    artifact.write_text(json.dumps(payload))
    provider = write_description_discovery_stub(root, repo_root, artifact)
    provider.write_text("def populate_descriptions(candidates):\n    return candidates\n")
    coder = root / "coder.sh"
    coder.write_text(
        """#!/bin/bash
set -eu
cat > "$JOB_AGENT_ROOT/prompt.txt"
cd "$JOB_AGENT_ROOT"
if [[ ! -e first-attempt ]]; then
    touch first-attempt
    cat > scripts/example_provider.py <<'PROVIDER'
def populate_descriptions(candidates):
    candidates[0].notes += " Maintains systems for three offices."
    return candidates
PROVIDER
elif [[ ! -e second-attempt ]]; then
    touch second-attempt
    cat > scripts/example_provider.py <<'PROVIDER'
from discover.helpers import set_candidate_description

def populate_descriptions(candidates):
    set_candidate_description(candidates[0], candidates[0].notes)
    return candidates
PROVIDER
else
    cat > scripts/example_provider.py <<'PROVIDER'
from discover.helpers import set_candidate_description

def populate_descriptions(candidates):
    set_candidate_description(candidates[0], candidates[0].notes)
    set_candidate_description(candidates[1], "Develop secure data pipelines for public infrastructure.")
    return candidates
PROVIDER
fi
"""
    )
    coder.chmod(0o755)
    command = description_loop_command(root, repo_root, artifact, coder)
    result = run_cmd(
        *command, "--max-attempts", "3", "--min-detail-fraction", "1", cwd=root,
        env={**os.environ, "JOB_AGENT_ROOT": str(root)},
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads((root / "summary.json").read_text())
    attempts = summary["attempts"]
    assert [attempt["eval_final_status"] for attempt in attempts] == ["integration_needed"] * 3 + ["pass"]
    assert "outside an unusable description" in attempts[1]["integration_ticket_summary"]
    assert "Reviewed minimum fraction is 1.0" in attempts[2]["integration_ticket_summary"]
    assert "set_candidate_description" in (root / "prompt.txt").read_text()
    [fresh_source] = json.loads(Path(summary["active_artifact_path"]).read_text())["sources"]
    assert [item["url"] for item in fresh_source["candidates"]] == [item["url"] for item in source["candidates"]]
    assert all(item["description"] for item in fresh_source["candidates"])


@pytest.mark.parametrize(
    "provider_body,expected_status",
    [
        ("set_candidate_description(candidates[0], candidates[0].notes)", "pass"),
        ('candidates[0].notes = ""', "inconclusive"),
        ("candidates.clear()", "inconclusive"),
    ],
    ids=["current-body", "notes-cleared", "empty-rediscovery"],
)
def test_legacy_description_ticket_requires_current_discovery_before_coding(
    tmp_job_agent_root, run_cmd, repo_root, provider_body, expected_status,
):
    root = tmp_job_agent_root
    artifact = root / "legacy.json"
    write_example_artifact(artifact)
    payload = json.loads(artifact.read_text())
    [candidate] = payload["sources"][0]["candidates"]
    candidate["notes"] = candidate.pop("description")
    artifact.write_text(json.dumps(payload))
    provider = write_description_discovery_stub(root, repo_root, artifact)
    provider.write_text(
        "from discover.helpers import set_candidate_description\n\n"
        "def populate_descriptions(candidates):\n"
        f"    {provider_body}\n"
        "    return candidates\n"
    )
    coder = root / "coder.sh"
    coder.write_text("#!/bin/bash\nexit 99\n")
    coder.chmod(0o755)

    result = run_cmd(
        *description_loop_command(root, repo_root, artifact, coder), cwd=root,
        env={**os.environ, "JOB_AGENT_ROOT": str(root)},
    )
    assert result.returncode == (0 if expected_status == "pass" else 1), result.stderr
    summary = json.loads((root / "summary.json").read_text())
    assert summary["final_status"] == expected_status
    assert summary["integration_attempts_used"] == 0
    assert summary["attempts"][0]["rediscovery_invoked"]
    assert summary["final_eval"]["deterministic"]["description_coverage"]["usable"] == (expected_status == "pass")


@pytest.mark.parametrize("keep_fourth", [False, True], ids=["drops-fourth", "retains-all"])
def test_description_repair_requires_every_affected_posting_beyond_sample(
    tmp_job_agent_root, run_cmd, repo_root, keep_fourth,
):
    root = tmp_job_agent_root
    artifact = root / "discovery.json"
    write_example_artifact(artifact)
    payload = json.loads(artifact.read_text())
    [source] = payload["sources"]
    [example] = source["candidates"]
    source["candidates"] = [
        {**example, "title": f"Engineer {index}", "url": f"https://jobs.example.com/jobs/{index}",
         "description": "", "notes": example["description"]}
        for index in range(1, 5)
    ]
    artifact.write_text(json.dumps(payload))
    provider = write_description_discovery_stub(root, repo_root, artifact)
    provider.write_text("def populate_descriptions(candidates):\n    return candidates\n")
    coder = root / "coder.sh"
    repaired_candidates = "candidates" if keep_fourth else "candidates[:3]"
    coder.write_text(
        f"""#!/bin/bash
set -eu
cat > "$JOB_AGENT_ROOT/prompt.txt"
cp "$JOB_AGENT_EVAL_ARTIFACT" "$JOB_AGENT_ROOT/before.json"
cat > "$JOB_AGENT_ROOT/scripts/example_provider.py" <<'PROVIDER'
from discover.helpers import set_candidate_description

def populate_descriptions(candidates):
    retained = {repaired_candidates}
    for candidate in retained:
        set_candidate_description(candidate, candidate.notes)
    return retained
PROVIDER
"""
    )
    coder.chmod(0o755)

    result = run_cmd(
        *description_loop_command(root, repo_root, artifact, coder), "--max-attempts", "1", cwd=root,
        env={**os.environ, "JOB_AGENT_ROOT": str(root)},
    )
    summary = json.loads((root / "summary.json").read_text())
    before = json.loads((root / "before.json").read_text())
    assert len(before["integration_ticket"]["description_evidence"]) == 3
    detail = before["deterministic"]["description_coverage"]
    assert detail["demonstrated_omissions"] == 4
    assert {item["url"] for item in detail["affected_postings"]} == {
        candidate["url"] for candidate in source["candidates"]
    }
    assert summary["final_status"] == ("pass" if keep_fourth else "inconclusive")
    assert result.returncode == (0 if keep_fourth else 1)
    if not keep_fourth:
        assert source["candidates"][3]["url"] in summary["attempts"][-1]["error"]


@pytest.mark.parametrize("keep_flagged", [False, True], ids=["drops-flagged", "repairs-flagged"])
def test_description_repair_verifies_reviewer_flagged_posting(
    tmp_job_agent_root, run_cmd, repo_root, keep_flagged,
):
    root = tmp_job_agent_root
    artifact = root / "discovery.json"
    write_example_artifact(artifact)
    payload = json.loads(artifact.read_text())
    [source] = payload["sources"]
    [healthy] = source["candidates"]
    flagged = {
        **healthy, "title": "Network Engineer", "url": "https://jobs.example.com/jobs/456",
        "alternate_url": "https://jobs.example.com/apply/456", "description": "",
    }
    source.update(candidates=[flagged, healthy], enumerated_jobs=2, matched_jobs=2)
    artifact.write_text(json.dumps(payload))
    provider = write_description_discovery_stub(root, repo_root, artifact)
    provider.write_text("def populate_descriptions(candidates):\n    return candidates\n")

    reviewer = root / "reviewer.sh"
    reviewer.write_text(
        """#!/bin/bash
set -eu
cat >/dev/null
if [[ -e repaired.marker ]]; then
    echo '{"defects":[]}'
else
    cat <<'JSON'
{"defects":[
  {"type":"partial_description","severity":"major","candidate_url":"https://jobs.example.com/apply/456/?utm_source=review#details","observed":"The saved description is empty.","expected":"The official posting describes maintaining network infrastructure."},
  {"type":"partial_description","severity":"blocking","candidate_url":"https://jobs.example.com/jobs/999","observed":"Unmatched URL."}
]}
JSON
fi
"""
    )
    reviewer.chmod(0o755)
    coder = root / "coder.sh"
    repaired_candidates = "candidates" if keep_flagged else "candidates[1:]"
    coder.write_text(
        f"""#!/bin/bash
set -eu
cat >/dev/null
cp "$JOB_AGENT_EVAL_ARTIFACT" "$JOB_AGENT_ROOT/before.json"
touch "$JOB_AGENT_ROOT/repaired.marker"
cat > "$JOB_AGENT_ROOT/scripts/example_provider.py" <<'PROVIDER'
from discover.helpers import set_candidate_description

def populate_descriptions(candidates):
    set_candidate_description(candidates[0], "Maintain network infrastructure across regional offices.")
    return {repaired_candidates}
PROVIDER
"""
    )
    coder.chmod(0o755)

    result = run_cmd(
        *description_loop_command(root, repo_root, artifact, coder, reviewer="force"),
        "--reviewer-bin", str(reviewer), "--max-attempts", "1", cwd=root,
        env={**os.environ, "JOB_AGENT_ROOT": str(root)},
    )
    before = json.loads((root / "before.json").read_text())
    assert before["integration_ticket"]["failure_mode"] == "missing_detail"
    assert before["deterministic"]["description_coverage"]["affected_postings"] == []
    summary = json.loads((root / "summary.json").read_text())
    assert summary["final_status"] == ("pass" if keep_flagged else "inconclusive")
    assert result.returncode == (0 if keep_flagged else 1)
    [fresh_source] = json.loads(Path(summary["active_artifact_path"]).read_text())["sources"]
    assert {item["url"] for item in fresh_source["candidates"]} == (
        {flagged["url"], healthy["url"]} if keep_flagged else {healthy["url"]}
    )
    if not keep_flagged:
        assert summary["attempts"][-1]["error"].endswith(flagged["url"])
