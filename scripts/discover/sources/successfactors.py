"""SAP SuccessFactors / Jobs2Web RSS feed providers.

Supported discovery modes:
- `demant_rss` — careers.demant.com per-term keyword RSS search
- `sennheiser_rss` — jobs.sennheiser.com full-feed RSS listing

Expected source URL shape:
- A careers page on the employer's SuccessFactors site; enumeration goes
  through the site's `/services/rss/job/` endpoint.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from html import unescape
from urllib.parse import urlencode

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


DEMANT_RSS_ENDPOINT = "https://careers.demant.com/services/rss/job/"
SENNHEISER_RSS_ENDPOINT = "https://jobs.sennheiser.com/services/rss/job/"
TITLE_LOCATION_RE = re.compile(r"\s*\(([^()]+)\)\s*$")


def _split_title_location(raw_title: str) -> tuple[str, str]:
    text = helpers.normalize_whitespace(unescape(raw_title or ""))
    match = TITLE_LOCATION_RE.search(text)
    if not match:
        return text or "unknown", "unknown"
    location = helpers.normalize_whitespace(match.group(1)) or "unknown"
    title = helpers.normalize_whitespace(text[: match.start()]) or "unknown"
    return title, location


def _discover_successfactors_rss(
    source: SourceConfig,
    terms: list[str],
    timeout_seconds: int,
    *,
    feeds: list[tuple[str, str]],
    notes: str,
    result_pages_label: str,
) -> Coverage:
    """Shared SuccessFactors RSS enumeration over ``feeds`` of (label, url)."""
    candidates_by_url: dict[str, Candidate] = {}
    seen_item_links: set[str] = set()
    enumerated = 0
    listing_pages_scanned = 0
    limitations: list[str] = []

    for label, feed_url in feeds:
        try:
            xml_text = http.fetch_text(feed_url, timeout_seconds)
            listing_pages_scanned += 1
        except Exception as exc:
            limitations.append(f"RSS fetch failed{label}: {type(exc).__name__}: {exc}")
            continue
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            limitations.append(f"RSS parse failed{label}: {exc}")
            continue
        for item in root.findall(".//item"):
            link_elem = item.find("link")
            title_elem = item.find("title")
            description_elem = item.find("description")
            raw_link = (link_elem.text or "").strip() if link_elem is not None else ""
            raw_title = (title_elem.text or "") if title_elem is not None else ""
            raw_description = (description_elem.text or "") if description_elem is not None else ""
            if not raw_link or not raw_title:
                continue
            absolute_url = helpers.normalize_url_without_fragment(raw_link)
            if absolute_url in seen_item_links:
                continue
            seen_item_links.add(absolute_url)
            enumerated += 1
            title, location = _split_title_location(raw_title)
            description_text = " ".join(helpers.extract_visible_text_lines_from_html(raw_description))
            searchable_text = " ".join(part for part in (title, location, description_text) if part)
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
                    location=location,
                    matched_terms=matched_terms,
                    notes=notes,
                ),
            )

    status = "complete" if listing_pages_scanned > 0 else "failed"
    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status=status,
        listing_pages_scanned=listing_pages_scanned,
        search_terms_tried=terms,
        result_pages_scanned=f"{result_pages_label}={listing_pages_scanned}",
        direct_job_pages_opened=0,
        enumerated_jobs=enumerated,
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_demant_successfactors(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    feeds = [
        (f" for {term!r}", f"{DEMANT_RSS_ENDPOINT}?{urlencode({'locale': 'en_GB', 'keywords': term})}")
        for term in terms
    ]
    return _discover_successfactors_rss(
        source,
        terms,
        timeout_seconds,
        feeds=feeds,
        notes="Enumerated through Demant SAP SuccessFactors RSS search",
        result_pages_label="rss_search",
    )


def discover_sennheiser_jobs(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    feeds = [("", f"{SENNHEISER_RSS_ENDPOINT}?{urlencode({'locale': 'en_US'})}")]
    return _discover_successfactors_rss(
        source,
        terms,
        timeout_seconds,
        feeds=feeds,
        notes="Enumerated through Sennheiser SAP/Jobs2Web RSS feed",
        result_pages_label="rss_feed",
    )


SOURCES = [
    SourceAdapter(modes=("demant_rss",), discover=discover_demant_successfactors),
    SourceAdapter(modes=("sennheiser_rss",), discover=discover_sennheiser_jobs),
]
