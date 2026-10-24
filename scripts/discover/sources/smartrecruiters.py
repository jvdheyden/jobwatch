"""SmartRecruiters public postings API provider.

Supported discovery modes:
- `smartrecruiters_api`

Expected source URL shape:
- `https://careers.smartrecruiters.com/<CompanyIdentifier>`
- `https://jobs.smartrecruiters.com/<CompanyIdentifier>`
"""

from __future__ import annotations

from urllib.parse import quote, urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


PAGE_SIZE = 100
MAX_PAGES = 20


def smartrecruiters_company_id(source_url: str) -> str:
    path_bits = [bit for bit in urlparse(source_url).path.split("/") if bit]
    if not path_bits:
        raise ValueError(f"Could not derive SmartRecruiters company identifier from {source_url}")
    return path_bits[0]


def build_smartrecruiters_job_url(company_id: str, posting_id: str, title: str) -> str:
    slug = helpers.slugify_title(title)
    suffix = f"{posting_id}-{slug}" if slug else posting_id
    return f"https://jobs.smartrecruiters.com/{quote(company_id)}/{suffix}"


def _label(value: object) -> str:
    if isinstance(value, dict):
        return helpers.normalize_whitespace(helpers.join_text(value.get("label")))
    return ""


def _location(posting: dict) -> tuple[str, str]:
    location = posting.get("location") if isinstance(posting.get("location"), dict) else {}
    full_location = helpers.join_text(location.get("fullLocation"))
    parts = full_location.split(",") if full_location else [
        helpers.join_text(location.get(key)) for key in ("city", "region", "country")
    ]
    # The API leaves empty segments for missing regions, e.g. "Beijing, , China".
    text = ", ".join(part for part in (helpers.normalize_whitespace(part) for part in parts) if part)
    if location.get("remote") is True:
        remote = "remote"
    elif location.get("hybrid") is True:
        remote = "hybrid"
    else:
        remote = helpers.infer_remote_status(text)
    return text or "unknown", remote


def discover_smartrecruiters_api(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    company_id = smartrecruiters_company_id(source.url)
    endpoint = f"https://api.smartrecruiters.com/v1/companies/{quote(company_id)}/postings"
    postings: list[dict] = []
    reported_total = 0
    pages_scanned = 0

    for page in range(MAX_PAGES):
        payload = http.fetch_json(f"{endpoint}?limit={PAGE_SIZE}&offset={page * PAGE_SIZE}", timeout_seconds)
        pages_scanned += 1
        content = payload.get("content") if isinstance(payload, dict) else []
        content = [posting for posting in content or [] if isinstance(posting, dict)]
        reported_total = int(payload.get("totalFound", 0) or 0) if isinstance(payload, dict) else 0
        postings.extend(content)
        if len(content) < PAGE_SIZE or len(postings) >= reported_total:
            break

    candidates_by_url: dict[str, Candidate] = {}
    for posting in postings:
        title = helpers.normalize_whitespace(helpers.join_text(posting.get("name"))) or "unknown"
        posting_id = helpers.normalize_whitespace(helpers.join_text(posting.get("id")))
        location, remote = _location(posting)
        function = _label(posting.get("function"))
        department = _label(posting.get("department"))
        employment_type = _label(posting.get("typeOfEmployment"))
        experience = _label(posting.get("experienceLevel"))
        custom_labels = [
            helpers.normalize_whitespace(helpers.join_text(field.get("valueLabel")))
            for field in posting.get("customField") or []
            if isinstance(field, dict)
        ]

        searchable_text = " ".join(
            part for part in [title, function, department, location, employment_type, experience, *custom_labels] if part
        )
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not matched_terms:
            continue

        note_parts = ["Enumerated through SmartRecruiters postings API"]
        if function:
            note_parts.append(f"Function: {function}")
        if department:
            note_parts.append(f"Department: {department}")
        if experience:
            note_parts.append(f"Level: {experience}")
        if employment_type:
            note_parts.append(f"Type: {employment_type}")

        helpers.merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=title,
                url=build_smartrecruiters_job_url(company_id, posting_id, title) if posting_id else source.url,
                source_url=source.url,
                location=location,
                remote=remote,
                matched_terms=matched_terms,
                notes="; ".join(note_parts),
            ),
        )

    limitations: list[str] = []
    status = "complete"
    if reported_total > len(postings):
        status = "partial"
        limitations.append(
            f"SmartRecruiters reported {reported_total} postings but {len(postings)} were enumerated "
            f"within {pages_scanned} page(s) of {PAGE_SIZE}."
        )

    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status=status,
        listing_pages_scanned=pages_scanned,
        search_terms_tried=terms,
        result_pages_scanned=f"api_pages={pages_scanned}",
        direct_job_pages_opened=0,
        enumerated_jobs=len(postings),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("smartrecruiters_api",), discover=discover_smartrecruiters_api)
