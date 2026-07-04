"""Spotify Life at Spotify jobs API provider.

Supported discovery modes:
- `lifeatspotify_api`

Expected source URL shape:
- A lifeatspotify.com jobs page; enumeration goes through the public
  api.lifeatspotify.com WP JSON endpoints.
"""

from __future__ import annotations

from html import unescape

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


LIFEATSPOTIFY_API_ROOT = "https://api.lifeatspotify.com/wp-json/animal/v1"
LIFEATSPOTIFY_DETAIL_ROOT = "https://www.lifeatspotify.com/jobs"


def _searchable_text(job: dict) -> str:
    title = unescape(str(job.get("text") or ""))
    main_cat = (job.get("main_category") or {}).get("name") or ""
    sub_cat = (job.get("sub_category") or {}).get("name") or ""
    job_type = (job.get("job_type") or {}).get("name") or ""
    locations = "; ".join(
        str(entry.get("location") or "")
        for entry in (job.get("locations") or [])
        if isinstance(entry, dict)
    )
    return " ".join(part for part in [title, main_cat, sub_cat, job_type, locations] if part)


def _detail_notes(detail: dict) -> str:
    note_parts = ["Enumerated through lifeatspotify.com jobs API"]
    content = detail.get("content") if isinstance(detail, dict) else None
    if not isinstance(content, dict):
        return "; ".join(note_parts)
    description_html = content.get("descriptionHtml") or ""
    if description_html:
        description_text = " ".join(helpers.extract_visible_text_lines_from_html(description_html))
        if description_text:
            note_parts.append(f"Description: {helpers.truncate_text(description_text, 260)}")
    for section in content.get("lists") or []:
        if not isinstance(section, dict):
            continue
        heading = unescape(str(section.get("text") or "")).strip()
        body_text = " ".join(helpers.extract_visible_text_lines_from_html(section.get("content") or ""))
        if heading and body_text:
            note_parts.append(f"{heading}: {helpers.truncate_text(body_text, 260)}")
    return "; ".join(note_parts)


def _job_location(job: dict) -> str:
    locations = [
        unescape(str(entry.get("location") or ""))
        for entry in (job.get("locations") or [])
        if isinstance(entry, dict) and entry.get("location")
    ]
    return "; ".join(locations) or "unknown"


def discover_lifeatspotify_jobs(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    search_endpoint = f"{LIFEATSPOTIFY_API_ROOT}/job/search"
    payload = http.fetch_json(search_endpoint, timeout_seconds)
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
        title = helpers.normalize_whitespace(unescape(str(job.get("text") or ""))) or "unknown"
        searchable_text = _searchable_text(job)
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not helpers.should_keep_candidate(title, matched_terms, searchable_text):
            continue
        detail_notes = "Enumerated through lifeatspotify.com jobs API"
        try:
            detail_payload = http.fetch_json(
                f"{LIFEATSPOTIFY_API_ROOT}/job/single/{job_id}", timeout_seconds
            )
            direct_job_pages_opened += 1
        except Exception as exc:
            limitations.append(f"Could not fetch detail for {job_id}: {type(exc).__name__}: {exc}")
            detail_payload = None
        if isinstance(detail_payload, dict):
            detail_notes = _detail_notes(detail_payload.get("data") or {})
        helpers.merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=title,
                url=f"{LIFEATSPOTIFY_DETAIL_ROOT}/{job_id}",
                source_url=source.url,
                location=_job_location(job),
                matched_terms=matched_terms,
                notes=detail_notes,
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
        direct_job_pages_opened=direct_job_pages_opened,
        enumerated_jobs=len(jobs),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("lifeatspotify_api",), discover=discover_lifeatspotify_jobs)
