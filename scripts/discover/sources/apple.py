"""Apple jobs search-page provider.

Supported discovery modes:
- `apple_jobs`

Expected source URL shape:
- `https://jobs.apple.com/<locale>/search?...`
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


APPLE_DETAIL_RE = re.compile(r"/[a-z]{2}-[a-z]{2}/details/(?P<role>\d{6,}(?:-\d{3,})?)/")
APPLE_ROLE_NUMBER_RE = re.compile(r"\b\d{6,}(?:-\d{3,})?\b")
APPLE_TERM_ALIASES = {
    "cryptography": ("crypto",),
    "secure hardware": ("secure enclave", "trusted execution"),
    "digital identity": ("identity", "wallet identity"),
    "authentication": ("wallet identity",),
}


def apple_role_number_from_url(url: str) -> str:
    match = APPLE_DETAIL_RE.search(urlparse(url).path)
    return match.group("role") if match else ""


def clean_apple_title(text: str) -> str:
    title = helpers.normalize_whitespace(text.replace("\xa0", " "))
    title = re.sub(r"^See full role description:\s*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*See full role description$", "", title, flags=re.IGNORECASE)
    match = APPLE_ROLE_NUMBER_RE.search(title)
    if not match:
        return title
    before = helpers.normalize_whitespace(title[: match.start()])
    after = helpers.normalize_whitespace(title[match.end() :])
    if before and after and helpers.normalize_for_matching(before) == helpers.normalize_for_matching(after):
        return before
    return before or after or title


def _collect_detail_links(html: str, base_url: str) -> tuple[dict[str, str], dict[str, str], int]:
    parser = helpers.LinkCollector()
    parser.feed(html)
    urls_by_role: dict[str, str] = {}
    titles_by_role: dict[str, str] = {}
    raw_urls: set[str] = set()
    for link in parser.links:
        absolute_url = helpers.normalize_url_without_fragment(urljoin(base_url, link["href"]))
        role_number = apple_role_number_from_url(absolute_url)
        if not role_number:
            continue
        raw_urls.add(absolute_url)
        urls_by_role.setdefault(role_number, absolute_url)
        title = clean_apple_title(link["text"])
        if title and not title.lower().startswith("see full role description"):
            titles_by_role.setdefault(role_number, title)
    return urls_by_role, titles_by_role, len(raw_urls)


def _line_value(line: str, label: str) -> str:
    cleaned = helpers.normalize_whitespace(line.replace("\xa0", " "))
    if not cleaned.lower().startswith(label.lower()):
        return ""
    return cleaned[len(label) :].lstrip(": ").strip()


def _location_before(lines: list[str], index: int) -> str:
    for line in reversed(lines[max(0, index - 8) : index]):
        location = _line_value(line, "Location")
        if location:
            return location
    return "unknown"


def _metadata_after(lines: list[str], index: int) -> tuple[str, str, str]:
    role_number = ""
    weekly_hours = ""
    description_start = index + 1
    for current_index in range(index + 1, min(len(lines), index + 14)):
        line = helpers.normalize_whitespace(lines[current_index].replace("\xa0", " "))
        role_number = _line_value(line, "Role Number") or role_number
        weekly_hours = _line_value(line, "Weekly Hours") or weekly_hours
        if weekly_hours:
            description_start = current_index + 1
            break

    description_lines: list[str] = []
    for line in lines[description_start : min(len(lines), description_start + 8)]:
        cleaned = helpers.normalize_whitespace(line.replace("\xa0", " "))
        if not cleaned:
            continue
        if cleaned == "Submit Resume" or cleaned.startswith("Share "):
            break
        if cleaned in {"Actions", "See full role description"}:
            continue
        if cleaned.startswith(("Role Number", "Weekly Hours")):
            continue
        description_lines.append(cleaned)
        if len(" ".join(description_lines)) >= 650:
            break

    return role_number, weekly_hours, helpers.truncate_text(" ".join(description_lines), 650)


def _share_line_payload(line: str) -> tuple[str, str] | None:
    cleaned = helpers.normalize_whitespace(line.replace("\xa0", " "))
    if not cleaned.startswith("Share "):
        return None
    match = APPLE_ROLE_NUMBER_RE.search(cleaned)
    if not match:
        return None
    title = helpers.normalize_whitespace(cleaned[len("Share ") : match.start()])
    role_number = match.group(0)
    if not title:
        return None
    return title, role_number


def _candidate_notes(role_number: str, weekly_hours: str, description: str) -> str:
    parts = ["Enumerated through Apple jobs search page."]
    if role_number:
        parts.append(f"Role number: {role_number}.")
    if weekly_hours:
        parts.append(f"Weekly hours: {weekly_hours}.")
    if description:
        parts.append(f"Responsibilities: {description}")
    return " ".join(parts)


def discover_apple_jobs(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = http.fetch_text(source.url, timeout_seconds)
    urls_by_role, titles_by_role, raw_url_count = _collect_detail_links(html, source.url)
    lines = helpers.extract_visible_text_lines_from_html(html)
    candidates_by_url: dict[str, Candidate] = {}
    seen_roles: set[str] = set()

    for index, line in enumerate(lines):
        payload = _share_line_payload(line)
        if payload is None:
            continue
        title, role_number = payload
        url = urls_by_role.get(role_number)
        if not url:
            continue
        seen_roles.add(role_number)
        title = titles_by_role.get(role_number, title)
        location = _location_before(lines, index)
        configured_role_number, weekly_hours, description = _metadata_after(lines, index)
        searchable_text = " ".join(part for part in [title, location, description, url] if part)
        matched_terms = sorted(
            set(helpers.match_terms_with_aliases(searchable_text, terms, APPLE_TERM_ALIASES))
        )
        if not helpers.should_keep_candidate(title, matched_terms, searchable_text):
            continue
        helpers.merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=title,
                url=url,
                source_url=source.url,
                location=location,
                matched_terms=matched_terms,
                notes=_candidate_notes(configured_role_number or role_number, weekly_hours, description),
            ),
        )

    limitations: list[str] = []
    if not raw_url_count:
        limitations.append("No Apple job-detail links were visible on the search page.")
    elif not candidates_by_url:
        limitations.append("Apple job-detail links were visible, but none matched the configured track terms.")

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
        result_pages_scanned="apple_search=1",
        direct_job_pages_opened=0,
        enumerated_jobs=raw_url_count or len(seen_roles),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("apple_jobs",), discover=discover_apple_jobs)
