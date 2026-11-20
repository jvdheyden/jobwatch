from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from unittest.mock import Mock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

import pytest

import eval_source_quality
from discover import http
from discover.core import SourceConfig, enrich_candidate_descriptions
from discover.sources.generic_html import discover_html


@pytest.fixture
def quality_site():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/jobs/unavailable":
                self.send_error(503)
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'<h1>Security Engineer</h1>')
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


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


def test_eval_source_quality_runs_reviewer_and_writes_integration_ticket(tmp_job_agent_root: Path, run_cmd, quality_site):
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
                        "source_url": f"{quality_site}/search",
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
                                "url": f"{quality_site}/jobs/123",
                                "source_url": f"{quality_site}/search",
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
{"defects":[{"type":"partial_description","severity":"major","source":"Example Source","candidate_url":"https://jobs.example.com/jobs/123","canary_title":"Security Engineer","observed":"The description was empty.","expected":"The posting lists duties for maintaining secure systems.","integration_hint":"Open the detail page and capture at least one short section summary.","repro_step":"Run discover_jobs.py for Example Source and inspect candidate.description."}]}
JSON
""".replace("https://jobs.example.com", quality_site)
    )
    reviewer_script.chmod(0o755)

    output_path = tmp_job_agent_root / "artifacts" / "evals" / "public_service" / "example_source" / "2026-04-02.json"
    env = os.environ.copy()

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
    assert payload["integration_ticket"]["summary"] == "The description was empty."
    assert payload["integration_ticket"]["failure_mode"] == "missing_detail"
    assert payload["integration_ticket"]["suggested_strategy"] == "dedicated_provider_logic"
    assert payload["integration_ticket"]["target_outcome"].startswith("Fresh discovery artifact keeps the relevant candidates")
    [evidence] = payload["integration_ticket"]["primary_evidence"]
    assert f"{quality_site}/jobs/123" in evidence
    assert "The description was empty." in evidence
    assert "maintaining secure systems" in evidence


def test_eval_source_quality_keeps_pass_when_reviewer_times_out(tmp_job_agent_root: Path, run_cmd, quality_site):
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
                        "source_url": f"{quality_site}/search",
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
                                "url": f"{quality_site}/jobs/123",
                                "source_url": f"{quality_site}/search",
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


@pytest.mark.parametrize(
    "name,mode,description,notes,corrected,status,secondary",
    [
        (
            "Bundeswehr", "bundeswehr_jobsuche",
            "Onlinebewerbung Das Bewerbungsportal wird geladen...",
            "RefCode: TEST-001; Deadline: 29.01.2027; Job: Sichere Netze konfigurieren und Störungen beheben.",
            "Aufgaben: Sichere Netze konfigurieren und Störungen beheben.",
            "complete", {"result_volume"},
        ),
        (
            "Meta", "browser", "",
            "Meta browser search q='privacy' page=1; Qualifications: Experience designing distributed systems.",
            "Minimum Qualifications: Experience designing distributed systems.",
            "partial", {"result_volume", "execution_complete", "browser_fallback_quality"},
        ),
    ],
)
def test_eval_prioritizes_demonstrated_description_omissions(
    tmp_path, monkeypatch, name, mode, description, notes, corrected, status, secondary,
):
    source_url = "https://jobs.example.org/search"
    affected = {
        "employer": name, "title": "Systems Engineer", "url": "https://jobs.example.org/jobs/one",
        "source_url": source_url, "location": "Berlin", "description": description, "notes": notes,
    }
    healthy = {
        **affected, "title": "Network Engineer", "url": "https://jobs.example.org/jobs/two", "notes": "",
        "description": "Design network monitoring systems and investigate outages.",
    }
    source = {
        "source": name, "source_url": source_url, "discovery_mode": mode, "status": status, "matched_jobs": 41,
        "candidates": [healthy, affected],
    }
    artifact = tmp_path / "discovery.json"
    output = tmp_path / "eval.json"
    monkeypatch.setenv("JOB_AGENT_ROOT", str(tmp_path))
    monkeypatch.setattr(sys, "argv", [
        "eval_source_quality.py", "--track", "demo", "--source", name, "--today", "2026-11-20",
        "--artifact-path", str(artifact), "--output", str(output), "--reviewer", "off",
        "--min-detail-fraction", "0.5",
    ])

    artifact.write_text(json.dumps({"sources": [source]}))
    assert eval_source_quality.main() == 1
    payload = json.loads(output.read_text())
    ticket = payload["integration_ticket"]
    assert payload["reviewer"]["status"] == "skipped"
    assert payload["deterministic"]["description_coverage"]["fraction"] == 0.5
    assert set(ticket["failing_checks"]) == {"detail_depth", *secondary}
    assert ticket["failure_mode"] == "missing_detail"
    assert ticket["suggested_strategy"] == "dedicated_provider_logic"
    assert affected["title"] in ticket["summary"]
    assert "set_candidate_description" in ticket["target_outcome"]
    [evidence] = ticket["description_evidence"]
    assert evidence["url"] == affected["url"]
    assert evidence["description_excerpt"] == description
    assert evidence["role_text_source"] == "notes"
    assert corrected.split(": ", 1)[1] in evidence["role_text_excerpt"]
    assert evidence["role_text_excerpt"] in ticket["primary_evidence"][0]

    affected["description"] = corrected
    artifact.write_text(json.dumps({"sources": [source]}))
    assert eval_source_quality.main() == 1
    payload = json.loads(output.read_text())
    assert payload["deterministic"]["description_coverage"]["fraction"] == 1
    assert set(payload["integration_ticket"]["failing_checks"]) == secondary
    assert payload["integration_ticket"]["failure_mode"] != "missing_detail"


@pytest.mark.parametrize("reviewer_mode", ["off", "auto"])
def test_browser_eval_defers_acceptance_without_verifiable_descriptions(
    tmp_path, monkeypatch, quality_site, reviewer_mode,
):
    source = {
        "source": "Example", "source_url": f"{quality_site}/search", "discovery_mode": "browser",
        "status": "complete", "enumerated_jobs": 1,
        "candidates": [{
            "employer": "Example", "title": "Security Engineer",
            "url": f"{quality_site}/jobs/unavailable", "source_url": f"{quality_site}/search",
            "location": "Berlin", "description": "", "notes": "",
        }],
    }
    artifact = tmp_path / "discovery.json"
    artifact.write_text(json.dumps({"sources": [source]}))
    output = tmp_path / "eval.json"
    reviewer = Mock(return_value={"status": "blocked", "defects": [], "error": "Timed out"})
    monkeypatch.setenv("JOB_AGENT_ROOT", str(tmp_path))
    monkeypatch.setattr(eval_source_quality, "review_source_with_llm", reviewer)
    monkeypatch.setattr(sys, "argv", [
        "eval_source_quality.py", "--track", "demo", "--source", "Example", "--today", "2026-11-20",
        "--artifact-path", str(artifact), "--output", str(output), "--reviewer", reviewer_mode,
    ])

    assert eval_source_quality.main() == 1
    payload = json.loads(output.read_text())
    assert reviewer.call_count == (reviewer_mode == "auto")
    assert payload["final_status"] == payload["verification"] == "inconclusive"
    assert payload["integration_ticket"] is None
    detail = payload["deterministic"]["description_coverage"]
    assert detail["usable"] == detail["demonstrated_omissions"] == 0
    assert detail["sampled_pages_unavailable"] == 1
