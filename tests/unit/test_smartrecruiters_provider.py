from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from discover import http
from discover.core import SourceConfig
from discover.sources import smartrecruiters


def _posting(posting_id: str, name: str, *, remote: bool = False, hybrid: bool = False) -> dict:
    # Mirrors the real `/v1/companies/<id>/postings` list item shape.
    return {
        "id": posting_id,
        "name": name,
        "company": {"identifier": "Canva", "name": "Canva"},
        "location": {
            "city": "Sydney",
            "country": "au",
            "remote": remote,
            "hybrid": hybrid,
            "fullLocation": "Sydney, , Australia",
        },
        "function": {"id": "product_management", "label": "Product Management"},
        "department": {},
        "typeOfEmployment": {"id": "permanent", "label": "Full-time"},
        "experienceLevel": {"id": "mid_senior_level", "label": "Mid-Senior Level"},
        "customField": [{"fieldLabel": "Org", "valueLabel": "Product"}],
    }


def _source() -> SourceConfig:
    return SourceConfig(
        source="Canva",
        url="https://careers.smartrecruiters.com/Canva",
        discovery_mode="smartrecruiters_api",
        last_checked=None,
        cadence_group="every_run",
    )


def _install_pages(monkeypatch, pages: list[list[dict]], total: int) -> list[str]:
    requested: list[str] = []

    def fake_fetch_json(url: str, timeout_seconds: int, headers=None):
        del timeout_seconds, headers
        requested.append(url)
        offset = int(parse_qs(urlparse(url).query)["offset"][0])
        index = offset // smartrecruiters.PAGE_SIZE
        content = pages[index] if index < len(pages) else []
        return {"offset": offset, "limit": smartrecruiters.PAGE_SIZE, "totalFound": total, "content": content}

    monkeypatch.setattr(http, "fetch_json", fake_fetch_json)
    return requested


def test_pages_through_all_postings_and_builds_public_job_urls(monkeypatch):
    first_page = [_posting(str(6000000000 + i), f"Legal Counsel {i}") for i in range(smartrecruiters.PAGE_SIZE)]
    second_page = [_posting("6000000001473739", "Product Manager, CJKI", hybrid=True)]
    requested = _install_pages(monkeypatch, [first_page, second_page], total=101)

    coverage = smartrecruiters.discover_smartrecruiters_api(_source(), ["product manager"], 5)

    assert [parse_qs(urlparse(url).query)["offset"] for url in requested] == [["0"], ["100"]]
    assert urlparse(requested[0]).path == "/v1/companies/Canva/postings"
    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 101
    assert coverage.listing_pages_scanned == 2
    [candidate] = coverage.candidates
    assert candidate.title == "Product Manager, CJKI"
    assert candidate.url == "https://jobs.smartrecruiters.com/Canva/6000000001473739-product-manager-cjki"
    assert candidate.location == "Sydney, Australia"
    assert candidate.remote == "hybrid"
    assert "Function: Product Management" in candidate.notes


def test_reports_partial_when_page_cap_stops_enumeration(monkeypatch):
    full_page = [_posting(str(i), "Engineer") for i in range(smartrecruiters.PAGE_SIZE)]
    monkeypatch.setattr(smartrecruiters, "MAX_PAGES", 2)
    _install_pages(monkeypatch, [full_page, full_page, full_page], total=300)

    coverage = smartrecruiters.discover_smartrecruiters_api(_source(), ["product manager"], 5)

    assert coverage.status == "partial"
    assert coverage.enumerated_jobs == 200
    assert coverage.limitations == [
        "SmartRecruiters reported 300 postings but 200 were enumerated within 2 page(s) of 100."
    ]


def test_derives_company_identifier_from_jobs_host():
    assert smartrecruiters.smartrecruiters_company_id("https://jobs.smartrecruiters.com/Canva/") == "Canva"
