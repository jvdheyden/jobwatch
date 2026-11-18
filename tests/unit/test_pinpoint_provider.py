from __future__ import annotations

import pytest

from discover import http
from discover.core import SourceConfig
from discover.sources import pinpoint

# Mirrors the real Pinpoint `/postings.json` feed: a `data` list with HTML
# description sections and nested job department/division objects.
POSTINGS_PAYLOAD = {
    "data": [
        {
            "id": "379752",
            "title": "Data Product Developer",
            "url": "https://inmusicbrands.pinpointhq.com/en/postings/58b39ffe-661a-40ef-85f7-40dcb6fb6bc4",
            "description": "<div><!--block-->Shape the product roadmap for our music software.</div>",
            "key_responsibilities": "<ul><li><!--block-->Work with the product manager on data tooling.</li></ul>",
            "skills_knowledge_expertise": "",
            "benefits": "<ul><li>Private healthcare</li></ul>",
            "employment_type_text": "Full Time",
            "workplace_type_text": "Hybrid",
            "job": {
                "department": {"id": "1", "name": "Engineering"},
                "division": {"id": "2", "name": "inMusic Europe Limited"},
            },
            "location": {"id": "3", "name": "Berlin, Germany", "city": "Berlin"},
        },
        {
            "id": "379753",
            "title": "UK Planner",
            "url": "https://inmusicbrands.pinpointhq.com/en/postings/aa",
            "description": "<p>Plan stock levels.</p>",
            "job": {"department": {"name": "Operations"}},
            "location": {"name": "Ash Vale, UK"},
        },
    ]
}


def _source() -> SourceConfig:
    return SourceConfig(
        source="iZotope / Native Instruments",
        url="https://inmusicbrands.pinpointhq.com/",
        discovery_mode="pinpoint_api",
        last_checked=None,
        cadence_group="every_run",
    )


def test_matches_description_text_and_keeps_posting_url(monkeypatch):
    requested: list[str] = []

    def fake_fetch_json(url: str, timeout_seconds: int, headers=None):
        del timeout_seconds, headers
        requested.append(url)
        return POSTINGS_PAYLOAD

    monkeypatch.setattr(http, "fetch_json", fake_fetch_json)

    coverage = pinpoint.discover_pinpoint_api(_source(), ["product manager"], 5)

    assert requested == ["https://inmusicbrands.pinpointhq.com/postings.json"]
    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 2
    [candidate] = coverage.candidates
    assert candidate.title == "Data Product Developer"
    assert candidate.url == "https://inmusicbrands.pinpointhq.com/en/postings/58b39ffe-661a-40ef-85f7-40dcb6fb6bc4"
    assert candidate.location == "Berlin, Germany"
    assert "Division: inMusic Europe Limited" in candidate.notes
    assert "Work with the product manager on data tooling." in candidate.description
    assert "<li>" not in candidate.description


def test_unexpected_feed_shape_raises_instead_of_reading_as_empty(monkeypatch):
    monkeypatch.setattr(http, "fetch_json", lambda url, timeout_seconds, headers=None: {"error": "maintenance"})

    with pytest.raises(ValueError, match="data"):
        pinpoint.discover_pinpoint_api(_source(), ["product manager"], 5)


def test_empty_data_list_is_a_complete_empty_board(monkeypatch):
    monkeypatch.setattr(http, "fetch_json", lambda url, timeout_seconds, headers=None: {"data": []})

    coverage = pinpoint.discover_pinpoint_api(_source(), ["product manager"], 5)

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 0


def test_postings_without_url_use_path_or_are_flagged(monkeypatch):
    base = POSTINGS_PAYLOAD["data"][0]
    payload = {
        "data": [
            base | {"id": "1", "url": "", "path": "/en/postings/from-path"},
            base | {"id": "2", "url": "", "path": "", "title": "Product Manager"},
        ]
    }
    monkeypatch.setattr(http, "fetch_json", lambda url, timeout_seconds, headers=None: payload)

    coverage = pinpoint.discover_pinpoint_api(_source(), ["product manager"], 5)

    assert [candidate.url for candidate in coverage.candidates] == [
        "https://inmusicbrands.pinpointhq.com/en/postings/from-path"
    ]
    assert coverage.status == "partial"
    assert coverage.limitations == ["1 matching Pinpoint posting(s) had no posting URL or path and were skipped."]
