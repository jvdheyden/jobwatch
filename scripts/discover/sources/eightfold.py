"""Eightfold PCSx search provider.

Supported discovery modes:
- `eightfold_api`
- `infineon_api`

Expected source URL shape:
- `https://<host>/careers` pages exposing `/api/pcsx/search`.
"""

from __future__ import annotations

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


def eightfold_domain_for_source(source: SourceConfig) -> str:
    host = urlparse(source.url).netloc.lower()
    if host in EIGHTFOLD_DOMAINS_BY_HOST:
        return EIGHTFOLD_DOMAINS_BY_HOST[host]
    if host.startswith("jobs.") and len(host.split(".")) > 2:
        return host.removeprefix("jobs.")
    raise ValueError(f"Could not infer Eightfold domain for {source.url}")


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
                if not helpers.should_keep_candidate(title, matched_terms, searchable_text):
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


discover_infineon_api = discover_eightfold_api

SOURCE = SourceAdapter(modes=("eightfold_api", "infineon_api"), discover=discover_eightfold_api)
