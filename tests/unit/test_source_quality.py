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


def test_validate_source_coverage_warns_when_only_card_level_metadata_is_present():
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
    assert result["confidence"] == "low"


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


def test_build_repair_ticket_prefers_blocking_deterministic_failure():
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
                "repair_hint": "Parse job cards instead of footer links.",
            }
        ],
    }

    ticket = source_quality.build_repair_ticket(
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
    assert ticket["likely_file"] == "scripts/discover_jobs.py"


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
