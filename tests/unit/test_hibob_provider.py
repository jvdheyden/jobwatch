from __future__ import annotations

from discover import http
from discover.core import SourceConfig
from discover.sources import hibob

# Mirrors the real HiBob `/api/job-ad` response: a curated list of published
# postings, each with pre-split description/requirements/responsibilities HTML.
JOB_AD_PAYLOAD = {
    "filterGroups": {"sites": [{"serverId": "1", "value": "New York Studio"}]},
    "jobAdDetails": [
        {
            "id": "78fb36c8-f210-4f63-ab28-2b697571755e",
            "title": "Growth Principal",
            "department": "Growth",
            "site": "New York Studio",
            "country": "United States",
            "workspaceType": "Hybrid",
            "description": "<p>Lead growth for the New York studio.</p>",
            "requirements": "<ul><li>10+ years experience</li></ul>",
        },
        {
            "id": "b8547f85-ccc9-4dcf-ac6b-f6d954f0ed28",
            "title": "Senior Product Manager",
            "department": "Strategy",
            "site": "London Studio",
            "country": "United Kingdom",
            "workspaceType": "Hybrid",
            "description": "<p>Own client product outcomes end to end.</p>",
        },
    ],
}


def _source() -> SourceConfig:
    return SourceConfig(
        source="ustwo",
        url="https://ustwo.careers.hibob.com",
        discovery_mode="hibob_api",
        last_checked=None,
        cadence_group="every_3_runs",
        source_id="ustwo",
    )


def test_company_identifier_from_subdomain():
    assert hibob.hibob_company_identifier("https://ustwo.careers.hibob.com") == "ustwo"


def test_hibob_provider_enumerates_all_postings_and_keeps_term_matches(monkeypatch):
    captured: dict[str, object] = {}

    def fake_fetch_json(url, timeout_seconds, headers=None):
        captured["url"] = url
        captured["headers"] = headers
        return JOB_AD_PAYLOAD

    monkeypatch.setattr(http, "fetch_json", fake_fetch_json)

    coverage = hibob.discover_hibob_api(_source(), ["product manager"], timeout_seconds=5)

    # The endpoint is derived from the source host and carries the required header.
    assert captured["url"] == "https://ustwo.careers.hibob.com/api/job-ad"
    assert captured["headers"] == {"companyIdentifier": "ustwo"}

    # Every real posting is enumerated, but only term matches become candidates.
    assert coverage.enumerated_jobs == 2
    assert len(coverage.candidates) == 1
    assert coverage.matched_jobs == 1

    pm = coverage.candidates[0]
    assert pm.title == "Senior Product Manager"
    assert pm.url == "https://ustwo.careers.hibob.com/jobs/b8547f85-ccc9-4dcf-ac6b-f6d954f0ed28"
    assert pm.location == "London Studio, United Kingdom"
    assert pm.remote == "Hybrid"
    assert pm.matched_terms == ["product manager"]
    assert "end to end" in pm.description
