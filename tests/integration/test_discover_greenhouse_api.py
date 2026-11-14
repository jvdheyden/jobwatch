from __future__ import annotations

import pytest

import discover_jobs
from discover import http as discover_http


@pytest.mark.parametrize(
    ("terms", "expected_matches"),
    [
        (["cryptography"], 0),
        (["cryptography", "privacy"], 1),
        (["privacy"], 1),
    ],
)
def test_greenhouse_coverage_is_complete_even_when_configured_terms_match_nothing(
    monkeypatch, terms, expected_matches
):
    source = discover_jobs.SourceConfig(
        source="Example Greenhouse",
        url="https://job-boards.greenhouse.io/example",
        discovery_mode="greenhouse_api",
        last_checked=None,
        cadence_group="every_run",
    )
    monkeypatch.setattr(
        discover_http,
        "fetch_json",
        lambda url, timeout_seconds: {
            "jobs": [{
                "title": "Software Engineer",
                "absolute_url": "https://job-boards.greenhouse.io/example/jobs/1",
                "location": {"name": "Remote"},
                "content": "<p>Build privacy engineering tools and data protection systems.</p>",
            }],
        },
    )

    coverage = discover_jobs.discover_greenhouse_api(source, terms, timeout_seconds=5)

    assert coverage.status == "complete"
    assert coverage.search_terms_tried == terms
    assert coverage.enumerated_jobs == 1
    assert coverage.matched_jobs == expected_matches
    assert len(coverage.candidates) == expected_matches
    if expected_matches:
        assert coverage.candidates[0].matched_terms == ["privacy"]


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


def test_discover_greenhouse_api_admits_configured_management_and_legal_titles(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Example Greenhouse",
        url="https://job-boards.greenhouse.io/example",
        discovery_mode="greenhouse_api",
        last_checked=None,
        cadence_group="every_3_runs",
    )
    titles = ["Engineering Manager", "Marketing Manager", "Legal Counsel"]

    monkeypatch.setattr(
        discover_http,
        "fetch_json",
        lambda url, timeout_seconds: {
            "jobs": [
                {
                    "title": title,
                    "absolute_url": f"https://job-boards.greenhouse.io/example/jobs/{index}",
                    "location": {"name": "Remote"},
                    "content": f"<p>Responsibilities for the {title} role.</p>",
                }
                for index, title in enumerate(titles)
            ]
        },
    )

    coverage = discover_jobs.discover_greenhouse_api(
        source,
        ["engineering manager", "marketing manager", "legal counsel"],
        timeout_seconds=5,
    )

    assert {candidate.title for candidate in coverage.candidates} == set(titles)
