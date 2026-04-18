"""Personio page payload provider.

Supported discovery modes:
- `personio_page`

Expected source URL shape:
- `https://<subdomain>.jobs.personio.de/`
"""

from __future__ import annotations

import json
import re
from typing import Any

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


PERSONIO_NEXT_F_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,"(?P<chunk>.*?)"\]\)', flags=re.DOTALL)


def extract_personio_jobs_from_html(html: str) -> list[Any] | None:
    for match in PERSONIO_NEXT_F_CHUNK_RE.finditer(html):
        chunk = match.group("chunk")
        try:
            decoded = json.loads(f'"{chunk}"')
        except json.JSONDecodeError:
            continue
        jobs = helpers.extract_json_array_after_marker(decoded, '{"jobs":')
        if jobs is not None:
            return jobs
    return None


def discover_personio_page(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = http.fetch_text(source.url, timeout_seconds)
    jobs = extract_personio_jobs_from_html(html)
    if jobs is None:
        if "Derzeit keine offenen Positionen" in html or "No open positions" in html:
            jobs = []
        else:
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
                limitations=["Personio page did not expose a parseable jobs payload."],
                candidates=[],
            )

    candidates_by_url: dict[str, Candidate] = {}
    for job in jobs:
        title = helpers.normalize_whitespace(helpers.join_text(job.get("name") or job.get("title"))) or "unknown"
        location = helpers.normalize_whitespace(
            helpers.join_text(job.get("office") or job.get("location") or job.get("locations"))
        ) or "unknown"
        searchable_text = " ".join(
            part
            for part in [
                title,
                location,
                helpers.join_text(job.get("department")),
                helpers.join_text(job.get("employmentType") or job.get("employment_type")),
                helpers.join_text(job),
            ]
            if part
        )
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not helpers.should_keep_candidate(title, matched_terms, searchable_text):
            continue
        job_url = helpers.normalize_url_without_fragment(helpers.join_text(job.get("url") or job.get("absoluteUrl") or source.url))
        helpers.merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=title,
                url=job_url,
                source_url=source.url,
                location=location,
                remote=helpers.infer_remote_status(location, searchable_text),
                matched_terms=matched_terms,
                notes="Enumerated through Personio page payload",
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
        result_pages_scanned=f"jobs={len(jobs)}",
        direct_job_pages_opened=0,
        enumerated_jobs=len(jobs),
        matched_jobs=len(candidates_by_url),
        limitations=[],
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("personio_page",), discover=discover_personio_page)
