"""BambooHR careers API provider.

Supported discovery modes:
- `bamboohr_api`

Expected source URL shape:
- A `<tenant>.bamboohr.com` careers page; enumeration goes through the
  tenant's `/careers/list` and `/careers/<id>/detail` JSON endpoints.
"""

from __future__ import annotations

from html import unescape
from urllib.parse import urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


BAMBOOHR_HOST_SUFFIX = ".bamboohr.com"
BAMBOOHR_TASK_HEADINGS = (
    "Overview",
    "Role Overview",
    "About the Role",
    "About this Role",
    "The Role",
    "Your Role",
    "Position Summary",
    "Position Overview",
    "Job Description",
    "Job Summary",
    "Job Purpose",
    "Summary",
    "Responsibilities",
    "Key Responsibilities",
    "What You'll Do",
    "What You Will Do",
    "What Youll Do",
    "What You'll Be Doing",
    "Your Mission",
    "Your Responsibilities",
)
BAMBOOHR_QUALIFICATION_HEADINGS = (
    "Qualifications",
    "Requirements",
    "Required Qualifications",
    "Required Skills",
    "Minimum Qualifications",
    "Preferred Qualifications",
    "Basic Qualifications",
    "Skills & Requirements",
    "What You Bring",
    "What You'll Bring",
    "What You Will Bring",
    "What We're Looking For",
    "Who You Are",
    "You Have",
    "You'll Need",
    "What You'll Need",
)
BAMBOOHR_COMPENSATION_HEADINGS = (
    "Compensation",
    "Pay Range",
    "Salary Range",
    "Total Rewards",
)
BAMBOOHR_DETAIL_STOP_HEADINGS = (
    *BAMBOOHR_TASK_HEADINGS,
    *BAMBOOHR_QUALIFICATION_HEADINGS,
    *BAMBOOHR_COMPENSATION_HEADINGS,
    "About Us",
    "About the Company",
    "Benefits",
    "Perks",
    "Perks & Benefits",
    "Equal Opportunity",
    "Equal Employment Opportunity",
    "EEO Statement",
    "Apply",
)
BAMBOOHR_COMPENSATION_MARKERS = (
    "salary range",
    "pay range",
    "compensation",
    "base pay",
    "hourly rate",
)


def _tenant(source_url: str) -> str:
    host = (urlparse(source_url).hostname or "").lower()
    if not host.endswith(BAMBOOHR_HOST_SUFFIX):
        return ""
    return host[: -len(BAMBOOHR_HOST_SUFFIX)]


def _format_location(job: dict) -> str:
    parts: list[str] = []
    ats_location = job.get("atsLocation") if isinstance(job, dict) else None
    if isinstance(ats_location, dict):
        for key in ("city", "state", "province", "country"):
            value = ats_location.get(key)
            if isinstance(value, str):
                cleaned = helpers.normalize_whitespace(unescape(value))
                if cleaned and cleaned not in parts:
                    parts.append(cleaned)
    if not parts:
        legacy_location = job.get("location") if isinstance(job, dict) else None
        if isinstance(legacy_location, dict):
            for key in ("city", "state", "addressCountry"):
                value = legacy_location.get(key)
                if isinstance(value, str):
                    cleaned = helpers.normalize_whitespace(unescape(value))
                    if cleaned and cleaned not in parts:
                        parts.append(cleaned)
    return ", ".join(parts) or "unknown"


def extract_bamboohr_detail_sections(description_html: str) -> dict[str, str]:
    detail_text = "\n".join(helpers.extract_visible_text_lines_from_html(description_html or ""))
    tasks = helpers.extract_visible_text_section(
        detail_text,
        BAMBOOHR_TASK_HEADINGS,
        BAMBOOHR_DETAIL_STOP_HEADINGS,
    )
    qualifications = helpers.extract_visible_text_section(
        detail_text,
        BAMBOOHR_QUALIFICATION_HEADINGS,
        BAMBOOHR_DETAIL_STOP_HEADINGS,
    )
    compensation = helpers.extract_visible_text_section(
        detail_text,
        BAMBOOHR_COMPENSATION_HEADINGS,
        BAMBOOHR_DETAIL_STOP_HEADINGS,
    ) or helpers.extract_visible_text_marker_snippet(
        detail_text,
        BAMBOOHR_COMPENSATION_MARKERS,
        BAMBOOHR_DETAIL_STOP_HEADINGS,
    )
    description_fallback = ""
    if not tasks and not qualifications:
        description_fallback = " ".join(helpers.split_visible_lines(detail_text))
    return {
        "tasks": tasks,
        "qualifications": qualifications,
        "compensation": compensation,
        "description": description_fallback,
    }


def build_bamboohr_detail_note_parts(sections: dict[str, str], department: str, employment_status: str) -> list[str]:
    parts: list[str] = []
    if department:
        parts.append(f"Department: {department}")
    if employment_status:
        parts.append(f"Employment: {employment_status}")
    if sections.get("tasks"):
        parts.append(f"Tasks: {helpers.truncate_text(sections['tasks'], 260)}")
    if sections.get("qualifications"):
        parts.append(f"Qualifications: {helpers.truncate_text(sections['qualifications'], 260)}")
    if sections.get("compensation"):
        parts.append(f"Compensation: {helpers.truncate_text(sections['compensation'], 200)}")
    if sections.get("description") and not sections.get("tasks") and not sections.get("qualifications"):
        parts.append(f"Description: {helpers.truncate_text(sections['description'], 260)}")
    return parts


def discover_bamboohr_jobs(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    tenant = _tenant(source.url)
    if not tenant:
        return Coverage(
            source=source.source,
            source_url=source.url,
            discovery_mode=source.discovery_mode,
            cadence_group=source.cadence_group,
            last_checked=source.last_checked,
            due_today=False,
            status="failed",
            listing_pages_scanned="unknown",
            search_terms_tried=terms,
            result_pages_scanned="unknown",
            direct_job_pages_opened=0,
            enumerated_jobs=0,
            matched_jobs=0,
            limitations=[f"Could not derive BambooHR tenant from URL: {source.url}"],
            candidates=[],
        )

    list_endpoint = f"https://{tenant}{BAMBOOHR_HOST_SUFFIX}/careers/list"
    detail_root = f"https://{tenant}{BAMBOOHR_HOST_SUFFIX}/careers"
    payload = http.fetch_json(list_endpoint, timeout_seconds)
    jobs = payload.get("result", []) if isinstance(payload, dict) else []
    candidates_by_url: dict[str, Candidate] = {}
    direct_job_pages_opened = 0
    limitations: list[str] = []

    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_id = str(job.get("id") or "").strip()
        if not job_id:
            continue
        title = helpers.normalize_whitespace(unescape(str(job.get("jobOpeningName") or ""))) or "unknown"
        department = helpers.normalize_whitespace(unescape(str(job.get("departmentLabel") or "")))
        employment_status = helpers.normalize_whitespace(unescape(str(job.get("employmentStatusLabel") or "")))
        location = _format_location(job)
        share_url = helpers.normalize_url_without_fragment(f"{detail_root}/{job_id}")

        detail_url = f"{detail_root}/{job_id}/detail"
        description_html = ""
        try:
            detail_payload = http.fetch_json(detail_url, timeout_seconds)
            direct_job_pages_opened += 1
        except Exception as exc:
            limitations.append(f"Could not fetch detail for {share_url}: {type(exc).__name__}: {exc}")
            detail_payload = None
        if isinstance(detail_payload, dict):
            job_opening = (detail_payload.get("result") or {}).get("jobOpening") if isinstance(detail_payload.get("result"), dict) else None
            if isinstance(job_opening, dict):
                description_html = str(job_opening.get("description") or "")
                detail_location = _format_location(job_opening)
                if detail_location and detail_location != "unknown":
                    location = detail_location
                detail_title = helpers.normalize_whitespace(unescape(str(job_opening.get("jobOpeningName") or "")))
                if detail_title:
                    title = detail_title
                if not department:
                    department = helpers.normalize_whitespace(unescape(str(job_opening.get("departmentLabel") or "")))
                if not employment_status:
                    employment_status = helpers.normalize_whitespace(unescape(str(job_opening.get("employmentStatusLabel") or "")))

        description_text = " ".join(helpers.extract_visible_text_lines_from_html(description_html))
        searchable_text = " ".join(part for part in (title, department, employment_status, location, description_text, share_url) if part)
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not matched_terms:
            continue

        sections = extract_bamboohr_detail_sections(description_html)
        note_parts = ["Enumerated through BambooHR careers API"]
        note_parts.extend(build_bamboohr_detail_note_parts(sections, department, employment_status))

        bamboo_candidate = Candidate(
            employer=source.source,
            title=title,
            url=share_url,
            source_url=source.url,
            location=location,
            matched_terms=matched_terms,
            notes="; ".join(part for part in note_parts if part),
        )
        helpers.set_candidate_description(bamboo_candidate, helpers.visible_text_from_html(description_html))
        helpers.merge_candidate(candidates_by_url, bamboo_candidate)

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
        enumerated_jobs=len(jobs),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("bamboohr_api",), discover=discover_bamboohr_jobs)
