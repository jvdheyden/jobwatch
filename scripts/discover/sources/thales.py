"""Thales search-results HTML provider."""

from __future__ import annotations

import re
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
                if not helpers.should_keep_candidate(title, matched_terms, searchable_text):
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
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_seen_ids),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("thales_html",), discover=discover_thales_html)
