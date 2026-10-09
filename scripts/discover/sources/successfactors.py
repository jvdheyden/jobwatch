"""SAP SuccessFactors / Jobs2Web RSS feed providers.

Supported discovery modes:
- `successfactors_rss` — host-derived per-term keyword RSS search
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
from urllib.parse import parse_qs, urlencode, urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


DEMANT_RSS_ENDPOINT = "https://careers.demant.com/services/rss/job/"
SENNHEISER_RSS_ENDPOINT = "https://jobs.sennheiser.com/services/rss/job/"
TITLE_LOCATION_RE = re.compile(r"\s*\(([^()]+)\)\s*$")
TASK_HEADINGS = (
    "Responsibilities",
    "Key Responsibilities",
    "Your Responsibilities",
    "What You'll Do",
    "What You Will Do",
    "Job Description",
    "Job Summary",
    "Ihre Aufgaben",
    "Aufgaben",
)
QUALIFICATION_HEADINGS = (
    "Qualifications",
    "Key Qualifications",
    "Requirements",
    "Required Qualifications",
    "Your Profile",
    "Ihre Qualifikationen",
    "Qualifikationen",
    "Ihr Profil",
    "Anforderungen",
)
COMPENSATION_HEADINGS = (
    "Compensation",
    "Pay Range",
    "Salary Range",
    "Vergütung",
    "Gehalt",
)
DETAIL_STOP_HEADINGS = (
    *TASK_HEADINGS,
    *QUALIFICATION_HEADINGS,
    *COMPENSATION_HEADINGS,
    "Benefits",
    "What We Offer",
    "Wir bieten",
    "Unser Angebot",
    "About Us",
    "Über uns",
    "Apply",
    "Bewerbung",
)


def _split_title_location(raw_title: str) -> tuple[str, str]:
    text = helpers.normalize_whitespace(unescape(raw_title or ""))
    match = TITLE_LOCATION_RE.search(text)
    if not match:
        return text or "unknown", "unknown"
    location = helpers.normalize_whitespace(match.group(1)) or "unknown"
    title = helpers.normalize_whitespace(text[: match.start()]) or "unknown"
    return title, location


def _canonicalize_successfactors_job_url(raw_link: str) -> str:
    parsed = urlparse(raw_link)
    return helpers.normalize_url_without_fragment(parsed._replace(query="", fragment="").geturl())


def _successfactors_rss_endpoint(source_url: str) -> str:
    parsed = urlparse(source_url)
    return parsed._replace(path="/services/rss/job/", params="", query="", fragment="").geturl()


def _successfactors_locale(source_url: str) -> str:
    parsed = urlparse(source_url)
    locale = (parse_qs(parsed.query).get("locale") or ["en_US"])[0]
    return helpers.normalize_whitespace(locale) or "en_US"


def _successfactors_detail_notes(description_html: str) -> list[str]:
    detail_text = "\n".join(helpers.extract_visible_text_lines_from_html(description_html))
    sections = (
        (
            "Tasks",
            helpers.extract_visible_text_section(detail_text, TASK_HEADINGS, DETAIL_STOP_HEADINGS),
            260,
        ),
        (
            "Qualifications",
            helpers.extract_visible_text_section(detail_text, QUALIFICATION_HEADINGS, DETAIL_STOP_HEADINGS),
            260,
        ),
        (
            "Compensation",
            helpers.extract_visible_text_section(detail_text, COMPENSATION_HEADINGS, DETAIL_STOP_HEADINGS),
            200,
        ),
    )
    return [f"{label}: {helpers.truncate_text(value, limit)}" for label, value, limit in sections if value]


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
            absolute_url = _canonicalize_successfactors_job_url(raw_link)
            if absolute_url in seen_item_links:
                continue
            seen_item_links.add(absolute_url)
            enumerated += 1
            title, location = _split_title_location(raw_title)
            description_text = "\n".join(helpers.extract_visible_text_lines_from_html(raw_description))
            searchable_text = " ".join(part for part in (title, location, description_text) if part)
            matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
            if not matched_terms:
                continue
            note_parts = [notes, *_successfactors_detail_notes(raw_description)]
            rss_candidate = Candidate(
                employer=source.source,
                title=title,
                url=absolute_url,
                source_url=source.url,
                location=location,
                matched_terms=matched_terms,
                notes="; ".join(note_parts),
            )
            helpers.set_candidate_description(rss_candidate, description_text)
            helpers.merge_candidate(candidates_by_url, rss_candidate)

    if not listing_pages_scanned:
        status = "failed"
    elif limitations:
        status = "partial"
    else:
        status = "complete"
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


def discover_successfactors_rss(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    endpoint = _successfactors_rss_endpoint(source.url)
    locale = _successfactors_locale(source.url)
    feeds = [
        (
            f" for {term!r}",
            f"{endpoint}?{urlencode({'locale': locale, 'keywords': term})}",
        )
        for term in terms
    ]
    return _discover_successfactors_rss(
        source,
        terms,
        timeout_seconds,
        feeds=feeds,
        notes="Enumerated through SAP SuccessFactors RSS keyword search",
        result_pages_label="rss_search",
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
    SourceAdapter(modes=("successfactors_rss",), discover=discover_successfactors_rss),
    SourceAdapter(modes=("demant_rss",), discover=discover_demant_successfactors),
    SourceAdapter(modes=("sennheiser_rss",), discover=discover_sennheiser_jobs),
]
