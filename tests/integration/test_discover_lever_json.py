from __future__ import annotations

import discover_jobs
from discover import http as discover_http


def test_discover_lever_json_filters_and_deduplicates(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Example Lever",
        url="https://jobs.lever.co/example",
        discovery_mode="lever_json",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    def fake_fetch_json(url: str, timeout_seconds: int):
        assert url == "https://api.lever.co/v0/postings/example?mode=json"
        assert timeout_seconds == 5
        return [
            {
                "text": "Security Engineer",
                "hostedUrl": "https://jobs.lever.co/example/security-engineer",
                "descriptionPlain": "Build security and applied cryptography systems.",
                "categories": {"team": "Engineering", "location": "Remote"},
            },
            {
                "text": "Security Engineer",
                "hostedUrl": "https://jobs.lever.co/example/security-engineer",
                "descriptionPlain": "Build protocol security systems.",
                "categories": {"team": "Engineering", "location": "Remote"},
            },
            {
                "text": "Product Marketing Manager",
                "hostedUrl": "https://jobs.lever.co/example/marketing",
                "descriptionPlain": "Campaign planning.",
                "categories": {"team": "Marketing", "location": "Remote"},
            },
        ]

    monkeypatch.setattr(discover_http, "fetch_json", fake_fetch_json)

    coverage = discover_jobs.discover_lever_json(source, ["security", "cryptography"], timeout_seconds=5)

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 3
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.title == "Security Engineer"
    assert candidate.url == "https://jobs.lever.co/example/security-engineer"
    assert candidate.location == "Remote"
    assert candidate.matched_terms == ["cryptography", "security"]
    assert candidate.notes == (
        "Description: Build security and applied cryptography systems.; "
        "Description: Build protocol security systems."
    )
    assert candidate.description == (
        "Build security and applied cryptography systems. "
        "Build protocol security systems."
    )
    assert candidate.description_truncated is False


def test_discover_lever_json_admits_configured_role_and_domain_terms(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Example Lever",
        url="https://jobs.lever.co/example",
        discovery_mode="lever_json",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    monkeypatch.setattr(
        discover_http,
        "fetch_json",
        lambda url, timeout_seconds: [
            {
                "text": "Product Manager",
                "hostedUrl": "https://jobs.lever.co/example/product-manager",
                "descriptionPlain": "Own the roadmap and product strategy.",
                "categories": {"team": "Product", "location": "Remote"},
            },
            {
                "text": "Office Coordinator",
                "hostedUrl": "https://jobs.lever.co/example/office-coordinator",
                "descriptionPlain": "Support a team building applied cryptography systems.",
                "categories": {"team": "Operations", "location": "Remote"},
            },
            {
                "text": "Customer Support Associate",
                "hostedUrl": "https://jobs.lever.co/example/support",
                "descriptionPlain": "Help customers use the service.",
                "categories": {"team": "Support", "location": "Remote"},
            },
        ],
    )

    coverage = discover_jobs.discover_lever_json(
        source,
        ["product manager", "cryptography"],
        timeout_seconds=5,
    )

    assert {candidate.title for candidate in coverage.candidates} == {
        "Product Manager",
        "Office Coordinator",
    }
    by_title = {candidate.title: candidate for candidate in coverage.candidates}
    assert by_title["Product Manager"].matched_terms == ["product manager"]
    assert by_title["Office Coordinator"].matched_terms == ["cryptography"]
