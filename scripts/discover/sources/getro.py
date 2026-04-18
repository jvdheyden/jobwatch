"""Getro collection search provider.

Supported discovery modes:
- `getro_api`

Expected source URL shape:
- Getro collection pages exposing `__NEXT_DATA__` with a network id.
"""

from __future__ import annotations

import json
import re
from html import unescape

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


NEXT_DATA_SCRIPT_RE = re.compile(
    r'<script[^>]+id="__NEXT_DATA__"[^>]*>(?P<payload>.*?)</script>',
    flags=re.DOTALL | re.IGNORECASE,
)
GETRO_RESULTS_PAGE_SIZE = 100
MAX_GETRO_PAGES = 50


def extract_next_data_payload(html: str) -> dict[str, object] | None:
    match = NEXT_DATA_SCRIPT_RE.search(html)
    if not match:
        return None
    try:
        return json.loads(unescape(match.group("payload")))
    except json.JSONDecodeError:
        return None


def discover_getro_api(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = http.fetch_text(source.url, timeout_seconds)
    next_data = extract_next_data_payload(html)
    if not next_data:
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
            limitations=["Getro jobs page did not expose a __NEXT_DATA__ payload."],
            candidates=[],
        )

    page_props = next_data.get("props", {}).get("pageProps", {})
    collection_id = helpers.normalize_whitespace(helpers.join_text(page_props.get("network", {}).get("id")))
    if not collection_id:
        collection_id = helpers.normalize_whitespace(helpers.join_text(page_props.get("initialState", {}).get("network", {}).get("id")))
    if not collection_id:
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
            limitations=["Getro jobs page exposed __NEXT_DATA__ but no collection id."],
            candidates=[],
        )

    endpoint = f"https://api.getro.com/api/v2/collections/{collection_id}/search/jobs"
    candidates_by_url: dict[str, Candidate] = {}
    raw_seen_ids: set[str] = set()
    page_signatures: set[str] = set()
    reported_total = 0
    limitations: list[str] = []
    pages_scanned = 0
    status = "complete"
    reached_end = False
    observed_page_size = 0

    for page_num in range(MAX_GETRO_PAGES):
        response = http.post_json(
            endpoint,
            {"hitsPerPage": GETRO_RESULTS_PAGE_SIZE, "page": page_num, "filters": "", "query": ""},
            timeout_seconds,
            headers={"Referer": source.url},
        )
        results = response.get("results", {}) if isinstance(response, dict) else {}
        jobs = results.get("jobs") or []
        reported_total = max(reported_total, int(results.get("count", reported_total or 0) or 0))
        if not jobs:
            reached_end = True
            break
        if not observed_page_size:
            observed_page_size = len(jobs)

        page_signature = ",".join(str(job.get("id") or job.get("slug") or job.get("url") or "") for job in jobs[:10])
        if page_signature and page_signature in page_signatures:
            status = "partial"
            limitations.append("Getro collection search repeated a page before exhausting the listing.")
            break
        if page_signature:
            page_signatures.add(page_signature)

        pages_scanned += 1
        for job in jobs:
            raw_id = str(job.get("id") or job.get("slug") or job.get("url") or f"{page_num}:{len(raw_seen_ids)}")
            raw_seen_ids.add(raw_id)
            title = helpers.normalize_whitespace(helpers.join_text(job.get("title"))) or "unknown"
            employer = helpers.normalize_whitespace(helpers.join_text(job.get("organization", {}).get("name"))) or source.source
            location_parts = [helpers.normalize_whitespace(helpers.join_text(item)) for item in (job.get("locations") or [])]
            location = "; ".join(part for part in location_parts if part) or "unknown"
            work_mode = helpers.normalize_whitespace(helpers.join_text(job.get("workMode") or job.get("work_mode")))
            seniority = helpers.normalize_whitespace(helpers.join_text(job.get("seniority")))
            topics = [helpers.normalize_whitespace(helpers.join_text(item)) for item in (job.get("organization", {}).get("topics") or [])]
            topics = [item for item in topics if item]
            industry_tags = [
                helpers.normalize_whitespace(helpers.join_text(item)) for item in (job.get("organization", {}).get("industryTags") or [])
            ]
            industry_tags = [item for item in industry_tags if item]
            job_url = helpers.normalize_url_without_fragment(helpers.join_text(job.get("url")) or source.url)
            searchable_text = " ".join(
                part
                for part in [
                    title,
                    employer,
                    location,
                    work_mode,
                    seniority,
                    helpers.join_text(job.get("skills")),
                    helpers.join_text(job.get("organization", {}).get("topics")),
                    helpers.join_text(job.get("organization", {}).get("industryTags")),
                ]
                if part
            )
            matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
            if not helpers.should_keep_candidate(title, matched_terms, searchable_text):
                continue

            note_parts = ["Enumerated through Getro collection search API"]
            if work_mode:
                note_parts.append(f"Work mode: {work_mode}")
            if seniority:
                note_parts.append(f"Seniority: {seniority}")
            if topics:
                note_parts.append(f"Topics: {', '.join(topics)}")
            if industry_tags:
                note_parts.append(f"Industries: {', '.join(industry_tags)}")

            helpers.merge_candidate(
                candidates_by_url,
                Candidate(
                    employer=employer,
                    title=title,
                    url=job_url,
                    source_url=source.url,
                    location=location,
                    remote=helpers.infer_remote_status(location, work_mode, title),
                    matched_terms=matched_terms,
                    notes="; ".join(note_parts),
                ),
            )

        if reported_total and len(raw_seen_ids) >= reported_total:
            reached_end = True
            break
        if observed_page_size and len(jobs) < observed_page_size:
            reached_end = True
            break

    if not reached_end and status == "complete":
        status = "partial"
        limitations.append(f"Getro collection search hit the page cap ({MAX_GETRO_PAGES}).")

    deduped_limitations = list(dict.fromkeys(limitations))
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
        result_pages_scanned=f"collection={pages_scanned}p/{len(raw_seen_ids)}of{reported_total or len(raw_seen_ids)}",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_seen_ids),
        matched_jobs=len(candidates_by_url),
        limitations=deduped_limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("getro_api",), discover=discover_getro_api)
