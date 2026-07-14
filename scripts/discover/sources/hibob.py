"""HiBob (Bob) hosted careers-page provider.

Supported discovery modes:
- `hibob_api`

Expected source URL shape:
- `https://<company>.careers.hibob.com`

HiBob renders its public careers page client-side, so static HTML enumeration
surfaces no postings. The page hydrates from a single JSON endpoint,
`/api/job-ad`, which requires a `companyIdentifier` request header (the
careers subdomain) and returns every published posting in one response.
"""

from __future__ import annotations

from urllib.parse import urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


def hibob_company_identifier(source_url: str) -> str:
    host = urlparse(source_url).hostname or ""
    label = host.split(".")[0] if host else ""
    if not label:
        raise ValueError(f"Could not derive HiBob company identifier from {source_url}")
    return label


def _job_location(job: dict) -> str:
    parts = [str(job.get(field) or "").strip() for field in ("site", "country")]
    return ", ".join(part for part in parts if part) or "unknown"


def _job_description(job: dict) -> str:
    sections = [job.get("description"), job.get("responsibilities"), job.get("requirements")]
    return helpers.visible_text_from_html(" ".join(part for part in sections if part))


def discover_hibob_api(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    company_identifier = hibob_company_identifier(source.url)
    base = f"{urlparse(source.url).scheme}://{urlparse(source.url).hostname}"
    endpoint = f"{base}/api/job-ad"
    payload = http.fetch_json(endpoint, timeout_seconds, headers={"companyIdentifier": company_identifier})
    postings = payload.get("jobAdDetails", []) if isinstance(payload, dict) else []

    candidates_by_url: dict[str, Candidate] = {}
    for job in postings:
        if not isinstance(job, dict):
            continue
        job_id = str(job.get("id") or "").strip()
        if not job_id:
            continue
        title = job.get("title") or "unknown"
        location = _job_location(job)
        description = _job_description(job)
        searchable_text = " ".join(
            part
            for part in [title, job.get("department") or "", location, description]
            if part
        )
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not helpers.should_keep_candidate(title, matched_terms, searchable_text):
            continue
        candidate = Candidate(
            employer=source.source,
            title=title,
            url=f"{base}/jobs/{job_id}",
            source_url=source.url,
            location=location,
            remote=job.get("workspaceType") or "unknown",
            matched_terms=matched_terms,
            notes="Enumerated through HiBob careers job-ad API",
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


SOURCE = SourceAdapter(modes=("hibob_api",), discover=discover_hibob_api)
