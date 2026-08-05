"""Eightfold PCSx search provider.

Supported discovery modes:
- `eightfold_api`
- `infineon_api`

Expected source URL shape:
- `https://<host>/careers` pages exposing `/api/pcsx/search`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from urllib.parse import urlencode, urljoin, urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


INFINEON_RESULTS_PAGE_SIZE = 10
EIGHTFOLD_MAX_PAGES = 10
EIGHTFOLD_DOMAINS_BY_HOST = {
    "apply.careers.microsoft.com": "microsoft.com",
    "jobs.infineon.com": "infineon.com",
}
EIGHTFOLD_JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(?P<payload>.*?)</script>',
    flags=re.IGNORECASE | re.DOTALL,
)
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
        "homomorphe verschlüsselung",
        "homomorphe verschluesselung",
        "homomorpher verschlüsselung",
        "homomorpher verschluesselung",
    ),
}
EIGHTFOLD_TASK_HEADINGS = (
    "Responsibilities",
    "Responsibility",
    "Tasks",
    "Your Tasks",
    "Ihre Aufgaben",
    "Job Description",
    "What You'll Do",
    "What You Will Do",
    "In Your New Role You Will",
    "In your new role you will",
)
EIGHTFOLD_QUALIFICATION_HEADINGS = (
    "Qualifications",
    "Requirements",
    "Required Qualifications",
    "Minimum Qualifications",
    "Preferred Qualifications",
    "Your Profile",
    "Ihr Profil",
    "Anforderungen",
    "What You Bring",
    "What You'll Need",
    "What You Need",
    "You are best equipped for this task if you have",
    "You are best equipped for this position if you have",
)
EIGHTFOLD_COMPENSATION_HEADINGS = (
    "Compensation",
    "Salary",
    "Salary Range",
    "Pay Range",
    "Benefits",
    "What we offer you",
    "Was wir Ihnen bieten",
)
EIGHTFOLD_DETAIL_STOP_HEADINGS = (
    *EIGHTFOLD_TASK_HEADINGS,
    *EIGHTFOLD_QUALIFICATION_HEADINGS,
    *EIGHTFOLD_COMPENSATION_HEADINGS,
    "About Us",
    "About Infineon",
    "Company Description",
    "Contact",
    "Further Information",
    "Further information",
    "Apply",
    "Apply Now",
    "Share",
    "Find similar jobs",
)
EIGHTFOLD_DETAIL_IGNORED_LINES = {
    "Apply",
    "Apply Now",
    "Share",
    "Find similar jobs",
}
EIGHTFOLD_TASK_MARKERS = (
    "responsibilities",
    "responsibility",
    "job description",
    "what you'll do",
    "what you will do",
    "your tasks",
    "in your new role you will",
)
EIGHTFOLD_QUALIFICATION_MARKERS = (
    "qualifications",
    "requirements",
    "your profile",
    "what you'll need",
    "what you need",
    "you are best equipped",
)
EIGHTFOLD_COMPENSATION_MARKERS = (
    "salary",
    "compensation",
    "pay range",
    "salary range",
    "benefits",
)


def eightfold_domain_for_source(source: SourceConfig) -> str:
    host = urlparse(source.url).netloc.lower()
    if host in EIGHTFOLD_DOMAINS_BY_HOST:
        return EIGHTFOLD_DOMAINS_BY_HOST[host]
    if host.startswith("jobs.") and len(host.split(".")) > 2:
        return host.removeprefix("jobs.")
    raise ValueError(f"Could not infer Eightfold domain for {source.url}")


def iter_json_objects(value: object) -> Iterator[dict[str, object]]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from iter_json_objects(nested)
    elif isinstance(value, list):
        for item in value:
            yield from iter_json_objects(item)


def extract_eightfold_json_ld_description(content: str) -> str:
    for match in EIGHTFOLD_JSON_LD_RE.finditer(content or ""):
        try:
            payload = json.loads(match.group("payload").strip())
        except json.JSONDecodeError:
            continue
        for item in iter_json_objects(payload):
            item_type = item.get("@type")
            item_types = item_type if isinstance(item_type, list) else [item_type]
            if "JobPosting" not in item_types:
                continue
            description = item.get("description")
            if isinstance(description, str) and description.strip():
                return description
    return ""


def eightfold_detail_text(content: str) -> tuple[str, bool]:
    json_ld_description = extract_eightfold_json_ld_description(content)
    if json_ld_description:
        return "\n".join(helpers.extract_visible_text_lines_from_html(json_ld_description)), True
    return "\n".join(helpers.extract_visible_text_lines_from_html(content)), False


def extract_eightfold_detail_sections(content: str) -> dict[str, str]:
    detail_text, from_json_ld = eightfold_detail_text(content)
    tasks = helpers.extract_visible_text_section(
        detail_text,
        EIGHTFOLD_TASK_HEADINGS,
        EIGHTFOLD_DETAIL_STOP_HEADINGS,
        ignored_lines=EIGHTFOLD_DETAIL_IGNORED_LINES,
    )
    qualifications = helpers.extract_visible_text_section(
        detail_text,
        EIGHTFOLD_QUALIFICATION_HEADINGS,
        EIGHTFOLD_DETAIL_STOP_HEADINGS,
        ignored_lines=EIGHTFOLD_DETAIL_IGNORED_LINES,
    )
    compensation = helpers.extract_visible_text_section(
        detail_text,
        EIGHTFOLD_COMPENSATION_HEADINGS,
        EIGHTFOLD_DETAIL_STOP_HEADINGS,
        ignored_lines=EIGHTFOLD_DETAIL_IGNORED_LINES,
    )
    if not tasks:
        tasks = helpers.extract_visible_text_marker_snippet(
            detail_text,
            EIGHTFOLD_TASK_MARKERS,
            EIGHTFOLD_DETAIL_STOP_HEADINGS,
            max_lines=4,
        )
    if not qualifications:
        qualifications = helpers.extract_visible_text_marker_snippet(
            detail_text,
            EIGHTFOLD_QUALIFICATION_MARKERS,
            EIGHTFOLD_DETAIL_STOP_HEADINGS,
            max_lines=4,
        )
    if not compensation:
        compensation = helpers.extract_visible_text_marker_snippet(
            detail_text,
            EIGHTFOLD_COMPENSATION_MARKERS,
            EIGHTFOLD_DETAIL_STOP_HEADINGS,
            max_lines=4,
        )
    if from_json_ld and not any((tasks, qualifications, compensation)):
        tasks = helpers.normalize_whitespace(detail_text)
    return {
        "tasks": tasks,
        "qualifications": qualifications,
        "compensation": compensation,
    }


def apply_eightfold_detail_text(candidate: Candidate, content: str, terms: list[str]) -> bool:
    sections = extract_eightfold_detail_sections(content)
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


def enrich_infineon_candidate_details(
    source: SourceConfig,
    candidates_by_url: dict[str, Candidate],
    terms: list[str],
    timeout_seconds: int,
    limitations: list[str],
) -> int:
    if not candidates_by_url:
        return 0

    direct_job_pages_opened = 0
    failed_urls: list[str] = []
    missing_detail_urls: list[str] = []
    source_url = source.url.rstrip("/")
    for candidate in candidates_by_url.values():
        if candidate.url.rstrip("/") == source_url:
            continue
        try:
            detail_html = http.fetch_text(candidate.url, timeout_seconds)
        except Exception:
            failed_urls.append(candidate.url)
            continue
        direct_job_pages_opened += 1
        if not apply_eightfold_detail_text(candidate, detail_html, terms):
            missing_detail_urls.append(candidate.url)

    if failed_urls:
        limitations.append(f"Infineon detail page fetch errored for {len(failed_urls)} matched roles")
    if missing_detail_urls:
        limitations.append(
            "Infineon detail page enrichment yielded no substantive role detail for "
            f"{len(missing_detail_urls)} of {len(candidates_by_url)} matched roles"
        )
    return direct_job_pages_opened


def discover_eightfold_api(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    candidates_by_url: dict[str, Candidate] = {}
    raw_seen_ids: set[str] = set()
    limitations: list[str] = []
    term_summaries: list[str] = []
    errored_terms: list[str] = []
    total_pages_scanned = 0
    parsed_source = urlparse(source.url)
    base_url = f"{parsed_source.scheme}://{parsed_source.netloc}"
    domain = eightfold_domain_for_source(source)

    for term in terms:
        term_pages_scanned = 0
        term_total = 0
        start = 0
        while True:
            query = urlencode(
                {
                    "domain": domain,
                    "query": term,
                    "location": "",
                    "start": start,
                    "sort_by": "timestamp",
                }
            )
            endpoint = f"{base_url}/api/pcsx/search?{query}&"
            try:
                payload = http.fetch_json(endpoint, timeout_seconds)
            except Exception:
                errored_terms.append(term)
                break

            data = payload.get("data", {}) if isinstance(payload, dict) else {}
            positions = data.get("positions", [])
            term_total = int(data.get("count", term_total or 0) or 0)
            if not positions:
                break

            term_pages_scanned += 1
            total_pages_scanned += 1
            for position in positions:
                job_id = str(position.get("id") or position.get("atsJobId") or "")
                if job_id:
                    raw_seen_ids.add(job_id)
                title = position.get("name") or "unknown"
                url = urljoin(source.url, position.get("positionUrl") or "")
                location = "; ".join(position.get("locations") or position.get("standardizedLocations") or []) or "unknown"
                workplace_values = position.get("efcustomTextWorkplaceType") or []
                remote = workplace_values[0] if workplace_values else (position.get("workLocationOption") or "unknown")
                department = position.get("department") or ""
                searchable_text = " ".join(
                    part
                    for part in [title, location, remote, department, position.get("displayJobId") or ""]
                    if part
                )
                matched_terms = sorted(
                    set(helpers.match_terms_with_aliases(searchable_text, terms, THALES_PAYLOAD_TERM_ALIASES))
                )
                if not matched_terms:
                    continue
                helpers.merge_candidate(
                    candidates_by_url,
                    Candidate(
                        employer=source.source,
                        title=title,
                        url=url or source.url,
                        source_url=source.url,
                        location=location,
                        remote=remote,
                        matched_terms=matched_terms,
                        notes=f"Enumerated through Eightfold PCSx search for '{term}'",
                    ),
                )

            start += len(positions)
            if len(positions) < INFINEON_RESULTS_PAGE_SIZE:
                break
            if term_total and start >= term_total:
                break
            if term_pages_scanned >= EIGHTFOLD_MAX_PAGES:
                limitations.append(f"Eightfold PCSx search for '{term}' hit the page cap ({EIGHTFOLD_MAX_PAGES})")
                break

        term_summaries.append(f"{term}={term_pages_scanned}p/{term_total}")

    if errored_terms:
        limitations.append("Errored terms: " + ", ".join(sorted(set(errored_terms))))

    direct_job_pages_opened = 0
    if source.discovery_mode == "infineon_api":
        direct_job_pages_opened = enrich_infineon_candidate_details(
            source,
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


discover_infineon_api = discover_eightfold_api

SOURCE = SourceAdapter(modes=("eightfold_api", "infineon_api"), discover=discover_eightfold_api)
