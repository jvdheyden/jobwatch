from __future__ import annotations

import json
import os
from pathlib import Path

import eval_source_quality


def test_eval_source_quality_runs_reviewer_and_writes_repair_ticket(tmp_job_agent_root: Path, run_cmd):
    artifact_dir = tmp_job_agent_root / "artifacts" / "discovery" / "public_service"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "2026-04-02.json"
    artifact_path.write_text(
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
                                "location": "unknown",
                                "remote": "unknown",
                                "matched_terms": ["security"],
                                "notes": "",
                            }
                        ],
                    }
                ],
            },
            indent=2,
        )
        + "\n"
    )

    reviewer_script = tmp_job_agent_root / "fake_reviewer.sh"
    reviewer_script.write_text(
        """#!/bin/bash
set -euo pipefail
cat >/dev/null
cat <<'JSON'
{"defects":[{"type":"partial_description","severity":"major","source":"Example Source","candidate_url":"https://jobs.example.com/jobs/123","canary_title":"Security Engineer","observed":"No descriptive notes were extracted.","expected":"Tasks or profile summary from the posting page.","repair_hint":"Open the detail page and capture at least one short section summary.","repro_step":"Run discover_jobs.py for Example Source and inspect candidate.notes."}]}
JSON
"""
    )
    reviewer_script.chmod(0o755)

    output_path = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.json"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "scripts")

    result = run_cmd(
        "python3",
        str(Path(__file__).resolve().parents[2] / "scripts" / "eval_source_quality.py"),
        "--track",
        "public_service",
        "--source",
        "Example Source",
        "--today",
        "2026-04-02",
        "--artifact-path",
        str(artifact_path),
        "--canary-title",
        "Security Engineer",
        "--reviewer",
        "auto",
        "--reviewer-bin",
        str(reviewer_script),
        "--output",
        str(output_path),
        env=env,
        cwd=tmp_job_agent_root,
    )

    assert result.returncode == 1
    payload = json.loads(output_path.read_text())
    assert payload["deterministic"]["confidence"] == "low"
    assert payload["reviewer"]["status"] == "completed"
    assert payload["reviewer"]["defects"][0]["type"] == "partial_description"
    assert payload["final_status"] == "repair_needed"
    assert payload["repair_ticket"]["status"] == "open"
    assert payload["repair_ticket"]["summary"] == "No descriptive notes were extracted."


def test_eval_source_quality_default_timeout_seconds_is_120():
    assert eval_source_quality.DEFAULT_REVIEW_TIMEOUT_SECONDS == 120


def test_eval_source_quality_keeps_pass_when_reviewer_times_out(tmp_job_agent_root: Path, run_cmd):
    artifact_dir = tmp_job_agent_root / "artifacts" / "discovery" / "public_service"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "2026-04-02.json"
    artifact_path.write_text(
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
                                "location": "unknown",
                                "remote": "unknown",
                                "matched_terms": ["security"],
                                "notes": "",
                            }
                        ],
                    }
                ],
            },
            indent=2,
        )
        + "\n"
    )

    reviewer_script = tmp_job_agent_root / "fake_timeout_reviewer.sh"
    reviewer_script.write_text(
        """#!/bin/bash
set -euo pipefail
cat >/dev/null
sleep 30
"""
    )
    reviewer_script.chmod(0o755)

    output_path = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.json"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "scripts")

    result = run_cmd(
        "python3",
        str(Path(__file__).resolve().parents[2] / "scripts" / "eval_source_quality.py"),
        "--track",
        "public_service",
        "--source",
        "Example Source",
        "--today",
        "2026-04-02",
        "--artifact-path",
        str(artifact_path),
        "--reviewer",
        "auto",
        "--reviewer-bin",
        str(reviewer_script),
        "--timeout-seconds",
        "1",
        "--output",
        str(output_path),
        env=env,
        cwd=tmp_job_agent_root,
    )

    assert result.returncode == 0
    payload = json.loads(output_path.read_text())
    assert payload["deterministic"]["confidence"] == "low"
    assert payload["reviewer"]["status"] == "blocked"
    assert "timed out after 1" in payload["reviewer"]["error"]
    assert payload["final_status"] == "pass"
    assert payload["repair_ticket"] is None
