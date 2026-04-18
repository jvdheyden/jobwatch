"""IACR Jobs provider.

Supported discovery modes:
- `iacr_jobs`

Expected source URL shape:
- `https://www.iacr.org/jobs/`
"""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import urljoin

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


IACR_POSTING_BLOCK_RE = re.compile(
    r'<h5>\s*<a href="(?P<href>[^"]+)" id="url-(?P<id>\d+)">\s*'
    r'<span id="position-(?P=id)">(?P<title>.*?)</span>\s*</a>\s*</h5>'
    r'(?P<body>.*?)(?=<hr\s*/?>|\Z)',
    flags=re.DOTALL,
)
IACR_PLACE_RE = re.compile(r'<h6 id="place-\d+"[^>]*>(?P<place>.*?)</h6>', flags=re.DOTALL)
IACR_DESCRIPTION_RE = re.compile(r'<div id="description-\d+">(?P<description>.*?)</div>', flags=re.DOTALL)
IACR_CONTACT_RE = re.compile(r'<span id="contact-\d+">(?P<contact>.*?)</span>', flags=re.DOTALL)
IACR_UPDATED_RE = re.compile(r"<strong>\s*Last updated:\s*</strong>\s*(?P<updated>[^<]+)", flags=re.DOTALL)
IACR_POSTED_RE = re.compile(r"<small[^>]*>posted on (?P<posted>[^<]+)</small>", flags=re.DOTALL)


def split_iacr_place(value: str) -> tuple[str, str]:
    place = helpers.normalize_whitespace(value)
    for separator in (" | ", " ; ", "; "):
        if separator in place:
            employer, location = place.split(separator, 1)
            return helpers.normalize_whitespace(employer), helpers.normalize_whitespace(location)
    return place or "unknown", "unknown"


def discover_iacr_jobs(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = http.fetch_text(source.url, timeout_seconds)
    candidates_by_url: dict[str, Candidate] = {}
    posting_count = 0

    for match in IACR_POSTING_BLOCK_RE.finditer(html):
        posting_count += 1
        posting_id = match.group("id")
        outbound_url = helpers.normalize_url_without_fragment(urljoin(source.url, unescape(match.group("href"))))
        item_url = helpers.normalize_url_without_fragment(urljoin(source.url, f"/jobs/item/{posting_id}"))
        title = helpers.strip_html_fragment(match.group("title")) or "unknown"
        body = match.group("body")

        place_match = IACR_PLACE_RE.search(body)
        description_match = IACR_DESCRIPTION_RE.search(body)
        contact_match = IACR_CONTACT_RE.search(body)
        updated_match = IACR_UPDATED_RE.search(body)
        posted_match = IACR_POSTED_RE.search(body)

        place = helpers.strip_html_fragment(place_match.group("place")) if place_match else ""
        employer, location = split_iacr_place(place)
        description = helpers.strip_html_fragment(description_match.group("description")) if description_match else ""
        contact = helpers.strip_html_fragment(contact_match.group("contact")) if contact_match else ""
        updated = helpers.normalize_whitespace(updated_match.group("updated")) if updated_match else ""
        posted = helpers.normalize_whitespace(posted_match.group("posted")) if posted_match else ""
        remote = helpers.infer_remote_status(place, description)

        searchable_text = " ".join(
            part
            for part in [
                title,
                employer,
                location,
                remote,
                description,
                contact,
                updated,
                posted,
                outbound_url,
            ]
            if part
        )
        matched_terms = helpers.match_terms(searchable_text, terms)
        if not helpers.should_keep_candidate(title, matched_terms, searchable_text):
            continue

        note_parts = ["IACR Jobs board listing"]
        if contact:
            note_parts.append(f"Contact: {contact}")
        if posted:
            note_parts.append(f"Posted: {posted}")
        if updated:
            note_parts.append(f"Updated: {updated}")
        if description:
            note_parts.append(f"Description: {description}")

        helpers.merge_candidate(
            candidates_by_url,
            Candidate(
                employer=employer,
                title=title,
                url=item_url,
                source_url=source.url,
                alternate_url=outbound_url if outbound_url != item_url else "",
                location=location,
                remote=remote,
                matched_terms=matched_terms,
                notes="; ".join(note_parts),
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
        result_pages_scanned=f"posting_blocks={posting_count}",
        direct_job_pages_opened=0,
        enumerated_jobs=posting_count,
        matched_jobs=len(candidates_by_url),
        limitations=[],
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("iacr_jobs",), discover=discover_iacr_jobs)
