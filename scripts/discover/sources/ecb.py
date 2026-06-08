"""European Central Bank / EZB career-source discovery."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


ECB_DEFAULT_FEED_URL = "https://talent.ecb.europa.eu/careers/SearchJobs/feed/?jobRecordsPerPage=50"
ECB_DETAIL_FIELD_RE = re.compile(r'<p class="paragraph[^"]*">(?P<body>.*?)</p>', re.DOTALL)
ECB_FIELD_TITLE_RE = re.compile(r'<span data-map="item-title">\s*<strong>(?P<title>.*?)</strong>\s*</span>', re.DOTALL)
ECB_FIELD_VALUE_RE = re.compile(r'<span data-map="item-value">\s*(?P<value>.*?)\s*</span>', re.DOTALL)
ECB_STRONG_RELEVANCE_MARKERS = (
    "digital euro",
    "privacy",
    "cryptograph",
    "security",
    "cyber",
    "offline technology",
)
ECB_DIGITAL_EURO_CONTEXT_MARKERS = (
    "market infrastructure",
    "offline",
    "privacy",
    "security",
    "cryptograph",
    "technology",
    "technical",
    "rulebook",
)


def ecb_avature_feed_url(source_url: str) -> str:
    if "/feed/" in source_url:
        return source_url
    parsed = urlparse(source_url)
    if parsed.netloc == "talent.ecb.europa.eu" and parsed.path.startswith("/careers"):
        return urljoin(source_url, "/careers/SearchJobs/feed/?jobRecordsPerPage=50")
    return ECB_DEFAULT_FEED_URL


def _item_text(item: ET.Element, name: str) -> str:
    child = item.find(name)
    return helpers.normalize_whitespace(child.text if child is not None and child.text else "")


def _rss_items(xml_text: str) -> list[dict[str, str]]:
    root = ET.fromstring(xml_text)
    items: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        title = _item_text(item, "title")
        link = _item_text(item, "link")
        if not title or not link:
            continue
        items.append(
            {
                "title": title,
                "url": link,
                "description": helpers.strip_html_fragment(_item_text(item, "description")),
                "published": _item_text(item, "pubDate"),
            }
        )
    return items


def _detail_fields(html: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for match in ECB_DETAIL_FIELD_RE.finditer(html):
        body = match.group("body")
        title_match = ECB_FIELD_TITLE_RE.search(body)
        if not title_match:
            continue
        title = helpers.strip_html_fragment(title_match.group("title"))
        values = [
            helpers.strip_html_fragment(value_match.group("value"))
            for value_match in ECB_FIELD_VALUE_RE.finditer(body)
        ]
        value = helpers.normalize_whitespace(" ".join(value for value in values if value))
        if title and value:
            fields[title] = value
    return fields


def _notes_from_fields(fields: dict[str, str], published: str) -> str:
    parts: list[str] = []
    if published:
        parts.append(f"Posted: {published}")
    field_map = (
        ("Type of contract", "Contract"),
        ("Role specialisation", "Role specialisation"),
        ("Place of work", "Location"),
        ("Closing date", "Deadline"),
        ("Your team", "Team"),
        ("Your role", "Tasks"),
        ("Qualifications, experience and skills", "Qualifications"),
    )
    for field_name, note_label in field_map:
        value = fields.get(field_name)
        if value:
            parts.append(f"{note_label}: {helpers.truncate_text(value, 500)}")
    return "; ".join(parts)


def _should_keep_ecb_candidate(title: str, searchable_text: str, matched_terms: list[str]) -> bool:
    if not matched_terms:
        return False
    normalized = helpers.normalize_for_matching(searchable_text)
    if any(marker in normalized for marker in ECB_STRONG_RELEVANCE_MARKERS):
        return True
    if "digital euro" in normalized and any(marker in normalized for marker in ECB_DIGITAL_EURO_CONTEXT_MARKERS):
        return True
    return helpers.should_keep_candidate(title, matched_terms, searchable_text)


def discover_ecb_avature_rss(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    feed_url = ecb_avature_feed_url(source.url)
    xml_text = http.fetch_text(feed_url, timeout_seconds)
    items = _rss_items(xml_text)
    candidates_by_url: dict[str, Candidate] = {}
    direct_job_pages_opened = 0
    limitations: list[str] = []

    for item in items:
        initial_text = " ".join([item["title"], item["description"], item["url"]])
        initial_matches = helpers.match_terms(initial_text, terms)
        if not _should_keep_ecb_candidate(item["title"], initial_text, initial_matches):
            continue

        fields: dict[str, str] = {}
        try:
            detail_html = http.fetch_text(item["url"], timeout_seconds)
            direct_job_pages_opened += 1
            fields = _detail_fields(detail_html)
        except Exception as exc:  # pragma: no cover - live-site defensive path
            limitations.append(f"Could not enrich ECB job detail {item['url']}: {type(exc).__name__}: {exc}")

        detail_text = " ".join(fields.values())
        matched_terms = sorted(set(initial_matches + helpers.match_terms(detail_text, terms)))
        searchable_text = " ".join([initial_text, detail_text])
        if not _should_keep_ecb_candidate(item["title"], searchable_text, matched_terms):
            continue

        helpers.merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=item["title"],
                url=item["url"],
                source_url=source.url,
                location=fields.get("Place of work", "unknown") or "unknown",
                matched_terms=matched_terms,
                notes=_notes_from_fields(fields, item["published"]) or "Enumerated through ECB Avature jobs RSS.",
            ),
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
        result_pages_scanned=f"rss={feed_url}",
        direct_job_pages_opened=direct_job_pages_opened,
        enumerated_jobs=len(items),
        matched_jobs=len(candidates_by_url),
        limitations=list(dict.fromkeys(limitations)),
        candidates=list(candidates_by_url.values()),
    )


SOURCES = [
    SourceAdapter(modes=("ecb_avature_rss",), discover=discover_ecb_avature_rss),
]
