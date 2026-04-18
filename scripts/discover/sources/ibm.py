"""IBM Careers search API provider."""

from __future__ import annotations

from typing import Any

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


IBM_SEARCH_API_URL = "https://www-api.ibm.com/search/api/v2"
IBM_RESULTS_PAGE_SIZE = 100
IBM_RESEARCH_GENERIC_MATCH_TERMS = frozenset({"research scientist", "postdoc", "postdoctoral"})


def build_ibm_title_query(terms: list[str]) -> str:
    query_terms: list[str] = []
    for term in terms:
        normalized = term.strip()
        if not normalized:
            continue
        escaped = normalized.replace("\\", "\\\\").replace('"', '\\"')
        if " " in normalized or "-" in normalized:
            query_terms.append(f'"{escaped}"')
        else:
            query_terms.append(escaped)
    if not query_terms:
        return ""
    return "title:(" + " OR ".join(query_terms) + ")"


def build_ibm_search_payload(offset: int, size: int, title_query: str | None = None) -> dict[str, Any]:
    must_clauses: list[dict[str, Any]] = []
    if title_query:
        must_clauses.append({"query_string": {"query": title_query}})
    return {
        "appId": "careers",
        "scopes": ["careers2"],
        "query": {"bool": {"must": must_clauses}},
        "aggs": {
            "field_keyword_172": {
                "filter": {"match_all": {}},
                "aggs": {
                    "field_keyword_17": {"terms": {"field": "field_keyword_17", "size": 6}},
                    "field_keyword_17_count": {"cardinality": {"field": "field_keyword_17"}},
                },
            },
            "field_keyword_083": {
                "filter": {"match_all": {}},
                "aggs": {
                    "field_keyword_08": {"terms": {"field": "field_keyword_08", "size": 6}},
                    "field_keyword_08_count": {"cardinality": {"field": "field_keyword_08"}},
                },
            },
            "field_keyword_184": {
                "filter": {"match_all": {}},
                "aggs": {
                    "field_keyword_18": {"terms": {"field": "field_keyword_18", "size": 6}},
                    "field_keyword_18_count": {"cardinality": {"field": "field_keyword_18"}},
                },
            },
            "field_keyword_055": {
                "filter": {"match_all": {}},
                "aggs": {
                    "field_keyword_05": {"terms": {"field": "field_keyword_05", "size": 1000}},
                    "field_keyword_05_count": {"cardinality": {"field": "field_keyword_05"}},
                },
            },
        },
        "size": size,
        "from": offset,
        "sort": [{"_score": "desc"}, {"pageviews": "desc"}],
        "lang": "zz",
        "localeSelector": {},
        "sm": {"query": "", "lang": "zz"},
        "_source": [
            "_id",
            "title",
            "url",
            "description",
            "language",
            "entitled",
            "field_keyword_17",
            "field_keyword_08",
            "field_keyword_18",
            "field_keyword_19",
        ],
    }


def should_keep_ibm_candidate(source: SourceConfig, title: str, matched_terms: list[str]) -> bool:
    if source.source != "IBM Research":
        return True

    title_lower = title.lower()
    if "postdoctoral" in title_lower or "postdoc" in title_lower:
        return True
    if "research scientist" not in title_lower:
        return False

    normalized_matches = {helpers.normalize_for_matching(term) for term in matched_terms}
    return any(term not in IBM_RESEARCH_GENERIC_MATCH_TERMS for term in normalized_matches)


def discover_ibm_api(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    candidates_by_url: dict[str, Candidate] = {}
    raw_seen_ids: set[str] = set()
    pages_scanned = 0
    total_hits = 0
    offset = 0
    title_query = build_ibm_title_query(terms)

    while True:
        payload = build_ibm_search_payload(offset, IBM_RESULTS_PAGE_SIZE, title_query=title_query)
        response = http.post_json(
            IBM_SEARCH_API_URL,
            payload,
            timeout_seconds,
            headers={"Referer": "https://www.ibm.com/"},
        )
        hits = response.get("hits", {})
        total = hits.get("total", {})
        total_hits = int(total.get("value", total_hits or 0) or 0)
        page_hits = hits.get("hits", [])
        if not page_hits:
            break

        pages_scanned += 1
        for hit in page_hits:
            source_payload = hit.get("_source", {})
            job_id = hit.get("_id") or source_payload.get("url") or ""
            if job_id:
                raw_seen_ids.add(job_id)
            title = source_payload.get("title") or "unknown"
            url = source_payload.get("url") or source.url
            description = helpers.strip_html_fragment(source_payload.get("description", ""))
            location = source_payload.get("field_keyword_19") or "unknown"
            remote = source_payload.get("field_keyword_17") or "unknown"
            team = source_payload.get("field_keyword_08") or ""
            level = source_payload.get("field_keyword_18") or ""
            searchable_text = " ".join(part for part in [title, description, location, remote, team, level] if part)
            matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
            if not helpers.should_keep_candidate(title, matched_terms, searchable_text):
                continue
            if not should_keep_ibm_candidate(source, title, matched_terms):
                continue
            note_parts = ["Enumerated through IBM careers search API with title-scoped server-side filtering"]
            if description:
                note_parts.append(f"Summary: {helpers.truncate_text(description, 220)}")
            helpers.merge_candidate(
                candidates_by_url,
                Candidate(
                    employer=source.source,
                    title=title,
                    url=url,
                    source_url=source.url,
                    location=location,
                    remote=remote,
                    matched_terms=matched_terms,
                    notes="; ".join(note_parts),
                ),
            )

        offset += len(page_hits)
        if len(page_hits) < IBM_RESULTS_PAGE_SIZE:
            break
        if total_hits and offset >= total_hits:
            break

    limitations: list[str] = []
    status = "complete"
    unique_hits = len(raw_seen_ids)
    if total_hits and unique_hits < total_hits:
        status = "partial"
        limitations.append(
            f"IBM API reported {total_hits} hits but only {unique_hits} unique records were observed across paged results"
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
        result_pages_scanned=f"full_index={pages_scanned}p/{unique_hits or total_hits}of{total_hits or unique_hits}",
        direct_job_pages_opened=0,
        enumerated_jobs=unique_hits or total_hits,
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("ibm_api",), discover=discover_ibm_api)
