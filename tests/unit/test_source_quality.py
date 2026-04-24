from __future__ import annotations

from pathlib import Path

import source_quality


def test_validate_source_coverage_flags_duplicate_and_missing_canary():
    source = {
        "source": "Example Source",
        "source_url": "https://jobs.example.com/search",
        "discovery_mode": "html",
        "enumerated_jobs": 2,
        "candidates": [
            {
                "employer": "Example Source",
                "title": "Security Engineer",
                "url": "https://jobs.example.com/jobs/123",
                "source_url": "https://jobs.example.com/search",
                "location": "Berlin",
                "notes": "Role note",
            },
            {
                "employer": "Example Source",
                "title": "Security Engineer",
                "url": "https://jobs.example.com/jobs/123",
                "source_url": "https://jobs.example.com/search",
                "location": "Berlin",
                "notes": "Role note",
            },
        ],
    }

    result = source_quality.validate_source_coverage(
        source,
        canary_title="Privacy Engineer",
        canary_url="https://jobs.example.com/jobs/999",
    )

    check_by_name = {check["name"]: check for check in result["checks"]}
    assert result["confidence"] == "failed"
    assert check_by_name["duplicate_jobs"]["status"] == "fail"
    assert check_by_name["canary_present"]["status"] == "fail"


def test_validate_source_coverage_allows_same_title_for_different_locations():
    source = {
        "source": "Example Source",
        "source_url": "https://jobs.example.com/search",
        "discovery_mode": "html",
        "enumerated_jobs": 2,
        "candidates": [
            {
                "employer": "Example Source",
                "title": "Research Engineer",
                "url": "https://jobs.example.com/jobs/berlin",
                "source_url": "https://jobs.example.com/search",
                "location": "Berlin",
                "notes": "Tasks: Build applied cryptography prototypes for privacy-preserving systems. Profile: Python and MPC research background.",
            },
            {
                "employer": "Example Source",
                "title": "Research Engineer",
                "url": "https://jobs.example.com/jobs/cologne",
                "source_url": "https://jobs.example.com/search",
                "location": "Cologne",
                "notes": "Tasks: Build applied cryptography prototypes for privacy-preserving systems. Profile: Python and MPC research background.",
            },
        ],
    }

    result = source_quality.validate_source_coverage(source, canary_title="", canary_url="")
    check_by_name = {check["name"]: check for check in result["checks"]}

    assert check_by_name["duplicate_jobs"]["status"] == "pass"
    assert result["confidence"] == "high"


def test_validate_source_coverage_rejects_browser_fallback_when_only_card_level_metadata_is_present():
    source = {
        "source": "Example Source",
        "source_url": "https://jobs.example.com/search",
        "discovery_mode": "browser",
        "enumerated_jobs": 1,
        "candidates": [
            {
                "employer": "Example Source",
                "title": "Privacy Engineer",
                "url": "https://jobs.example.com/jobs/123",
                "source_url": "https://jobs.example.com/search",
                "location": "Menlo Park, CA",
                "notes": "Meta browser search q='privacy' page=1",
            }
        ],
    }

    result = source_quality.validate_source_coverage(
        source,
        canary_title="Privacy Engineer",
        canary_url="https://jobs.example.com/jobs/123",
        raw_text_fetcher=lambda _url, _timeout: "<html><body>Privacy Engineer</body></html>",
    )

    check_by_name = {check["name"]: check for check in result["checks"]}
    assert check_by_name["detail_depth"]["status"] == "warn"
    assert check_by_name["browser_fallback_quality"]["status"] == "fail"
    assert result["confidence"] == "failed"


def test_validate_source_coverage_fails_when_raw_pages_show_dropped_detail():
    source = {
        "source": "Example Source",
        "source_url": "https://jobs.example.com/search",
        "discovery_mode": "browser",
        "enumerated_jobs": 1,
        "candidates": [
            {
                "employer": "Example Source",
                "title": "Privacy Engineer",
                "url": "https://jobs.example.com/jobs/123",
                "source_url": "https://jobs.example.com/search",
                "location": "Menlo Park, CA",
                "notes": "Meta browser search q='privacy' page=1",
            }
        ],
    }

    result = source_quality.validate_source_coverage(
        source,
        canary_title="Privacy Engineer",
        canary_url="https://jobs.example.com/jobs/123",
        raw_text_fetcher=lambda _url, _timeout: """
        <html><body>
        <h2>Responsibilities</h2>
        <p>Build privacy-preserving systems.</p>
        <h2>Minimum Qualifications</h2>
        <p>Experience with applied cryptography.</p>
        </body></html>
        """,
    )

    check_by_name = {check["name"]: check for check in result["checks"]}
    assert check_by_name["detail_depth"]["status"] == "fail"
    assert result["confidence"] == "failed"


def test_build_integration_ticket_prefers_blocking_deterministic_failure():
    source = {
        "source": "Example Source",
        "discovery_mode": "html",
    }
    deterministic = {
        "confidence": "failed",
        "checks": [
            {
                "name": "listing_kind",
                "status": "fail",
                "severity": "blocking",
                "details": "All surfaced candidates look like navigation or non-job content.",
            }
        ],
        "warnings": [],
    }
    reviewer = {
        "status": "completed",
        "defects": [
            {
                "type": "navigation_noise",
                "severity": "blocking",
                "observed": "The extracted titles are category links.",
                "integration_hint": "Parse job cards instead of footer links.",
            }
        ],
    }

    ticket = source_quality.build_integration_ticket(
        "public_service",
        source,
        deterministic,
        reviewer,
        canary_title="Canary Role",
        canary_url="https://example.com/jobs/1",
    )

    assert ticket is not None
    assert ticket["summary"] == "All surfaced candidates look like navigation or non-job content."
    assert ticket["defect_types"] == ["listing_kind"]
    assert ticket["failure_mode"] == "candidate_noise"
    assert ticket["primary_evidence"][0] == "listing_kind: All surfaced candidates look like navigation or non-job content."
    assert ticket["target_outcome"].startswith("Fresh discovery artifact removes implausible candidates")
    assert ticket["suggested_strategy"] == "dedicated_provider_logic"
    assert ticket["test_hint"] == ""
    assert ticket["likely_file"] == "scripts/discover/sources/generic_html.py"


def test_build_integration_ticket_maps_reviewer_only_other_noise_to_candidate_noise():
    source = {
        "source": "IBM Research",
        "discovery_mode": "ibm_api",
    }
    deterministic = {
        "confidence": "low",
        "checks": [],
        "warnings": [],
    }
    reviewer = {
        "status": "completed",
        "defects": [
            {
                "type": "other",
                "severity": "major",
                "observed": "Quantum hardware role is not plausibly aligned with the postdoc cryptography track terms.",
                "integration_hint": "",
            },
            {
                "type": "other",
                "severity": "major",
                "observed": "Intern role is not a postdoctoral/research role aligned with the target track.",
                "integration_hint": "",
            },
        ],
    }

    ticket = source_quality.build_integration_ticket(
        "postdoc_crypto",
        source,
        deterministic,
        reviewer,
        canary_title="Postdoctoral IT Research Scientist - IBM Research South Africa",
        canary_url="https://careers.ibm.com/careers/JobDetail?jobId=107245",
    )

    assert ticket is not None
    assert ticket["failure_mode"] == "candidate_noise"
    assert ticket["suggested_strategy"] == "dedicated_provider_logic"
    assert ticket["test_hint"] == "tests/integration/test_discover_followup_sources.py"
    assert any("not plausibly aligned" in evidence for evidence in ticket["primary_evidence"])
    assert "Preserve the canary" in ticket["target_outcome"]


def test_build_integration_ticket_distinguishes_config_native_filters_for_high_volume():
    source = {
        "source": "Example Browser",
        "source_url": "https://jobs.example.com/search",
        "discovery_mode": "browser",
        "status": "complete",
        "search_terms_tried": ["security"],
        "enumerated_jobs": 250,
        "matched_jobs": 80,
        "result_pages_scanned": "page=1",
        "direct_job_pages_opened": 1,
        "candidates": [
            {
                "employer": "Example",
                "title": f"Role {index}",
                "url": f"https://jobs.example.com/jobs/{index}",
                "source_url": "https://jobs.example.com/search",
                "location": "Berlin",
                "notes": "Tasks: Build applied privacy systems. Profile: security engineering.",
            }
            for index in range(source_quality.HIGH_VOLUME_CANDIDATE_THRESHOLD + 1)
        ],
    }
    deterministic = source_quality.validate_source_coverage(source)

    ticket = source_quality.build_integration_ticket(
        "demo",
        source,
        deterministic,
        {"status": "skipped", "defects": []},
        canary_title="",
        canary_url="",
    )

    assert ticket is not None
    assert ticket["failing_checks"] == ["result_volume"]
    assert ticket["suggested_strategy"] == "config_native_filters"
    assert ticket["candidate_counts"]["candidates"] == source_quality.HIGH_VOLUME_CANDIDATE_THRESHOLD + 1


def test_build_integration_ticket_distinguishes_provider_filter_support_when_filters_exist():
    source = {
        "source": "Example Browser",
        "source_url": "https://jobs.example.com/search",
        "discovery_mode": "browser",
        "status": "complete",
        "search_terms_tried": ["security"],
        "filters": {"location": ["Berlin, Germany"]},
        "enumerated_jobs": 250,
        "matched_jobs": 80,
        "result_pages_scanned": "page=1",
        "direct_job_pages_opened": 1,
        "candidates": [
            {
                "employer": "Example",
                "title": f"Role {index}",
                "url": f"https://jobs.example.com/jobs/{index}",
                "source_url": "https://jobs.example.com/search",
                "location": "Berlin",
                "notes": "Tasks: Build applied privacy systems. Profile: security engineering.",
            }
            for index in range(source_quality.HIGH_VOLUME_CANDIDATE_THRESHOLD + 1)
        ],
    }
    deterministic = source_quality.validate_source_coverage(source)

    ticket = source_quality.build_integration_ticket(
        "demo",
        source,
        deterministic,
        {"status": "skipped", "defects": []},
        canary_title="",
        canary_url="",
    )

    assert ticket is not None
    assert ticket["suggested_strategy"] == "provider_filter_support"
    assert ticket["configured_filters"] == {"location": ["Berlin, Germany"]}


def test_build_reviewer_context_shares_all_candidates_when_under_cap():
    source = {
        "source": "Example Source",
        "source_url": "https://jobs.example.com/search",
        "discovery_mode": "html",
        "status": "complete",
        "search_terms_tried": ["security"],
        "candidates": [
            {
                "employer": "Example Source",
                "title": f"Role {index}",
                "url": f"https://jobs.example.com/jobs/{index}",
                "source_url": "https://jobs.example.com/search",
                "location": "Berlin",
                "notes": f"Tasks: Example role {index}.",
            }
            for index in range(3)
        ],
    }

    context = source_quality._build_reviewer_context(
        Path("artifacts/discovery/public_service/2026-04-02.json"),
        source,
        canary_title="",
        canary_url="",
        timeout_seconds=5,
        raw_text_fetcher=lambda url, _timeout: f"<html><body>{url}</body></html>",
    )

    assert context["source"]["candidate_count_total"] == 3
    assert context["source"]["candidate_count_shared"] == 3
    assert context["source"]["candidate_context_truncated"] is False
    assert [candidate["title"] for candidate in context["source"]["candidates"]] == ["Role 0", "Role 1", "Role 2"]
    assert [sample["url"] for sample in context["raw_samples"]] == [
        "https://jobs.example.com/jobs/0",
        "https://jobs.example.com/jobs/1",
        "https://jobs.example.com/jobs/2",
    ]


def test_build_reviewer_context_caps_candidates_and_marks_truncation():
    source = {
        "source": "Example Source",
        "source_url": "https://jobs.example.com/search",
        "discovery_mode": "html",
        "status": "complete",
        "search_terms_tried": ["security"],
        "candidates": [
            {
                "employer": "Example Source",
                "title": f"Role {index}",
                "url": f"https://jobs.example.com/jobs/{index}",
                "source_url": "https://jobs.example.com/search",
                "location": "Berlin",
                "notes": f"Tasks: Example role {index}.",
            }
            for index in range(source_quality.REVIEWER_MAX_CANDIDATES + 2)
        ],
    }

    context = source_quality._build_reviewer_context(
        Path("artifacts/discovery/public_service/2026-04-02.json"),
        source,
        canary_title="",
        canary_url="",
        timeout_seconds=5,
        raw_text_fetcher=lambda url, _timeout: f"<html><body>{url}</body></html>",
    )

    assert context["source"]["candidate_count_total"] == source_quality.REVIEWER_MAX_CANDIDATES + 2
    assert context["source"]["candidate_count_shared"] == source_quality.REVIEWER_MAX_CANDIDATES
    assert context["source"]["candidate_context_truncated"] is True
    assert [candidate["title"] for candidate in context["source"]["candidates"]] == [
        f"Role {index}" for index in range(source_quality.REVIEWER_MAX_CANDIDATES)
    ]


def test_build_reviewer_context_includes_canary_candidate_outside_cap():
    canary_index = source_quality.REVIEWER_MAX_CANDIDATES + 1
    source = {
        "source": "Example Source",
        "source_url": "https://jobs.example.com/search",
        "discovery_mode": "html",
        "status": "complete",
        "search_terms_tried": ["security"],
        "candidates": [
            {
                "employer": "Example Source",
                "title": f"Role {index}",
                "url": f"https://jobs.example.com/jobs/{index}",
                "source_url": "https://jobs.example.com/search",
                "location": "Berlin",
                "notes": f"Tasks: Example role {index}.",
            }
            for index in range(source_quality.REVIEWER_MAX_CANDIDATES + 2)
        ],
    }

    context = source_quality._build_reviewer_context(
        Path("artifacts/discovery/public_service/2026-04-02.json"),
        source,
        canary_title=f"Role {canary_index}",
        canary_url=f"https://jobs.example.com/jobs/{canary_index}",
        timeout_seconds=5,
        raw_text_fetcher=lambda url, _timeout: f"<html><body>{url}</body></html>",
    )

    titles = [candidate["title"] for candidate in context["source"]["candidates"]]
    raw_sample_urls = [sample["url"] for sample in context["raw_samples"]]

    assert len(titles) == source_quality.REVIEWER_MAX_CANDIDATES
    assert f"Role {canary_index}" in titles
    assert f"Role {source_quality.REVIEWER_MAX_CANDIDATES - 1}" not in titles
    assert raw_sample_urls[0] == f"https://jobs.example.com/jobs/{canary_index}"


def test_build_reviewer_command_forces_low_reasoning_effort():
    command = source_quality.build_reviewer_command(
        Path("/tmp/jobwatch"),
        Path("/usr/local/bin/codex"),
    )

    assert command == [
        "/usr/local/bin/codex",
        "--search",
        "-a",
        "never",
        "exec",
        "-c",
        'model_reasoning_effort="low"',
        "-C",
        "/tmp/jobwatch",
        "-s",
        "read-only",
        "-",
    ]


def test_build_reviewer_command_supports_claude_print_mode(monkeypatch):
    monkeypatch.setenv("JOB_AGENT_CLAUDE_PERMISSION_MODE", "acceptEdits")
    monkeypatch.delenv("JOB_AGENT_CLAUDE_REVIEWER_ALLOWED_TOOLS", raising=False)

    command = source_quality.build_reviewer_command(
        Path("/tmp/jobwatch"),
        Path("/usr/local/bin/claude"),
        provider="claude",
    )

    assert command == [
        "/usr/local/bin/claude",
        "-p",
        "--no-session-persistence",
        "--output-format",
        "text",
        "--permission-mode",
        "acceptEdits",
        "--allowedTools",
        "Read,Glob,Grep,LS",
    ]


def test_build_reviewer_command_supports_gemini_headless_mode(monkeypatch):
    monkeypatch.delenv("JOB_AGENT_GEMINI_REVIEWER_APPROVAL_MODE", raising=False)

    command = source_quality.build_reviewer_command(
        Path("/tmp/jobwatch"),
        Path("/usr/local/bin/gemini"),
        provider="gemini",
    )

    assert command == [
        "/usr/local/bin/gemini",
        "--skip-trust",
        "--output-format",
        "text",
    ]


def test_review_source_with_llm_ignores_empty_canary_and_normalizes_message_fields(monkeypatch):
    source = {
        "source": "Example Source",
        "source_url": "https://jobs.example.com/search",
        "discovery_mode": "html",
        "status": "complete",
        "search_terms_tried": ["security"],
        "candidates": [],
    }

    monkeypatch.setattr(
        source_quality,
        "_build_reviewer_context",
        lambda *_args, **_kwargs: {"source": {"source": "Example Source"}, "canary": {"title": "", "url": ""}, "raw_samples": []},
    )

    class Completed:
        returncode = 0
        stdout = """
{"defects":[
  {"type":"canary_missing","severity":"blocking","message":"ignore this"},
  {"type":"partial_description","severity":"major","message":"No descriptive notes were extracted.","path":"raw_samples"}
]}
"""
        stderr = ""

    monkeypatch.setattr(source_quality.subprocess, "run", lambda *args, **kwargs: Completed())

    reviewer = source_quality.review_source_with_llm(
        Path("/tmp/jobwatch"),
        Path("artifacts/discovery/public_service/2026-04-02.json"),
        source,
        canary_title="",
        canary_url="",
        reviewer_bin=Path("/bin/bash"),
        timeout_seconds=5,
    )

    assert reviewer["status"] == "completed"
    assert reviewer["defects"] == [
        {
            "type": "partial_description",
            "severity": "major",
            "source": "Example Source",
            "candidate_url": "",
            "canary_title": "",
            "observed": "No descriptive notes were extracted.",
            "expected": "",
            "integration_hint": "",
            "repro_step": "raw_samples",
        }
    ]
