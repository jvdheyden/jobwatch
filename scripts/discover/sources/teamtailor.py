"""Teamtailor jobs.json feed provider.

Supported discovery modes:
- `teamtailor_api`

Expected source URL shape:
- A Teamtailor-hosted careers site (custom domains included) exposing the
  standard `/jobs.json` feed relative to the site root.
"""

from __future__ import annotations

from html import unescape
from urllib.parse import urljoin

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


TEAMTAILOR_FEED_PATH = "/jobs.json"


def _job_location(job_posting: dict) -> str:
    raw_locations = job_posting.get("jobLocation") if isinstance(job_posting, dict) else None
    if isinstance(raw_locations, dict):
        raw_locations = [raw_locations]
    if not isinstance(raw_locations, list):
        return "unknown"
    parts: list[str] = []
    for entry in raw_locations:
        if not isinstance(entry, dict):
            continue
        address = entry.get("address") if isinstance(entry.get("address"), dict) else {}
        locality = unescape(str(address.get("addressLocality") or "")).strip()
        region = unescape(str(address.get("addressRegion") or "")).strip()
        country = unescape(str(address.get("addressCountry") or "")).strip()
        components = [component for component in (locality, region, country) if component]
        if components:
            parts.append(", ".join(components))
    return "; ".join(parts) or "unknown"


def discover_teamtailor_jobs(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    feed_url = urljoin(source.url, TEAMTAILOR_FEED_PATH)
    payload = http.fetch_json(feed_url, timeout_seconds)
    items = payload.get("items", []) if isinstance(payload, dict) else []
    candidates_by_url: dict[str, Candidate] = {}

    for item in items:
        if not isinstance(item, dict):
            continue
        url = helpers.normalize_whitespace(str(item.get("url") or ""))
        if not url:
            continue
        title = helpers.normalize_whitespace(unescape(str(item.get("title") or ""))) or "unknown"
        job_posting = item.get("_jobposting") if isinstance(item.get("_jobposting"), dict) else {}
        location = _job_location(job_posting)
        description_html = item.get("content_html") or (
            job_posting.get("description") if isinstance(job_posting, dict) else ""
        ) or ""
        description_text = " ".join(helpers.extract_visible_text_lines_from_html(description_html))
        searchable_text = " ".join(part for part in (title, location, description_text) if part)
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not helpers.should_keep_candidate(title, matched_terms, searchable_text):
            continue
        note_parts = ["Enumerated through Teamtailor jobs.json feed"]
        if description_text:
            note_parts.append(f"Description: {helpers.truncate_text(description_text, 260)}")
        teamtailor_candidate = Candidate(
            employer=source.source,
            title=title,
            url=helpers.normalize_url_without_fragment(url),
            source_url=source.url,
            location=location,
            matched_terms=matched_terms,
            notes="; ".join(note_parts),
        )
        helpers.set_candidate_description(teamtailor_candidate, description_text)
        helpers.merge_candidate(candidates_by_url, teamtailor_candidate)

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
        enumerated_jobs=len(items),
        matched_jobs=len(candidates_by_url),
        limitations=[],
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("teamtailor_api",), discover=discover_teamtailor_jobs)
