"""Generic and filtered static HTML discovery providers."""

from __future__ import annotations

import re
from collections.abc import Callable
from urllib.parse import urljoin, urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


def is_same_page_link(source_url: str, candidate_url: str) -> bool:
    return helpers.normalize_url_without_fragment(source_url) == helpers.normalize_url_without_fragment(candidate_url)


def looks_like_non_job_link(text: str, href: str) -> bool:
    text_lower = helpers.normalize_whitespace(text).lower()
    href_lower = href.lower()
    if text_lower in {
        "",
        "skip to content",
        "jump to main content.",
        "top of this page",
        "top of page",
        "privacy",
        "privacy policy",
        "impressum",
        "report this content",
        "collapse this bar",
        "customize",
        "accept all",
        "accept selection",
        "decline non-essential cookies",
        "subscribe",
        "subscribed",
    }:
        return True
    return any(
        marker in href_lower
        for marker in (
            "/privacy",
            "/cookie",
            "/impressum",
            "/learn/",
            "/resources/",
            "/resource/",
            "/services/",
            "/abuse/",
        )
    )


def collect_job_links(html: str, base_url: str, path_fragment: str) -> dict[str, str]:
    parser = helpers.LinkCollector()
    parser.feed(html)
    links: dict[str, str] = {}
    for link in parser.links:
        absolute_url = urljoin(base_url, link["href"])
        if path_fragment not in absolute_url:
            continue
        links[absolute_url] = link["text"]
    return links


def discover_html(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = http.fetch_text(source.url, timeout_seconds)
    parser = helpers.LinkCollector()
    parser.feed(html)
    candidates: list[Candidate] = []
    seen_urls: set[str] = set()
    for link in parser.links:
        href = link["href"]
        text = helpers.normalize_whitespace(link["text"])
        if href.startswith("#"):
            continue
        absolute_url = helpers.normalize_url_without_fragment(urljoin(source.url, href))
        if absolute_url in seen_urls:
            continue
        if urlparse(absolute_url).scheme not in {"file", "http", "https"}:
            continue
        if looks_like_non_job_link(text, absolute_url):
            continue
        if is_same_page_link(source.url, absolute_url):
            continue
        matched_terms = helpers.match_terms(f"{text} {absolute_url}", terms)
        if not matched_terms and not helpers.looks_like_job_link(text, absolute_url):
            continue
        if matched_terms and not helpers.should_keep_candidate(text or "unknown", matched_terms, f"{text} {absolute_url}"):
            continue
        seen_urls.add(absolute_url)
        candidates.append(
            Candidate(
                employer=source.source,
                title=text or "unknown",
                url=absolute_url,
                source_url=source.url,
                matched_terms=matched_terms,
                notes="Static HTML enumeration",
            )
        )
    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="complete",
        listing_pages_scanned=1,
        search_terms_tried=terms,
        result_pages_scanned="local_filter=1",
        direct_job_pages_opened=0,
        enumerated_jobs=len(parser.links),
        matched_jobs=len(candidates),
        limitations=[],
        candidates=candidates,
    )


def discover_filtered_html_links(
    source: SourceConfig,
    terms: list[str],
    timeout_seconds: int,
    url_filter: Callable[[str], bool],
    notes: str,
    limitation_if_empty: str | None = None,
) -> Coverage:
    html = http.fetch_text(source.url, timeout_seconds)
    parser = helpers.LinkCollector()
    parser.feed(html)
    raw_urls: set[str] = set()
    candidates_by_url: dict[str, Candidate] = {}

    for link in parser.links:
        absolute_url = helpers.normalize_url_without_fragment(urljoin(source.url, link["href"]))
        if urlparse(absolute_url).scheme not in {"http", "https"}:
            continue
        if not url_filter(absolute_url):
            continue
        raw_urls.add(absolute_url)
        text = helpers.normalize_whitespace(link["text"]) or "unknown"
        visible_lines = helpers.split_visible_lines(link["text"])
        title = visible_lines[0] if visible_lines else text
        searchable_text = f"{title} {text} {absolute_url}"
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not helpers.should_keep_candidate(title, matched_terms, searchable_text):
            continue
        helpers.merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=title,
                url=absolute_url,
                source_url=source.url,
                matched_terms=matched_terms,
                notes=notes,
            ),
        )

    limitations = [limitation_if_empty] if not raw_urls and limitation_if_empty else []
    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="complete",
        listing_pages_scanned=1,
        search_terms_tried=terms,
        result_pages_scanned="filtered_links=1",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_urls),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_cybernetica_teamdash(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    return discover_filtered_html_links(
        source,
        terms,
        timeout_seconds,
        lambda url: "cyber.teamdash.com/p/job/" in url,
        notes="Enumerated through Teamdash links on the Cybernetica careers page",
        limitation_if_empty="No Teamdash job links were visible on the Cybernetica careers page.",
    )


def discover_secunet_jobboard(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    pattern = re.compile(r"^https://jobs\.secunet\.com/.+-j\d+\.html$")
    return discover_filtered_html_links(
        source,
        terms,
        timeout_seconds,
        lambda url: bool(pattern.match(url)),
        notes="Enumerated through direct secunet job-detail links",
        limitation_if_empty="No secunet job-detail links matching the standard job pattern were visible.",
    )


SOURCES = [
    SourceAdapter(modes=("html", "icims_html"), discover=discover_html),
    SourceAdapter(modes=("cybernetica_teamdash",), discover=discover_cybernetica_teamdash),
    SourceAdapter(modes=("secunet_jobboard",), discover=discover_secunet_jobboard),
]
