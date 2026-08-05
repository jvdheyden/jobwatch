"""Thales search-results HTML provider."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from urllib.parse import urlencode, urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter
from discover.sources.generic_html import collect_job_links


THALES_RESULTS_PAGE_SIZE = 10
THALES_PAYLOAD_TERM_ALIASES = {
    "cryptography": (
        "kryptographie",
        "kryptografie",
    ),
    "multi-party computation": (
        "mehrparteienberechnung",
        "mehrparteien-berechnung",
        "sichere mehrparteienberechnung",
    ),
    "homomorphic encryption": (
        "homomorphe verschl\u00fcsselung",
        "homomorphe verschluesselung",
        "homomorpher verschl\u00fcsselung",
        "homomorpher verschluesselung",
    ),
}
THALES_JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(?P<payload>.*?)</script>',
    flags=re.IGNORECASE | re.DOTALL,
)
THALES_TASK_HEADINGS = (
    "Responsibilities",
    "Responsibility",
    "Tasks",
    "Your Tasks",
    "Key Tasks",
    "Key Responsibilities",
    "What You'll Do",
    "What You Will Do",
    "What Youll Do",
    "The Role",
    "About the Role",
    "Your Role",
    "Your Mission",
    "Job Description",
    "Position Summary",
    "Aufgaben",
    "Ihre Aufgaben",
    "Deine Aufgaben",
    "Vos missions",
    "Votre mission",
)
THALES_QUALIFICATION_HEADINGS = (
    "Qualifications",
    "Requirements",
    "Required Qualifications",
    "Minimum Qualifications",
    "Preferred Qualifications",
    "Required Skills",
    "Your Profile",
    "What You Bring",
    "What You'll Bring",
    "What You Will Bring",
    "What We're Looking For",
    "What Were Looking For",
    "Who You Are",
    "You Have",
    "You'll Need",
    "What You'll Need",
    "Anforderungen",
    "Ihr Profil",
    "Dein Profil",
    "Votre profil",
    "Profil",
)
THALES_COMPENSATION_HEADINGS = (
    "Compensation",
    "Salary",
    "Salary Range",
    "Pay Range",
    "Benefits",
    "Total Rewards",
    "What We Offer",
    "What We Offer You",
    "What we offer you",
    "Was wir Ihnen bieten",
    "Wir bieten",
    "Avantages",
)
THALES_DETAIL_STOP_HEADINGS = (
    *THALES_TASK_HEADINGS,
    *THALES_QUALIFICATION_HEADINGS,
    *THALES_COMPENSATION_HEADINGS,
    "About Us",
    "About Thales",
    "Company Description",
    "Apply",
    "Apply Now",
    "Share",
    "Similar Jobs",
    "Find similar jobs",
)
THALES_DETAIL_IGNORED_LINES = {
    "Apply",
    "Apply Now",
    "Share",
    "Similar Jobs",
    "Find similar jobs",
}
THALES_TASK_MARKERS = (
    "responsibilities",
    "responsibility",
    "tasks",
    "what you'll do",
    "what you will do",
    "your role",
    "your mission",
    "you will",
    "job description",
    "aufgaben",
    "ihre aufgaben",
    "vos missions",
)
THALES_QUALIFICATION_MARKERS = (
    "qualifications",
    "requirements",
    "required skills",
    "your profile",
    "what you bring",
    "what you'll need",
    "who you are",
    "you have",
    "ihr profil",
    "anforderungen",
    "votre profil",
)
THALES_COMPENSATION_MARKERS = (
    "compensation",
    "salary",
    "pay range",
    "benefits",
    "total rewards",
    "what we offer",
    "what we offer you",
    "was wir ihnen bieten",
    "avantages",
)


def iter_thales_json_objects(value: object) -> Iterator[dict[str, object]]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from iter_thales_json_objects(nested)
    elif isinstance(value, list):
        for item in value:
            yield from iter_thales_json_objects(item)


def _thales_json_ld_jobposting(content: str) -> dict[str, object]:
    for match in THALES_JSON_LD_RE.finditer(content or ""):
        try:
            payload = json.loads(match.group("payload").strip())
        except json.JSONDecodeError:
            continue
        for item in iter_thales_json_objects(payload):
            item_type = item.get("@type")
            item_types = item_type if isinstance(item_type, list) else [item_type]
            if "JobPosting" in item_types:
                return item
    return {}


def _thales_visible_text_lines(value: str) -> list[str]:
    text = value or ""
    lines: list[str] = []
    for _ in range(3):
        lines = helpers.extract_visible_text_lines_from_html(text)
        cleaned_text = "\n".join(lines)
        if "<" not in cleaned_text and "&lt;" not in cleaned_text:
            return lines
        if cleaned_text == text:
            return lines
        text = cleaned_text
    return lines


def _thales_json_field_text(value: object) -> str:
    return "\n".join(_thales_visible_text_lines(helpers.join_text(value)))


def _thales_base_salary_text(value: object) -> str:
    if not isinstance(value, dict):
        return _thales_json_field_text(value)

    parts: list[str] = []
    currency = value.get("currency")
    if currency:
        parts.append(str(currency))
    amount = value.get("value")
    if isinstance(amount, dict):
        min_value = amount.get("minValue")
        max_value = amount.get("maxValue")
        unit_text = amount.get("unitText")
        if min_value and max_value:
            parts.append(f"{min_value} - {max_value}")
        elif min_value:
            parts.append(str(min_value))
        elif max_value:
            parts.append(str(max_value))
        if unit_text:
            parts.append(str(unit_text))
    elif amount:
        parts.append(str(amount))
    return helpers.normalize_whitespace(" ".join(parts))


def thales_detail_text(content: str) -> str:
    job_posting = _thales_json_ld_jobposting(content)
    description = job_posting.get("description") if job_posting else ""
    if isinstance(description, str) and description.strip():
        return "\n".join(_thales_visible_text_lines(description))
    return "\n".join(helpers.extract_visible_text_lines_from_html(content))


def extract_thales_detail_sections(content: str) -> dict[str, str]:
    job_posting = _thales_json_ld_jobposting(content)
    detail_text = thales_detail_text(content)

    tasks = _thales_json_field_text(job_posting.get("responsibilities")) if job_posting else ""
    qualifications = (
        _thales_json_field_text(
            job_posting.get("qualifications")
            or job_posting.get("experienceRequirements")
            or job_posting.get("educationRequirements")
            or job_posting.get("skills")
        )
        if job_posting
        else ""
    )
    compensation = (
        _thales_base_salary_text(job_posting.get("baseSalary"))
        or _thales_json_field_text(job_posting.get("jobBenefits"))
        if job_posting
        else ""
    )

    if not tasks:
        tasks = helpers.extract_visible_text_section(
            detail_text,
            THALES_TASK_HEADINGS,
            THALES_DETAIL_STOP_HEADINGS,
            ignored_lines=THALES_DETAIL_IGNORED_LINES,
        )
    if not qualifications:
        qualifications = helpers.extract_visible_text_section(
            detail_text,
            THALES_QUALIFICATION_HEADINGS,
            THALES_DETAIL_STOP_HEADINGS,
            ignored_lines=THALES_DETAIL_IGNORED_LINES,
        )
    if not compensation:
        compensation = helpers.extract_visible_text_section(
            detail_text,
            THALES_COMPENSATION_HEADINGS,
            THALES_DETAIL_STOP_HEADINGS,
            ignored_lines=THALES_DETAIL_IGNORED_LINES,
        )

    if not tasks:
        tasks = helpers.extract_visible_text_marker_snippet(
            detail_text,
            THALES_TASK_MARKERS,
            THALES_DETAIL_STOP_HEADINGS,
            max_lines=4,
        )
    if not qualifications:
        qualifications = helpers.extract_visible_text_marker_snippet(
            detail_text,
            THALES_QUALIFICATION_MARKERS,
            THALES_DETAIL_STOP_HEADINGS,
            max_lines=4,
        )
    if not compensation:
        compensation = helpers.extract_visible_text_marker_snippet(
            detail_text,
            THALES_COMPENSATION_MARKERS,
            THALES_DETAIL_STOP_HEADINGS,
            max_lines=3,
        )

    return {
        "tasks": tasks,
        "qualifications": qualifications,
        "compensation": compensation,
    }


def apply_thales_detail_text(candidate: Candidate, content: str, terms: list[str]) -> bool:
    sections = extract_thales_detail_sections(content)
    detail_text = " ".join(part for part in sections.values() if part)
    original_notes = candidate.notes
    original_terms = list(candidate.matched_terms)
    if detail_text:
        candidate.matched_terms = sorted(
            set(candidate.matched_terms + helpers.match_terms_with_aliases(detail_text, terms, THALES_PAYLOAD_TERM_ALIASES))
        )

    note_parts = [candidate.notes] if candidate.notes else []
    if sections["tasks"]:
        note_parts.append(f"Tasks: {helpers.truncate_text(sections['tasks'], 260)}")
    if sections["qualifications"]:
        note_parts.append(f"Qualifications: {helpers.truncate_text(sections['qualifications'], 260)}")
    if sections["compensation"]:
        note_parts.append(f"Compensation: {helpers.truncate_text(sections['compensation'], 220)}")

    candidate.notes = "; ".join(dict.fromkeys(part for part in note_parts if part))
    return candidate.notes != original_notes or candidate.matched_terms != original_terms


def enrich_thales_candidate_details(
    candidates_by_url: dict[str, Candidate],
    terms: list[str],
    timeout_seconds: int,
    limitations: list[str],
) -> int:
    direct_job_pages_opened = 0
    failed_urls: list[str] = []
    missing_detail_urls: list[str] = []
    for candidate in candidates_by_url.values():
        try:
            detail_html = http.fetch_text(candidate.url, timeout_seconds)
        except Exception:
            failed_urls.append(candidate.url)
            continue
        direct_job_pages_opened += 1
        if not apply_thales_detail_text(candidate, detail_html, terms):
            missing_detail_urls.append(candidate.url)
        helpers.set_candidate_description(candidate, helpers.visible_text_from_html(detail_html))

    if failed_urls:
        limitations.append(f"Thales detail page fetch errored for {len(failed_urls)} matched roles")
    if missing_detail_urls:
        limitations.append(
            "Thales detail page enrichment yielded no substantive role detail for "
            f"{len(missing_detail_urls)} of {len(candidates_by_url)} matched roles"
        )
    return direct_job_pages_opened


def discover_thales_html(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    candidates_by_url: dict[str, Candidate] = {}
    raw_seen_ids: set[str] = set()
    limitations: list[str] = []
    term_summaries: list[str] = []
    errored_terms: list[str] = []
    total_pages_scanned = 0

    for term in terms:
        term_pages_scanned = 0
        term_total = 0
        term_visible_total = 0
        offset = 0
        page_signatures: set[str] = set()
        while True:
            params = {"keywords": term}
            if offset:
                params["from"] = str(offset)
                params["s"] = "1"
            search_url = f"{source.url}?{urlencode(params)}"
            try:
                html = http.fetch_text(search_url, timeout_seconds)
            except Exception:
                errored_terms.append(term)
                break

            payload = helpers.extract_json_object_after_marker(html, '"eagerLoadRefineSearch":')
            if not payload:
                errored_terms.append(term)
                break

            jobs = payload.get("data", {}).get("jobs", [])
            hits = int(payload.get("hits", 0) or 0)
            if term_total == 0:
                term_total = int(payload.get("totalHits", 0) or 0)
            if not jobs:
                break

            page_signature = ",".join(str(job.get("jobSeqNo") or job.get("reqId") or "") for job in jobs[:10])
            if not page_signature or page_signature in page_signatures:
                break
            page_signatures.add(page_signature)

            term_pages_scanned += 1
            total_pages_scanned += 1
            term_visible_total += hits or len(jobs)
            link_map = collect_job_links(html, source.url, "/global/en/job/")
            for job in jobs:
                req_id = job.get("reqId") or job.get("jobId") or ""
                job_url = next((url for url in link_map if f"/job/{req_id}/" in url), None)
                if not job_url:
                    title_slug = re.sub(r"-{2,}", "-", re.sub(r"[^A-Za-z0-9]+", "-", job.get("title") or "")).strip("-")
                    job_url = (
                        f"{urlparse(source.url).scheme}://{urlparse(source.url).netloc}/global/en/job/{req_id}/{title_slug}"
                        if req_id
                        else source.url
                    )
                raw_id = job.get("jobSeqNo") or req_id or job_url
                raw_seen_ids.add(str(raw_id))
                title = job.get("title") or "unknown"
                location = job.get("cityStateCountry") or job.get("location") or job.get("workLocation") or "unknown"
                searchable_text = " ".join(
                    part
                    for part in [
                        title,
                        job.get("descriptionTeaser") or "",
                        helpers.join_text(job.get("ml_skills")),
                        job.get("category") or "",
                        location,
                        job.get("workLocation") or "",
                    ]
                    if part
                )
                matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
                if not matched_terms:
                    continue
                helpers.merge_candidate(
                    candidates_by_url,
                    Candidate(
                        employer=source.source,
                        title=title,
                        url=job_url,
                        source_url=source.url,
                        location=location,
                        matched_terms=matched_terms,
                        notes=f"Enumerated through Thales search-results HTML for '{term}'",
                    ),
                )

            offset += hits or len(jobs)
            if (hits or len(jobs)) < THALES_RESULTS_PAGE_SIZE:
                break
            if term_total and offset >= term_total:
                break

        term_summaries.append(f"{term}={term_pages_scanned}p/{term_visible_total}of{term_total}")

    if errored_terms:
        limitations.append("Errored terms: " + ", ".join(sorted(set(errored_terms))))
    direct_job_pages_opened = enrich_thales_candidate_details(
        candidates_by_url,
        terms,
        timeout_seconds,
        limitations,
    )

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


SOURCE = SourceAdapter(modes=("thales_html",), discover=discover_thales_html)
