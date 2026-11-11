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
    # An empty `data` list is a legitimate empty board; anything else without a
    # `data` list is an unexpected response and must not read as "no jobs".
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("Pinpoint postings feed did not contain a `data` list")
    postings = [posting for posting in payload["data"] if isinstance(posting, dict)]
    parsed_source = urlparse(source.url)
    candidates_by_url: dict[str, Candidate] = {}
    missing_url = 0

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

        url = helpers.normalize_whitespace(helpers.join_text(posting.get("url")))
        path = helpers.normalize_whitespace(helpers.join_text(posting.get("path")))
        if not url and path.startswith("/"):
            url = f"{parsed_source.scheme or 'https'}://{parsed_source.netloc}{path}"
        if not url:
            missing_url += 1
            continue
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

    limitations: list[str] = []
    if missing_url:
        limitations.append(f"{missing_url} matching Pinpoint posting(s) had no posting URL or path and were skipped.")

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
        direct_job_pages_opened=0,
        enumerated_jobs=len(postings),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("pinpoint_api",), discover=discover_pinpoint_api)
