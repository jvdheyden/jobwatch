"""Jobvite careers-site provider.

Supported discovery modes:
- `jobvite_html`

Expected source URL shape:
- A jobs.jobvite.com company listing page rendering `jv-job-list-*` rows.
"""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import urljoin

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


JOBVITE_JOB_ROW_RE = re.compile(
    r'<a\s+href="(?P<href>/[^"]+/job/[^"]+)"[^>]*>\s*'
    r'<div\s+class="jv-job-list-name">\s*(?P<title>[^<]+?)\s*</div>\s*'
    r'(?:<div\s+class="jv-job-id">\s*(?P<reqid>[^<]*?)\s*</div>\s*)?'
    r'<div\s+class="[^"]*\bjv-job-list-location\b[^"]*">\s*(?P<location>.*?)\s*</div>',
    re.DOTALL,
)
JOBVITE_TASK_HEADINGS = (
    "Responsibilities",
    "Key Responsibilities",
    "Your Responsibilities",
    "What You'll Do",
    "What You Will Do",
    "What Youll Do",
    "What You'll Be Doing",
    "Job Description",
    "Position Summary",
    "Position Overview",
    "Role Summary",
    "The Role",
    "About the Role",
    "Your Role",
    "Your Mission",
    "Job Summary",
)
JOBVITE_QUALIFICATION_HEADINGS = (
    "Qualifications",
    "Requirements",
    "Required Qualifications",
    "Required Skills",
    "Minimum Qualifications",
    "Preferred Qualifications",
    "Basic Qualifications",
    "What You Bring",
    "What You'll Bring",
    "What You Will Bring",
    "What We're Looking For",
    "Who You Are",
    "You Have",
    "You'll Need",
    "What You'll Need",
)
JOBVITE_COMPENSATION_HEADINGS = (
    "Compensation",
    "Pay Range",
    "Salary Range",
    "Total Rewards",
)
JOBVITE_DETAIL_STOP_HEADINGS = (
    *JOBVITE_TASK_HEADINGS,
    *JOBVITE_QUALIFICATION_HEADINGS,
    *JOBVITE_COMPENSATION_HEADINGS,
    "About Us",
    "About the Company",
    "About Xperi",
    "Benefits",
    "Equal Opportunity",
    "Equal Employment Opportunity",
    "EEO Statement",
    "Apply",
    "Apply Now",
    "Apply for this Job",
)
JOBVITE_COMPENSATION_MARKERS = (
    "salary range",
    "pay range",
    "compensation",
    "base pay",
    "hourly rate",
)


def extract_jobvite_detail_sections(detail_html: str) -> dict[str, str]:
    detail_text = "\n".join(helpers.extract_visible_text_lines_from_html(detail_html))
    tasks = helpers.extract_visible_text_section(
        detail_text,
        JOBVITE_TASK_HEADINGS,
        JOBVITE_DETAIL_STOP_HEADINGS,
    )
    qualifications = helpers.extract_visible_text_section(
        detail_text,
        JOBVITE_QUALIFICATION_HEADINGS,
        JOBVITE_DETAIL_STOP_HEADINGS,
    )
    compensation_section = helpers.extract_visible_text_section(
        detail_text,
        JOBVITE_COMPENSATION_HEADINGS,
        JOBVITE_DETAIL_STOP_HEADINGS,
    )
    compensation = compensation_section or helpers.extract_visible_text_marker_snippet(
        detail_text,
        JOBVITE_COMPENSATION_MARKERS,
        JOBVITE_DETAIL_STOP_HEADINGS,
    )
    return {
        "tasks": tasks,
        "qualifications": qualifications,
        "compensation": compensation,
    }


def build_jobvite_detail_note_parts(sections: dict[str, str]) -> list[str]:
    parts: list[str] = []
    if sections.get("tasks"):
        parts.append(f"Tasks: {helpers.truncate_text(sections['tasks'], 260)}")
    if sections.get("qualifications"):
        parts.append(f"Qualifications: {helpers.truncate_text(sections['qualifications'], 260)}")
    if sections.get("compensation"):
        parts.append(f"Compensation: {helpers.truncate_text(sections['compensation'], 200)}")
    return parts


def discover_jobvite_jobs(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = http.fetch_text(source.url, timeout_seconds)
    candidates_by_url: dict[str, Candidate] = {}
    enumerated = 0
    for match in JOBVITE_JOB_ROW_RE.finditer(html):
        enumerated += 1
        href = match.group("href")
        title = helpers.normalize_whitespace(unescape(match.group("title") or "")) or "unknown"
        reqid = helpers.normalize_whitespace(unescape(match.group("reqid") or ""))
        location = helpers.normalize_whitespace(
            unescape(re.sub(r"<[^>]+>", " ", match.group("location") or ""))
        ) or "unknown"
        absolute_url = helpers.normalize_url_without_fragment(urljoin(source.url, href))
        searchable_text = " ".join(part for part in (title, reqid, location, absolute_url) if part)
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not helpers.should_keep_candidate(title, matched_terms, searchable_text):
            continue
        note_parts = ["Enumerated through Jobvite careers listing HTML"]
        if reqid:
            note_parts.append(reqid)
        helpers.merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=title,
                url=absolute_url,
                source_url=source.url,
                location=location,
                matched_terms=matched_terms,
                notes="; ".join(note_parts),
            ),
        )
    limitations: list[str] = []
    if enumerated == 0:
        limitations.append("No Jobvite job rows matched the standard listing markup.")
    direct_job_pages_opened = 0
    for candidate_url, candidate in candidates_by_url.items():
        try:
            detail_html = http.fetch_text(candidate_url, timeout_seconds)
        except Exception:
            limitations.append(f"Detail fetch failed for {candidate_url}")
            continue
        direct_job_pages_opened += 1
        sections = extract_jobvite_detail_sections(detail_html)
        detail_parts = build_jobvite_detail_note_parts(sections)
        if detail_parts:
            candidate.notes = "; ".join(part for part in [candidate.notes, *detail_parts] if part)
    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="partial" if limitations else "complete",
        listing_pages_scanned=1,
        search_terms_tried=terms,
        result_pages_scanned="local_filter=1",
        direct_job_pages_opened=direct_job_pages_opened,
        enumerated_jobs=enumerated,
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("jobvite_html",), discover=discover_jobvite_jobs)
