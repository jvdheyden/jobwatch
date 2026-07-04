"""Dover careers-page API provider.

Supported discovery modes:
- `dover_api`

Expected source URL shape:
- An app.dover.com careers page whose path contains the careers-page UUID,
  e.g. `https://app.dover.com/<company>/careers/<uuid>`.
"""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


DOVER_API_ROOT = "https://app.dover.com/api/v1/careers-page"
DOVER_DETAIL_ROOT = "https://app.dover.com/dover/careers"
DOVER_CAREERS_PATH_RE = re.compile(
    r"^/(?:[^/]+/)?careers/(?P<id>[0-9a-fA-F-]{36})/?$"
)


def _careers_id(url: str) -> str | None:
    path = urlparse(url).path or ""
    match = DOVER_CAREERS_PATH_RE.match(path)
    return match.group("id") if match else None


def _job_location(job: dict) -> str:
    parts: list[str] = []
    for entry in job.get("locations") or []:
        if not isinstance(entry, dict):
            continue
        name = unescape(str(entry.get("name") or "")).strip()
        if name:
            parts.append(name)
    return "; ".join(parts) or "unknown"


def discover_dover_jobs(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    careers_id = _careers_id(source.url)
    if not careers_id:
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
            limitations=[f"Could not extract Dover careers id from URL: {source.url}"],
            candidates=[],
        )

    jobs_endpoint = f"{DOVER_API_ROOT}/{careers_id}/jobs"
    payload = http.fetch_json(jobs_endpoint, timeout_seconds)
    jobs = payload.get("results", []) if isinstance(payload, dict) else []
    candidates_by_url: dict[str, Candidate] = {}

    for job in jobs:
        if not isinstance(job, dict):
            continue
        if not job.get("is_published"):
            continue
        if job.get("is_sample"):
            continue
        job_id = str(job.get("id") or "").strip()
        title = helpers.normalize_whitespace(unescape(str(job.get("title") or ""))) or "unknown"
        if not job_id:
            continue
        location = _job_location(job)
        searchable_text = f"{title} {location}"
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not helpers.should_keep_candidate(title, matched_terms, searchable_text):
            continue
        helpers.merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=title,
                url=f"{DOVER_DETAIL_ROOT}/{careers_id}/{job_id}",
                source_url=source.url,
                location=location,
                matched_terms=matched_terms,
                notes="Enumerated through Dover careers-page API",
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


SOURCE = SourceAdapter(modes=("dover_api",), discover=discover_dover_jobs)
