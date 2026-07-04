"""Krisp careers-site provider.

Supported discovery modes:
- `krisp_html`

Expected source URL shape:
- The krisp.ai careers page; job postings are enumerated through direct
  `/jobs/<slug>` links and enriched from each job-detail page.
"""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import urljoin, urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


KRISP_HOST = "krisp.ai"
KRISP_JOB_PATH_RE = re.compile(r"^/jobs/[^/]+/?$")
KRISP_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
KRISP_REMOTE_TOKENS = ("On-site", "Onsite", "Hybrid", "Remote")
KRISP_TASK_HEADINGS = (
    "What you'll do",
    "What you will do",
    "Your Responsibilities",
    "Responsibilities",
    "Key Responsibilities",
    "The Role",
    "About the Role",
    "Your Role",
    "What you do",
    "Day-to-day",
    "Your day-to-day",
)
KRISP_QUALIFICATION_HEADINGS = (
    "What we are looking for",
    "What we're looking for",
    "What we look for",
    "Requirements",
    "Qualifications",
    "Required Qualifications",
    "Required Skills",
    "Your Profile",
    "About You",
    "Who You Are",
    "What You Bring",
)
KRISP_DETAIL_STOP_HEADINGS = (
    *KRISP_TASK_HEADINGS,
    *KRISP_QUALIFICATION_HEADINGS,
    "How to apply",
    "Apply",
    "Apply now",
    "About us",
    "About Krisp",
    "Benefits",
    "What we offer",
    "We offer",
    "Why join us",
    "Equal Opportunity",
    "Krisp is an Equal Opportunity Employer",
    "Krisp is an Equal Opportunity Employer:",
)


def _clean_title(detail_html: str, fallback: str) -> str:
    match = KRISP_TITLE_RE.search(detail_html or "")
    if not match:
        return fallback or "unknown"
    raw = helpers.normalize_whitespace(unescape(match.group(1)))
    if "|" in raw:
        raw = raw.split("|", 1)[0].strip()
    return raw or (fallback or "unknown")


def _location_and_remote(listing_text: str, clean_title: str) -> tuple[str, str]:
    text = helpers.normalize_whitespace(listing_text or "")
    title = helpers.normalize_whitespace(clean_title or "")
    if title and text.startswith(title):
        remainder = text[len(title):].strip()
    else:
        remainder = text
    if not remainder:
        return "unknown", "unknown"
    for token in KRISP_REMOTE_TOKENS:
        if remainder.endswith(" " + token):
            location = remainder[: -len(token)].strip()
            return location or "unknown", token
        if remainder == token:
            return "unknown", token
    return remainder, "unknown"


def extract_krisp_detail_sections(detail_html: str) -> dict[str, str]:
    detail_text = "\n".join(helpers.extract_visible_text_lines_from_html(detail_html or ""))
    tasks = helpers.extract_visible_text_section(
        detail_text,
        KRISP_TASK_HEADINGS,
        KRISP_DETAIL_STOP_HEADINGS,
    )
    qualifications = helpers.extract_visible_text_section(
        detail_text,
        KRISP_QUALIFICATION_HEADINGS,
        KRISP_DETAIL_STOP_HEADINGS,
    )
    return {"tasks": tasks, "qualifications": qualifications}


def build_krisp_detail_note_parts(sections: dict[str, str]) -> list[str]:
    parts: list[str] = []
    if sections.get("tasks"):
        parts.append(f"Tasks: {helpers.truncate_text(sections['tasks'], 260)}")
    if sections.get("qualifications"):
        parts.append(f"Qualifications: {helpers.truncate_text(sections['qualifications'], 260)}")
    return parts


def discover_krisp_jobs(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    careers_html = http.fetch_text(source.url, timeout_seconds)
    parser = helpers.LinkCollector()
    parser.feed(careers_html)

    job_link_texts: dict[str, str] = {}
    for link in parser.links:
        absolute_url = helpers.normalize_url_without_fragment(urljoin(source.url, link["href"]))
        parsed = urlparse(absolute_url)
        if (parsed.hostname or "").lower() != KRISP_HOST:
            continue
        path = parsed.path if parsed.path.endswith("/") else parsed.path + "/"
        if not KRISP_JOB_PATH_RE.match(path):
            continue
        if absolute_url in job_link_texts:
            continue
        job_link_texts[absolute_url] = helpers.normalize_whitespace(link["text"])

    candidates_by_url: dict[str, Candidate] = {}
    direct_job_pages_opened = 0
    limitations: list[str] = []

    for absolute_url, listing_text in job_link_texts.items():
        clean_title = listing_text or "unknown"
        location = "unknown"
        remote = "unknown"
        note_parts: list[str] = ["Enumerated through krisp.ai careers HTML"]
        try:
            detail_html = http.fetch_text(absolute_url, timeout_seconds)
        except Exception as exc:
            limitations.append(f"Could not fetch detail for {absolute_url}: {type(exc).__name__}")
            detail_html = ""
        if detail_html:
            direct_job_pages_opened += 1
            clean_title = _clean_title(detail_html, listing_text)
            location, remote = _location_and_remote(listing_text, clean_title)
            sections = extract_krisp_detail_sections(detail_html)
            note_parts.extend(build_krisp_detail_note_parts(sections))
        searchable_text = " ".join(part for part in (clean_title, listing_text, absolute_url) if part)
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not helpers.should_keep_candidate(clean_title, matched_terms, searchable_text):
            continue
        helpers.merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=clean_title,
                url=absolute_url,
                source_url=source.url,
                location=location,
                remote=remote,
                matched_terms=matched_terms,
                notes="; ".join(part for part in note_parts if part),
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
        result_pages_scanned="local_filter=1",
        direct_job_pages_opened=direct_job_pages_opened,
        enumerated_jobs=len(job_link_texts),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("krisp_html",), discover=discover_krisp_jobs)
