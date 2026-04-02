from __future__ import annotations

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
