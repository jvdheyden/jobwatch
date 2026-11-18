from __future__ import annotations

import pytest

from discover import http
from discover.core import SourceConfig
from discover.sources import kula


def _item(
    job_id: str,
    title: str,
    *,
    city: str = "London",
    state: str = "",
    country: str = "United Kingdom",
    department: str = "Labs",
    workplace: str = "OFFICE",
    description: str = "&lt;h3&gt;What you'll do&lt;/h3&gt;&lt;p&gt;Own subscription pricing.&lt;/p&gt;",
    link: str | None = None,
) -> str:
    # Mirrors a real careers.kula.ai/<company>/feed item.
    link = link if link is not None else f"https://careers.kula.ai/nothing/{job_id}/apply"
    return f"""
    <item>
      <title>{title}</title>
      <link>{link}</link>
      <guid isPermaLink="true">{link}</guid>
      <category>{department}</category>
      <description>{description}</description>
      <job:employmentType>FULL_TIME</job:employmentType>
      <job:workplace>{workplace}</job:workplace>
      <job:location>
        <job:officeName>{city}</job:officeName>
        <job:city>{city}</job:city>
        <job:state>{state}</job:state>
        <job:country>{country}</job:country>
      </job:location>
    </item>"""


def _feed(*items: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss xmlns:job="https://kula.ai/rss" version="2.0"><channel>'
        "<title>Nothing Technology</title><link>https://careers.kula.ai/nothing</link>"
        + "".join(items)
        + "</channel></rss>"
    )


def _source(url: str = "https://careers.kula.ai/nothing") -> SourceConfig:
    return SourceConfig(
        source="Nothing",
        url=url,
        discovery_mode="kula_rss",
        last_checked=None,
        cadence_group="every_run",
    )


def _serve(monkeypatch, xml_text: str) -> list[str]:
    requested: list[str] = []

    def fake_fetch_text(url: str, timeout_seconds: int, headers=None) -> str:
        del timeout_seconds, headers
        requested.append(url)
        return xml_text

    monkeypatch.setattr(http, "fetch_text", fake_fetch_text)
    return requested


def test_merges_per_office_items_and_builds_candidates_from_the_feed(monkeypatch):
    requested = _serve(
        monkeypatch,
        _feed(
            _item("58931", "Growth Lead, Subscription Products"),
            _item(
                "58931",
                "Growth Lead, Subscription Products",
                city="San Francisco",
                state="California",
                country="United States",
            ),
            _item("59045", "Product Manager, Subscription Products", workplace="HYBRID"),
            _item("59073", "Ecommerce Executive", department="US Market"),
        ),
    )

    coverage = kula.discover_kula_rss(_source(), ["product manager", "growth"], 5)

    assert requested == ["https://careers.kula.ai/nothing/feed"]
    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 3
    growth, pm = coverage.candidates
    assert growth.url == "https://careers.kula.ai/nothing/58931"
    assert growth.location == "London, United Kingdom; San Francisco, California, United States"
    assert growth.remote == "on-site"
    assert growth.notes == "Enumerated through Kula job feed; Department: Labs; Workplace: Office; Type: Full time"
    assert growth.description == "What you'll do Own subscription pricing."
    assert pm.title == "Product Manager, Subscription Products"
    assert pm.remote == "hybrid"


def test_feed_url_comes_from_the_company_segment_of_a_job_page_url(monkeypatch):
    requested = _serve(monkeypatch, _feed())

    kula.discover_kula_rss(_source("https://careers.kula.ai/nothing/59045-product-manager/"), ["product"], 5)

    assert requested == ["https://careers.kula.ai/nothing/feed"]


def test_rejects_source_url_without_company():
    with pytest.raises(ValueError, match="company slug"):
        kula.kula_feed_url("https://careers.kula.ai/")


@pytest.mark.parametrize(
    "response",
    ["<!DOCTYPE html><html><body>Not found</body></html>", "<html><body><p>Not found</p></body></html>"],
    ids=["not-xml", "not-rss"],
)
def test_unexpected_feed_response_raises_instead_of_reading_as_empty(monkeypatch, response):
    _serve(monkeypatch, response)

    with pytest.raises(ValueError, match="Kula feed"):
        kula.discover_kula_rss(_source(), ["product"], 5)


def test_feed_without_items_is_a_complete_empty_board(monkeypatch):
    _serve(monkeypatch, _feed())

    coverage = kula.discover_kula_rss(_source(), ["product"], 5)

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 0
    assert coverage.candidates == []


def test_items_without_a_job_id_are_flagged_not_dropped_silently(monkeypatch):
    _serve(
        monkeypatch,
        _feed(
            _item("59045", "Product Manager, Subscription Products"),
            _item("", "Product Manager, Payments", link="https://careers.kula.ai/nothing"),
        ),
    )

    coverage = kula.discover_kula_rss(_source(), ["product manager"], 5)

    assert [candidate.title for candidate in coverage.candidates] == ["Product Manager, Subscription Products"]
    assert coverage.status == "partial"
    assert coverage.limitations == ["1 Kula feed item(s) had no job id in their link and were skipped."]
