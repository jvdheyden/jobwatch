from __future__ import annotations

import json
import os
from pathlib import Path


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


def test_repair_source_runs_coder_and_reaches_pass(tmp_job_agent_root: Path, run_cmd, repo_root: Path):
    artifact_path = tmp_job_agent_root / "artifacts" / "discovery" / "public_service" / "2026-04-02.json"
    write_example_artifact(artifact_path)

    coder_script = tmp_job_agent_root / "fake_repair_coder.sh"
    coder_script.write_text(
        """#!/bin/bash
set -euo pipefail
cat >/dev/null
python3 - "$JOB_AGENT_DISCOVERY_ARTIFACT" "$JOB_AGENT_CANARY_TITLE" "$JOB_AGENT_CANARY_URL" <<'PY'
import json
import sys
from pathlib import Path

artifact_path = Path(sys.argv[1])
canary_title = sys.argv[2]
canary_url = sys.argv[3]
payload = json.loads(artifact_path.read_text())
candidate = payload["sources"][0]["candidates"][0]
candidate["title"] = canary_title
candidate["url"] = canary_url
artifact_path.write_text(json.dumps(payload, indent=2) + "\\n")
PY
"""
    )
    coder_script.chmod(0o755)

    eval_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.json"
    summary_output = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.repair_loop.json"
    env = os.environ.copy()

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
    assert summary["final_status"] == "pass"
    assert summary["repair_attempts_used"] == 1
    assert len(summary["attempts"]) == 2
    assert summary["attempts"][0]["eval_final_status"] == "repair_needed"
    assert summary["attempts"][0]["coding_invoked"] is True
    assert summary["attempts"][1]["eval_final_status"] == "pass"
    assert json.loads(eval_output.read_text())["final_status"] == "pass"


def test_repair_source_stops_at_retry_limit(tmp_job_agent_root: Path, run_cmd, repo_root: Path):
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
        cwd=tmp_job_agent_root,
    )

    assert result.returncode == 1
    summary = json.loads(summary_output.read_text())
    assert summary["final_status"] == "retry_limit"
    assert summary["repair_attempts_used"] == 1
    assert len(summary["attempts"]) == 2
    assert summary["attempts"][0]["coding_invoked"] is True
    assert summary["attempts"][1]["eval_final_status"] == "repair_needed"
