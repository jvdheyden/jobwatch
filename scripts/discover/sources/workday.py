"""Workday jobs API provider.

Supported discovery modes:
- `workday_api`

Expected source URL shape:
- `https://<tenant>.wd*.myworkdayjobs.com/<site>`
"""

from __future__ import annotations

from urllib.parse import urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


WORKDAY_RESULTS_PAGE_SIZE = 20
WORKDAY_TASK_HEADINGS = (
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
)
WORKDAY_QUALIFICATION_HEADINGS = (
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
WORKDAY_COMPENSATION_HEADINGS = (
    "Compensation",
    "Pay Range",
    "Salary Range",
    "Total Rewards",
)
WORKDAY_DETAIL_STOP_HEADINGS = (
    *WORKDAY_TASK_HEADINGS,
    *WORKDAY_QUALIFICATION_HEADINGS,
    *WORKDAY_COMPENSATION_HEADINGS,
    "About Us",
    "About the Company",
    "About Bose",
    "Benefits",
    "Equal Opportunity",
    "Equal Employment Opportunity",
    "EEO Statement",
    "Apply",
)
WORKDAY_COMPENSATION_MARKERS = (
    "salary range",
    "pay range",
    "compensation",
    "base pay",
    "hourly rate",
)


def build_workday_job_url(source_url: str, external_path: str) -> str:
    if not external_path:
        return source_url
    parsed = urlparse(external_path)
    if parsed.scheme and parsed.netloc:
        return helpers.normalize_url_without_fragment(external_path)
    return helpers.normalize_url_without_fragment(source_url.rstrip("/") + "/" + external_path.lstrip("/"))


def build_workday_job_detail_endpoint(source_url: str, external_path: str) -> str:
    parsed = urlparse(source_url)
    tenant = parsed.netloc.split(".")[0]
    path_bits = [bit for bit in parsed.path.split("/") if bit]
    if not path_bits:
        raise ValueError(f"Could not derive Workday site token from {source_url}")
    site = path_bits[0]
    suffix = external_path if external_path.startswith("/") else "/" + external_path
    return f"{parsed.scheme}://{parsed.netloc}/wday/cxs/{tenant}/{site}{suffix}"


def extract_workday_detail_sections(job_description_html: str) -> dict[str, str]:
    detail_text = "\n".join(helpers.extract_visible_text_lines_from_html(job_description_html))
    tasks = helpers.extract_visible_text_section(
        detail_text,
        WORKDAY_TASK_HEADINGS,
        WORKDAY_DETAIL_STOP_HEADINGS,
    )
    qualifications = helpers.extract_visible_text_section(
        detail_text,
        WORKDAY_QUALIFICATION_HEADINGS,
        WORKDAY_DETAIL_STOP_HEADINGS,
    )
    compensation_section = helpers.extract_visible_text_section(
        detail_text,
        WORKDAY_COMPENSATION_HEADINGS,
        WORKDAY_DETAIL_STOP_HEADINGS,
    )
    compensation = compensation_section or helpers.extract_visible_text_marker_snippet(
        detail_text,
        WORKDAY_COMPENSATION_MARKERS,
        WORKDAY_DETAIL_STOP_HEADINGS,
    )
    return {
        "tasks": tasks,
        "qualifications": qualifications,
        "compensation": compensation,
    }


def build_workday_detail_note_parts(sections: dict[str, str]) -> list[str]:
    parts: list[str] = []
    if sections.get("tasks"):
        parts.append(f"Tasks: {helpers.truncate_text(sections['tasks'], 260)}")
    if sections.get("qualifications"):
        parts.append(f"Qualifications: {helpers.truncate_text(sections['qualifications'], 260)}")
    if sections.get("compensation"):
        parts.append(f"Compensation: {helpers.truncate_text(sections['compensation'], 200)}")
    return parts


def fetch_workday_job_detail(source_url: str, external_path: str, timeout_seconds: int) -> dict:
    detail_url = build_workday_job_detail_endpoint(source_url, external_path)
    response = http.fetch_json(detail_url, timeout_seconds)
    if not isinstance(response, dict):
        return {}
    info = response.get("jobPostingInfo")
    return info if isinstance(info, dict) else {}


def discover_workday_api(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    parsed_source = urlparse(source.url)
    if "myworkdayjobs.com" not in parsed_source.netloc:
        raise ValueError(f"Workday discovery requires a Workday board URL, got {source.url}")
    path_bits = [bit for bit in parsed_source.path.split("/") if bit]
    if not path_bits:
        raise ValueError(f"Could not derive Workday site token from {source.url}")
    tenant = parsed_source.netloc.split(".")[0]
    site = path_bits[0]
    endpoint = f"{parsed_source.scheme}://{parsed_source.netloc}/wday/cxs/{tenant}/{site}/jobs"
    candidates_by_url: dict[str, Candidate] = {}
    external_paths_by_url: dict[str, str] = {}
    raw_seen_ids: set[str] = set()
    limitations: list[str] = []
    term_summaries: list[str] = []
    errored_terms: list[str] = []
    total_pages_scanned = 0

    for term in terms:
        term_pages_scanned = 0
        term_total = 0
        offset = 0
        page_signatures: set[str] = set()
        while True:
            payload = {"limit": WORKDAY_RESULTS_PAGE_SIZE, "offset": offset, "searchText": term}
            try:
                response = http.post_json(endpoint, payload, timeout_seconds, headers={"Referer": source.url})
            except Exception:
                errored_terms.append(term)
                break

            postings = response.get("jobPostings", []) if isinstance(response, dict) else []
            if term_total == 0:
                term_total = int(response.get("total", 0) or 0) if isinstance(response, dict) else 0
            if not postings:
                break

            page_signature = ",".join(
                str(posting.get("externalPath") or posting.get("title") or "") for posting in postings[:10]
            )
            if not page_signature or page_signature in page_signatures:
                break
            page_signatures.add(page_signature)

            term_pages_scanned += 1
            total_pages_scanned += 1
            for posting in postings:
                external_path = posting.get("externalPath") or ""
                title = posting.get("title") or "unknown"
                absolute_url = build_workday_job_url(source.url, external_path)
                raw_id = external_path or title
                raw_seen_ids.add(raw_id)
                location = posting.get("locationsText") or "unknown"
                searchable_text = " ".join(
                    part
                    for part in [
                        title,
                        location,
                        posting.get("postedOn") or "",
                        helpers.join_text(posting.get("bulletFields")),
                    ]
                    if part
                )
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
                        notes=f"Enumerated through Workday jobs API for '{term}'",
                    ),
                )
                if external_path and absolute_url not in external_paths_by_url:
                    external_paths_by_url[absolute_url] = external_path

            offset += len(postings)
            if len(postings) < WORKDAY_RESULTS_PAGE_SIZE:
                break
            if term_total and offset >= term_total:
                break

        term_summaries.append(f"{term}={term_pages_scanned}p/{term_total}")

    direct_job_pages_opened = 0
    for candidate_url, external_path in external_paths_by_url.items():
        candidate = candidates_by_url.get(candidate_url)
        if candidate is None:
            continue
        try:
            posting_info = fetch_workday_job_detail(source.url, external_path, timeout_seconds)
        except Exception:
            limitations.append(f"Detail fetch failed for {candidate_url}")
            continue
        direct_job_pages_opened += 1
        sections = extract_workday_detail_sections(posting_info.get("jobDescription") or "")
        detail_parts = build_workday_detail_note_parts(sections)
        if detail_parts:
            candidate.notes = "; ".join(part for part in [candidate.notes, *detail_parts] if part)

    if errored_terms:
        limitations.append("Errored terms: " + ", ".join(sorted(set(errored_terms))))

    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="partial" if limitations else "complete",
        listing_pages_scanned=total_pages_scanned,
        search_terms_tried=terms,
        result_pages_scanned=", ".join(term_summaries) if term_summaries else "none",
        direct_job_pages_opened=direct_job_pages_opened,
        enumerated_jobs=len(raw_seen_ids),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("workday_api",), discover=discover_workday_api)
