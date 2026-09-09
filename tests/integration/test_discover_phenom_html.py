from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

from discover import http
from discover.constants import JD_DESCRIPTION_CHAR_BUDGET
from discover.core import SourceConfig, discover_source
from discover.sources.phenom import (
    PHENOM_MAX_PAGES_PER_TERM,
    build_phenom_job_url,
    build_phenom_search_url,
    discover_phenom_html,
    extract_phenom_search_payload,
)


SCOPED_SOURCE_URL = "https://careers.bcg.com/global/en/search-results?keywords=BCG%20X"


def _source(url: str = SCOPED_SOURCE_URL) -> SourceConfig:
    return SourceConfig(
        source="BCG X",
        url=url,
        discovery_mode="phenom_html",
        last_checked=None,
        cadence_group="every_run",
    )


def _job(job_id: str, title: str, teaser: str, **extra: object) -> dict[str, object]:
    return {
        "jobId": job_id,
        "reqId": job_id,
        "jobSeqNo": f"BCG1US{job_id}EXTERNALENGLOBAL",
        "title": title,
        "location": "London, United Kingdom",
        "category": "Product Management",
        "descriptionTeaser": teaser,
        "ml_skills": [],
        **extra,
    }


def _search_page(jobs: list[dict[str, object]], *, hits: int | None = None, total: int | None = None) -> str:
    payload = {
        "eagerLoadRefineSearch": {
            "hits": len(jobs) if hits is None else hits,
            "totalHits": len(jobs) if total is None else total,
            "data": {"jobs": jobs},
        }
    }
    return f"<html><body><script>phApp.ddo = {json.dumps(payload)};</script></body></html>"


def _detail_page(description: str) -> str:
    payload = {"jobDetail": {"data": {"job": {"description": description}}}}
    return f"<html><body><nav>Careers home</nav><script>phApp.ddo = {json.dumps(payload)};</script></body></html>"


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query)


def test_phenom_html_scopes_url_keywords_paginates_and_enriches(monkeypatch):
    product_builder = _job(
        "58305",
        "(Senior) AI Factory Product Builder, London - BCG X",
        "Seeking an AI Factory Product Builder to design AI-enabled products.",
    )
    security_engineer = _job(
        "57948",
        "Global IT Director - Principal Security Engineer",
        "Lead enterprise-wide IAM capabilities.",
        category="Technology and Engineering",
    )
    us_product_builder = _job(
        "57679",
        "(Senior) AI Factory Product Builder, United States - BCG X",
        "Build AI tools for consulting teams.",
        location="Boston, Massachusetts, United States of America",
    )
    fetched_urls: list[str] = []

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        assert timeout_seconds == 5
        fetched_urls.append(url)
        if "/job/58305/" in url:
            return _detail_page("<p>Design and deploy <b>AI-enabled</b> products.</p>")
        if "/job/57679/" in url:
            return "<html><body><h1>Product Builder</h1><p>Detail page without an embedded payload.</p></body></html>"
        keywords = _query(url)["keywords"][0]
        offset = _query(url).get("from", ["0"])[0]
        if keywords == "BCG X product builder":
            if offset == "0":
                return _search_page([product_builder, security_engineer], hits=2, total=3)
            return _search_page([us_product_builder], hits=1, total=3)
        if keywords == "BCG X security":
            return _search_page([security_engineer])
        raise AssertionError(f"unexpected search: {url}")

    monkeypatch.setattr(http, "fetch_text", fake_fetch_text)

    coverage = discover_phenom_html(_source(), ["product builder", "security"], 5)

    assert coverage.status == "complete"
    assert coverage.listing_pages_scanned == 3
    assert coverage.result_pages_scanned == "BCG X product builder=2p/3of3, BCG X security=1p/1of1"
    assert coverage.enumerated_jobs == 3
    assert coverage.matched_jobs == 2
    assert coverage.direct_job_pages_opened == 2

    search_urls = [url for url in fetched_urls if "/search-results" in url]
    assert [_query(url)["keywords"] for url in search_urls] == [
        ["BCG X product builder"],
        ["BCG X product builder"],
        ["BCG X security"],
    ]
    assert _query(search_urls[0]).get("from") is None
    assert _query(search_urls[1])["from"] == ["2"]
    assert "s" not in _query(search_urls[1])

    by_url = {candidate.url: candidate for candidate in coverage.candidates}
    london = by_url["https://careers.bcg.com/global/en/job/58305/senior-ai-factory-product-builder-london-bcg-x"]
    assert london.employer == "BCG X"
    assert london.location == "London, United Kingdom"
    assert london.matched_terms == ["product builder"]
    assert london.description == "Design and deploy AI-enabled products."
    assert london.description_truncated is False
    assert "BCG X product builder" in london.notes
    boston = by_url["https://careers.bcg.com/global/en/job/57679/senior-ai-factory-product-builder-united-states-bcg-x"]
    assert boston.location == "Boston, Massachusetts, United States of America"
    assert boston.description == "Product Builder Detail page without an embedded payload."
    assert not any("/job/57948/" in url for url in by_url)


def test_phenom_html_without_url_keywords_searches_each_term_and_keeps_native_query(monkeypatch):
    fetched_urls: list[str] = []

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        fetched_urls.append(url)
        if "/job/" in url:
            return _detail_page("<p>Security role detail.</p>")
        return _search_page(
            [_job("57948", "Principal Security Engineer", "Lead IAM.", category="Technology and Engineering")]
        )

    monkeypatch.setattr(http, "fetch_text", fake_fetch_text)
    source = _source("https://careers.example.com/en/search-results?locale=en_US")

    coverage = discover_phenom_html(source, ["security", "privacy"], 5)

    search_urls = [url for url in fetched_urls if "/search-results" in url]
    assert [_query(url)["keywords"] for url in search_urls] == [["security"], ["privacy"]]
    assert all(_query(url)["locale"] == ["en_US"] for url in search_urls)
    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 1
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.url == "https://careers.example.com/en/job/57948/principal-security-engineer"
    assert candidate.matched_terms == ["security"]
    assert candidate.description == "Security role detail."


def test_phenom_html_stops_at_page_cap_and_reports_partial_coverage(monkeypatch):
    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        if "/job/" in url:
            return _detail_page("<p>Detail.</p>")
        offset = int(_query(url).get("from", ["0"])[0])
        jobs = [
            _job(str(1000 + offset + index), f"BCG X Product Lead {offset + index}", "Own the product roadmap.")
            for index in range(10)
        ]
        return _search_page(jobs, hits=10, total=100)

    monkeypatch.setattr(http, "fetch_text", fake_fetch_text)

    coverage = discover_phenom_html(_source(), ["product lead"], 5)

    assert coverage.status == "partial"
    assert coverage.listing_pages_scanned == PHENOM_MAX_PAGES_PER_TERM
    assert coverage.enumerated_jobs == PHENOM_MAX_PAGES_PER_TERM * 10
    assert coverage.matched_jobs == PHENOM_MAX_PAGES_PER_TERM * 10
    assert coverage.result_pages_scanned == f"BCG X product lead={PHENOM_MAX_PAGES_PER_TERM}p/50of100"
    assert coverage.limitations == [
        f"Phenom page cap of {PHENOM_MAX_PAGES_PER_TERM} pages per term reached for 1 of 1 searches"
    ]


def test_phenom_html_bounds_long_detail_descriptions(monkeypatch):
    long_description = "<p>" + " ".join(f"sentence{index}" for index in range(1200)) + "</p>"

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        if "/job/" in url:
            return _detail_page(long_description)
        return _search_page([_job("58305", "BCG X Product Manager", "Ship products.")])

    monkeypatch.setattr(http, "fetch_text", fake_fetch_text)

    coverage = discover_phenom_html(_source(), ["product manager"], 5)

    candidate = coverage.candidates[0]
    assert candidate.description_truncated is True
    assert len(candidate.description) <= JD_DESCRIPTION_CHAR_BUDGET
    assert candidate.description.startswith("sentence0 sentence1")


def test_phenom_html_missing_payload_and_detail_failures_are_limitations(monkeypatch):
    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        if "/job/" in url:
            raise OSError("detail fetch failed")
        if _query(url)["keywords"] == ["BCG X product manager"]:
            return _search_page([_job("58305", "BCG X Product Manager", "Ship products.")])
        return "<html><body><p>No embedded search payload here.</p></body></html>"

    monkeypatch.setattr(http, "fetch_text", fake_fetch_text)

    coverage = discover_phenom_html(_source(), ["product manager", "founder"], 5)

    assert coverage.status == "partial"
    assert coverage.matched_jobs == 1
    assert coverage.direct_job_pages_opened == 0
    assert coverage.candidates[0].description == ""
    assert coverage.limitations == [
        "Phenom search payload for 'BCG X founder' was not found in the page HTML",
        "Phenom detail page fetch errored for 1 of 1 matched roles",
    ]


def test_phenom_html_network_failure_returns_partial_without_candidates(monkeypatch):
    def raise_error(url: str, timeout_seconds: int) -> str:
        raise OSError("network down")

    monkeypatch.setattr(http, "fetch_text", raise_error)

    coverage = discover_source(_source(), ["product manager"], 5)

    assert coverage.status == "partial"
    assert coverage.candidates == []
    assert coverage.limitations == ["Errored Phenom searches: BCG X product manager"]


def test_phenom_search_payload_accepts_bare_eager_load_marker():
    html = '<script>window.__DATA__ = {"eagerLoadRefineSearch":{"hits":1,"totalHits":1,"data":{"jobs":[{"jobId":"1"}]}}};</script>'

    payload = extract_phenom_search_payload(html)

    assert payload is not None
    assert payload["data"]["jobs"] == [{"jobId": "1"}]
    assert extract_phenom_search_payload("<html></html>") is None


def test_phenom_url_builders_reuse_source_locale_path_and_query():
    assert (
        build_phenom_search_url("https://careers.bcg.com/global/en/search-results?keywords=BCG%20X&s=1", "BCG X CEO", 20)
        == "https://careers.bcg.com/global/en/search-results?keywords=BCG+X+CEO&from=20"
    )
    assert (
        build_phenom_job_url("https://careers.bcg.com/global/en/search-results?keywords=BCG%20X", "59145", "BCG X Global Product Marketing Manager")
        == "https://careers.bcg.com/global/en/job/59145/bcg-x-global-product-marketing-manager"
    )
    assert build_phenom_job_url("https://jobs.example.com/de/de/search-results", "7", "") == "https://jobs.example.com/de/de/job/7"
