from __future__ import annotations

import discover_jobs
from discover import http as discover_http


def test_discover_greenhouse_api_populates_description_from_html_content(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Plain HTML Greenhouse",
        url="https://job-boards.greenhouse.io/example",
        discovery_mode="greenhouse_api",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    def fake_fetch_json(url: str, timeout_seconds: int):
        return {
            "jobs": [
                {
                    "title": "Security Engineer",
                    "absolute_url": "https://job-boards.greenhouse.io/example/jobs/1",
                    "location": {"name": "Remote"},
                    "content": (
                        "<p>Build applied cryptography systems for privacy products.</p>"
                        "<p>Security engineering experience required.</p>"
                    ),
                },
            ],
        }

    monkeypatch.setattr(discover_http, "fetch_json", fake_fetch_json)

    coverage = discover_jobs.discover_greenhouse_api(source, ["security", "cryptography"], timeout_seconds=5)

    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert "Build applied cryptography systems for privacy products." in candidate.description
    assert "Security engineering experience required." in candidate.description
    assert "<p>" not in candidate.description
    assert candidate.description_truncated is False


def test_discover_greenhouse_api_unescapes_html_entities_in_content(monkeypatch):
    """Greenhouse's API returns HTML-entity-encoded HTML; encoded tags must not survive into description."""
    source = discover_jobs.SourceConfig(
        source="Encoded Greenhouse",
        url="https://job-boards.greenhouse.io/example",
        discovery_mode="greenhouse_api",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    def fake_fetch_json(url: str, timeout_seconds: int):
        return {
            "jobs": [
                {
                    "title": "Security Engineer",
                    "absolute_url": "https://job-boards.greenhouse.io/example/jobs/42",
                    "location": {"name": "Remote"},
                    "content": (
                        "&lt;p&gt;Build applied cryptography systems for privacy products.&lt;/p&gt;"
                        "&lt;p&gt;Security engineering experience required.&lt;/p&gt;"
                    ),
                },
            ],
        }

    monkeypatch.setattr(discover_http, "fetch_json", fake_fetch_json)

    coverage = discover_jobs.discover_greenhouse_api(source, ["security", "cryptography"], timeout_seconds=5)

    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert "Build applied cryptography systems for privacy products." in candidate.description
    assert "<p>" not in candidate.description
    assert "&lt;" not in candidate.description
