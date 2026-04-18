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
