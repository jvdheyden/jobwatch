"""Pinpoint public postings feed provider.

Supported discovery modes:
- `pinpoint_api`

Expected source URL shape:
- `https://<company>.pinpointhq.com/`
"""

from __future__ import annotations

from urllib.parse import urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


DESCRIPTION_FIELDS = ("description", "key_responsibilities", "skills_knowledge_expertise", "benefits")


def pinpoint_postings_url(source_url: str) -> str:
    parsed = urlparse(source_url)
    if not parsed.netloc:
        raise ValueError(f"Could not derive Pinpoint host from {source_url}")
    return f"{parsed.scheme or 'https'}://{parsed.netloc}/postings.json"


def _name(value: object) -> str:
    if isinstance(value, dict):
        return helpers.normalize_whitespace(helpers.join_text(value.get("name")))
    return ""


def discover_pinpoint_api(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    payload = http.fetch_json(pinpoint_postings_url(source.url), timeout_seconds)
    postings = payload.get("data") if isinstance(payload, dict) else []
    postings = [posting for posting in postings or [] if isinstance(posting, dict)]
    candidates_by_url: dict[str, Candidate] = {}

    for posting in postings:
        title = helpers.normalize_whitespace(helpers.join_text(posting.get("title"))) or "unknown"
        job = posting.get("job") if isinstance(posting.get("job"), dict) else {}
        department = _name(job.get("department"))
        division = _name(job.get("division"))
        location = _name(posting.get("location")) or "unknown"
        workplace = helpers.normalize_whitespace(helpers.join_text(posting.get("workplace_type_text")))
        employment_type = helpers.normalize_whitespace(helpers.join_text(posting.get("employment_type_text")))
        description = " ".join(
            helpers.visible_text_from_html(helpers.join_text(posting.get(field))) for field in DESCRIPTION_FIELDS
        ).strip()

        searchable_text = " ".join(
            part for part in [title, department, division, location, workplace, employment_type, description] if part
        )
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not matched_terms:
            continue

        url = helpers.normalize_whitespace(helpers.join_text(posting.get("url"))) or source.url
        note_parts = ["Enumerated through Pinpoint postings feed"]
        if division:
            note_parts.append(f"Division: {division}")
        if department:
            note_parts.append(f"Department: {department}")
        if workplace:
            note_parts.append(f"Workplace: {workplace}")
        if employment_type:
            note_parts.append(f"Type: {employment_type}")

        candidate = Candidate(
            employer=source.source,
            title=title,
            url=helpers.normalize_url_without_fragment(url),
            source_url=source.url,
            location=location,
            remote=helpers.infer_remote_status(location, workplace),
            matched_terms=matched_terms,
            notes="; ".join(note_parts),
        )
        helpers.set_candidate_description(candidate, description)
        helpers.merge_candidate(candidates_by_url, candidate)

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
        enumerated_jobs=len(postings),
        matched_jobs=len(candidates_by_url),
        limitations=[],
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("pinpoint_api",), discover=discover_pinpoint_api)
