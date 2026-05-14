"""Greenhouse board provider.

Supported discovery modes:
- `greenhouse_api`

Expected source URL shape:
- `https://job-boards.greenhouse.io/<board-token>`
- `https://boards.greenhouse.io/<board-token>`
"""

from __future__ import annotations

from urllib.parse import urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


GREENHOUSE_TASK_HEADINGS = (
    "Responsibilities",
    "What You'll Do",
    "What You Will Do",
    "What Youll Do",
    "What You'll Be Doing",
    "The Role",
    "About the Role",
    "Your Role",
)
GREENHOUSE_QUALIFICATION_HEADINGS = (
    "Qualifications",
    "Requirements",
    "Minimum Qualifications",
    "What We're Looking For",
    "What Were Looking For",
    "What You Bring",
    "Who You Are",
    "You Have",
)
GREENHOUSE_PROFILE_HEADINGS = (
    "About You",
    "Profile",
    "Ideal Candidate",
)
GREENHOUSE_DETAIL_STOP_HEADINGS = (
    *GREENHOUSE_TASK_HEADINGS,
    *GREENHOUSE_QUALIFICATION_HEADINGS,
    *GREENHOUSE_PROFILE_HEADINGS,
    "About Us",
    "About the Company",
    "Benefits",
    "Compensation",
    "Equal Opportunity",
    "Equal Employment Opportunity",
    "Apply",
)
GREENHOUSE_DETAIL_IGNORED_LINES = {
    "Apply for this job",
    "Apply to this job",
    "Apply now",
}
GREENHOUSE_FALLBACK_IGNORED_HEADINGS = {
    helpers.normalize_heading_line(heading) for heading in GREENHOUSE_DETAIL_STOP_HEADINGS
}


def greenhouse_board_token(source_url: str) -> str:
    path_bits = [bit for bit in urlparse(source_url).path.split("/") if bit]
    if not path_bits:
        raise ValueError(f"Could not derive Greenhouse board token from {source_url}")
    return path_bits[0]


def greenhouse_content_text(content: str) -> str:
    return "\n".join(helpers.extract_visible_text_lines_from_html(content))


def greenhouse_fallback_detail_snippet(detail_text: str) -> str:
    selected: list[str] = []
    for line in helpers.split_visible_lines(detail_text):
        if line in GREENHOUSE_DETAIL_IGNORED_LINES:
            continue
        if helpers.normalize_heading_line(line) in GREENHOUSE_FALLBACK_IGNORED_HEADINGS:
            continue
        selected.append(line)
        if len(selected) >= 3:
            break
    return helpers.normalize_whitespace(" ".join(selected))


def extract_greenhouse_detail_sections(content: str) -> dict[str, str]:
    detail_text = greenhouse_content_text(content)
    tasks = helpers.extract_visible_text_section(
        detail_text,
        GREENHOUSE_TASK_HEADINGS,
        GREENHOUSE_DETAIL_STOP_HEADINGS,
        ignored_lines=GREENHOUSE_DETAIL_IGNORED_LINES,
    )
    qualifications = helpers.extract_visible_text_section(
        detail_text,
        GREENHOUSE_QUALIFICATION_HEADINGS,
        GREENHOUSE_DETAIL_STOP_HEADINGS,
        ignored_lines=GREENHOUSE_DETAIL_IGNORED_LINES,
    )
    profile = helpers.extract_visible_text_section(
        detail_text,
        GREENHOUSE_PROFILE_HEADINGS,
        GREENHOUSE_DETAIL_STOP_HEADINGS,
        ignored_lines=GREENHOUSE_DETAIL_IGNORED_LINES,
    )
    details = "" if any((tasks, qualifications, profile)) else greenhouse_fallback_detail_snippet(detail_text)
    return {
        "tasks": tasks,
        "qualifications": qualifications,
        "profile": profile,
        "details": details,
    }


def build_greenhouse_candidate_notes(content: str) -> str:
    sections = extract_greenhouse_detail_sections(content)
    note_parts = ["Enumerated through Greenhouse board API"]
    if sections["tasks"]:
        note_parts.append(f"Tasks: {helpers.truncate_text(sections['tasks'], 260)}")
    if sections["qualifications"]:
        note_parts.append(f"Qualifications: {helpers.truncate_text(sections['qualifications'], 260)}")
    if sections["profile"]:
        note_parts.append(f"Profile: {helpers.truncate_text(sections['profile'], 260)}")
    if sections["details"]:
        note_parts.append(f"Details: {helpers.truncate_text(sections['details'], 320)}")
    return "; ".join(note_parts)


def discover_greenhouse_api(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    token = greenhouse_board_token(source.url)
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
    payload = http.fetch_json(api_url, timeout_seconds)
    jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
    candidates_by_url: dict[str, Candidate] = {}

    for job in jobs:
        if not isinstance(job, dict):
            continue
        title = job.get("title", "unknown")
        location_payload = job.get("location", {})
        if not isinstance(location_payload, dict):
            location_payload = {}
        location = location_payload.get("name") or "unknown"
        content = job.get("content", "")
        searchable_text = f"{title} {location} {content}"
        matched = helpers.match_terms(searchable_text, terms)
        if not helpers.should_keep_candidate(title, matched, searchable_text):
            continue
        helpers.merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=title,
                url=helpers.normalize_url_without_fragment(job.get("absolute_url") or source.url),
                source_url=source.url,
                location=location,
                matched_terms=matched,
                notes=build_greenhouse_candidate_notes(content),
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
        direct_job_pages_opened=0,
        enumerated_jobs=len(jobs),
        matched_jobs=len(candidates_by_url),
        limitations=[],
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("greenhouse_api",), discover=discover_greenhouse_api)
