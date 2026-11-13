from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from unittest.mock import Mock

import eval_source_quality
from discover import http
from discover.core import SourceConfig, enrich_candidate_descriptions
from discover.sources.generic_html import discover_html


def test_generic_policy_description_does_not_skip_auto_review(tmp_path, monkeypatch):
    source = SourceConfig("Example", "https://example.com/careers", "html", None, "every_run")
    pages = {
        source.url: '<a href="/security">Security Policy</a>',
        "https://example.com/security": (
            "<h1>Security Policy</h1><p>We comply with applicable security requirements "
            "to protect customer data.</p>"
        ),
    }
    monkeypatch.setattr(http, "fetch_text", lambda url, *_: pages[url])
    coverage = discover_html(source, ["security"], 10)
    enrich_candidate_descriptions(coverage, 10)
    assert len(coverage.candidates) == 1
    assert "security requirements" in coverage.candidates[0].description

    artifact = tmp_path / "discovery.json"
    artifact.write_text(json.dumps({"sources": [asdict(coverage)]}))
    output = tmp_path / "eval.json"
    reviewer = Mock(return_value={
        "status": "completed",
        "defects": [{
            "type": "navigation_noise",
            "severity": "major",
            "observed": "Security Policy is not a job posting.",
        }],
    })
    monkeypatch.setattr(eval_source_quality, "review_source_with_llm", reviewer)
    monkeypatch.setattr(eval_source_quality, "apply_runtime_env", lambda **_: None)
    monkeypatch.setattr(eval_source_quality, "resolve_reviewer_bin", lambda _: None)
    monkeypatch.setattr(sys, "argv", [
        "eval_source_quality.py", "--track", "test", "--source", "Example",
        "--today", "2026-11-13", "--artifact-path", str(artifact),
        "--output", str(output), "--reviewer", "auto",
    ])

    assert eval_source_quality.main() == 1
    reviewer.assert_called_once()
    payload = json.loads(output.read_text())
    assert payload["deterministic"]["confidence"] == "low"
    assert payload["reviewer"]["status"] == "completed"
    assert payload["integration_ticket"]["failure_mode"] == "candidate_noise"
    assert payload["integration_ticket"]["suggested_strategy"] == "config_terms_override"


def test_eval_source_quality_runs_reviewer_and_writes_integration_ticket(tmp_job_agent_root: Path, run_cmd):
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
{"defects":[{"type":"partial_description","severity":"major","source":"Example Source","candidate_url":"https://jobs.example.com/jobs/123","canary_title":"Security Engineer","observed":"No descriptive notes were extracted.","expected":"Tasks or profile summary from the posting page.","integration_hint":"Open the detail page and capture at least one short section summary.","repro_step":"Run discover_jobs.py for Example Source and inspect candidate.notes."}]}
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
    assert payload["final_status"] == "integration_needed"
    assert payload["integration_ticket"]["status"] == "open"
    assert payload["integration_ticket"]["summary"] == "No descriptive notes were extracted."
    assert payload["integration_ticket"]["failure_mode"] == "missing_detail"
    assert payload["integration_ticket"]["suggested_strategy"] == "dedicated_provider_logic"
    assert payload["integration_ticket"]["target_outcome"].startswith("Fresh discovery artifact keeps the relevant candidates")
    assert payload["integration_ticket"]["primary_evidence"] == [
        "partial_description: No descriptive notes were extracted."
    ]


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
    assert payload["integration_ticket"] is None
