from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from discover import http
from discover.core import SourceConfig
from discover.sources import avature
from discover.sources.avature import discover_avature_html


def _card(job_id: int, title: str, location: str = "London, United Kingdom", department: str = "Studios") -> str:
    slug = title.replace(" ", "-")
    url = f"https://jobs.example.com/en_US/careers/JobDetail/{slug}/{job_id}"
    return f"""
    <article class="article article--result">
      <h3><a class="link link_result" href="{url}">
        {title}
      </a></h3>
      <div class="article__header__text__subtitle">
        <span class="list-item-location">{location}</span>
        <span class="list-item-id">Role ID {job_id}</span>
        <span class="list-item-workerType">Regular Employee</span>
        <span class="list-item-department">{department}</span>
      </div>
      <a class="button button--primary" href="{url}">More Information</a>
    </article>
    """


def _page(total: int, cards: list[str]) -> str:
    return f'<html><body><div aria-label="{total} results">of {total} results</div>{"".join(cards)}</body></html>'


def _source(url: str = "https://jobs.example.com/careers/SearchJobs") -> SourceConfig:
    return SourceConfig(
        source="Example Games",
        url=url,
        discovery_mode="avature_html",
        last_checked=None,
        cadence_group="every_run",
    )


def test_avature_html_pages_through_job_offset_until_reported_total(monkeypatch):
    pages = {
        0: _page(5, [_card(1, "Lead Product Manager"), _card(2, "Software Engineer")]),
        2: _page(5, [_card(3, "Senior Producer", "Madrid, Spain", "EA SPORTS FC"), _card(4, "Data Analyst")]),
        4: _page(5, [_card(5, "Art Director")]),
    }
    fetched_offsets: list[int] = []

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        assert timeout_seconds == 5
        query = parse_qs(urlparse(url).query)
        assert query["search"] == ["games"]
        offset = int(query.get("jobOffset", ["0"])[0])
        fetched_offsets.append(offset)
        return pages[offset]

    monkeypatch.setattr(http, "fetch_text", fake_fetch_text)

    coverage = discover_avature_html(
        _source("https://jobs.example.com/careers/SearchJobs?search=games&jobOffset=40"),
        ["product manager", "producer"],
        5,
    )

    assert fetched_offsets == [0, 2, 4]
    assert coverage.status == "complete"
    assert coverage.listing_pages_scanned == 3
    assert coverage.enumerated_jobs == 5
    assert coverage.limitations == []
    assert [candidate.title for candidate in coverage.candidates] == ["Lead Product Manager", "Senior Producer"]
    producer = coverage.candidates[1]
    assert producer.url == "https://jobs.example.com/en_US/careers/JobDetail/Senior-Producer/3"
    assert producer.location == "Madrid, Spain"
    assert "Department: EA SPORTS FC" in producer.notes
    assert "Type: Regular Employee" in producer.notes


def test_avature_html_stops_when_a_page_repeats_and_reports_shortfall(monkeypatch):
    first_page = _page(4, [_card(1, "Lead Product Manager"), _card(2, "Software Engineer")])
    monkeypatch.setattr(http, "fetch_text", lambda url, timeout_seconds: first_page)

    coverage = discover_avature_html(_source(), ["product manager"], 5)

    assert coverage.listing_pages_scanned == 2
    assert coverage.enumerated_jobs == 2
    assert coverage.status == "partial"
    assert coverage.limitations == ["Avature listing reported 4 results but 2 were enumerated."]


def test_avature_html_keeps_earlier_pages_when_a_later_page_fails(monkeypatch):
    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        if "jobOffset" in url:
            raise TimeoutError("read timed out")
        return _page(4, [_card(1, "Lead Product Manager"), _card(2, "Software Engineer")])

    monkeypatch.setattr(http, "fetch_text", fake_fetch_text)

    coverage = discover_avature_html(_source(), ["product manager"], 5)

    assert coverage.status == "partial"
    assert [candidate.title for candidate in coverage.candidates] == ["Lead Product Manager"]
    assert coverage.limitations[0].startswith("Stopped Avature pagination at jobOffset=2: TimeoutError")


def test_avature_html_reports_page_cap(monkeypatch):
    monkeypatch.setattr(avature, "AVATURE_MAX_PAGES", 2)

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        offset = int(parse_qs(urlparse(url).query).get("jobOffset", ["0"])[0])
        return _page(100, [_card(offset + 1, "Producer"), _card(offset + 2, "Engineer")])

    monkeypatch.setattr(http, "fetch_text", fake_fetch_text)

    coverage = discover_avature_html(_source(), ["producer"], 5)

    assert coverage.listing_pages_scanned == 2
    assert coverage.status == "partial"
    assert "Avature pagination stopped at the 2-page cap." in coverage.limitations


@pytest.mark.parametrize(
    ("source_url", "offset", "expected"),
    [
        ("https://jobs.example.com/careers/SearchJobs", 0, "https://jobs.example.com/careers/SearchJobs"),
        (
            "https://jobs.example.com/careers/SearchJobs?jobOffset=60#top",
            20,
            "https://jobs.example.com/careers/SearchJobs?jobOffset=20",
        ),
    ],
)
def test_avature_page_url_replaces_job_offset(source_url: str, offset: int, expected: str):
    assert avature.avature_page_url(source_url, offset) == expected


def _serve(monkeypatch, html: str) -> None:
    monkeypatch.setattr(http, "fetch_text", lambda url, timeout_seconds, headers=None: html)


def test_avature_html_reports_partial_when_a_reported_total_parses_to_zero_jobs(monkeypatch):
    # The maintainer's repro: the listing reports results but no card is recognised.
    _serve(monkeypatch, _page(2, ["<article><h3>Producer</h3></article>", "<article><h3>Designer</h3></article>"]))

    coverage = discover_avature_html(_source(), ["producer"], 5)

    assert coverage.status == "partial"
    assert coverage.enumerated_jobs == 0
    assert coverage.limitations == ["Avature listing reported 2 results but 0 were enumerated."]


def test_avature_html_reports_partial_without_a_result_count_or_jobs(monkeypatch):
    _serve(monkeypatch, "<html><body><p>Something went wrong</p></body></html>")

    coverage = discover_avature_html(_source(), ["producer"], 5)

    assert coverage.status == "partial"
    assert coverage.limitations == ["Avature listing showed neither a result count nor JobDetail links."]


def test_avature_html_keeps_a_listing_reporting_zero_results_complete(monkeypatch):
    _serve(monkeypatch, _page(0, []))

    coverage = discover_avature_html(_source(), ["producer"], 5)

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 0


def test_avature_html_reads_single_quoted_job_links(monkeypatch):
    cards = [_card(101, "Senior Producer").replace('"', "'"), _card(102, "Game Designer").replace('"', "'")]
    _serve(monkeypatch, _page(2, cards))

    coverage = discover_avature_html(_source(), ["producer"], 5)

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 2
    assert [candidate.url for candidate in coverage.candidates] == [
        "https://jobs.example.com/en_US/careers/JobDetail/Senior-Producer/101"
    ]
