"""service.bund.de provider.

Supported discovery modes:
- `service_bund_search`
- `service_bund_links`
"""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse

from discover import helpers, http
from discover.constants import NON_TECHNICAL_TITLE_HINTS
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


SERVICE_BUND_RESULT_RE = re.compile(
    r'<a[^>]+href="(?P<href>[^"]*IMPORTE/Stellenangebote[^"]*)"[^>]*>'
    r'.*?<h3>(?P<title>.*?)</h3>'
    r'.*?<p><em>Arbeitgeber</em>\s*(?P<employer>.*?)</p>'
    r'.*?<p><em>Veröffentlicht</em>\s*(?P<posted>[^<]+)</p>'
    r'.*?<p><em>Bewerbungsfrist</em>\s*(?P<deadline>[^<]+)</p>',
    flags=re.DOTALL | re.IGNORECASE,
)
SERVICE_BUND_NEXT_RE = re.compile(
    r'<li class="next"[^>]*>.*?<button[^>]+name="gtp"[^>]+value="(?P<gtp>[^"]+)"',
    flags=re.DOTALL | re.IGNORECASE,
)
SERVICE_BUND_DIRECT_LINK_RE = re.compile(
    r'<a[^>]+href="(?P<href>[^"]*service\.bund\.de/[^"]*IMPORTE/Stellenangebote[^"]*)"[^>]*>(?P<text>.*?)</a>',
    flags=re.DOTALL | re.IGNORECASE,
)
SERVICE_BUND_PUBLIC_INTEREST_HINTS = (
    "krypt",
    "it-sicherheit",
    "cyber",
    "cyber/it",
    "security",
    "attack surface",
    "biometr",
    "kritis",
    "digital",
    "informatik",
    "informationstechnik",
    "telekommunikation",
    "netz",
)


def should_keep_service_bund_candidate(
    title: str,
    matched_terms: list[str],
    searchable_text: str,
    *,
    allow_curated_without_term: bool = False,
) -> bool:
    if helpers.should_keep_candidate(title, matched_terms, searchable_text):
        return True
    if any(token in title.lower() for token in NON_TECHNICAL_TITLE_HINTS):
        return False
    haystack = helpers.normalize_for_matching(searchable_text)
    has_public_interest_tech_hint = any(token in haystack for token in SERVICE_BUND_PUBLIC_INTEREST_HINTS)
    normalized_terms = {helpers.normalize_for_matching(term) for term in matched_terms}
    if normalized_terms == {"referent"}:
        return has_public_interest_tech_hint
    if normalized_terms:
        return has_public_interest_tech_hint
    return allow_curated_without_term and has_public_interest_tech_hint


def build_service_bund_search_url(source_url: str, term: str, gtp: str | None = None) -> str:
    parsed = urlparse(source_url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params["templateQueryString"] = term
    params["resultsPerPage"] = "100"
    params["sortOrder"] = "dateOfIssue_dt desc"
    if gtp:
        params["gtp"] = gtp
    else:
        params.pop("gtp", None)
    query = urlencode(params)
    return parsed._replace(query=query, fragment="").geturl()


def discover_service_bund_search(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    candidates_by_url: dict[str, Candidate] = {}
    limitations: list[str] = []
    listing_pages_scanned = 0
    result_summaries: list[str] = []
    raw_seen_ids: set[str] = set()
    max_pages_per_term = 5

    for term in terms:
        page_num = 1
        gtp: str | None = None
        term_raw_count = 0

        while page_num <= max_pages_per_term:
            html = http.fetch_text(build_service_bund_search_url(source.url, term, gtp), timeout_seconds)
            listing_pages_scanned += 1

            page_matches = list(SERVICE_BUND_RESULT_RE.finditer(html))
            term_raw_count += len(page_matches)
            for match in page_matches:
                absolute_url = helpers.normalize_url_without_fragment(urljoin(source.url, unescape(match.group("href"))))
                raw_seen_ids.add(absolute_url)
                title = helpers.strip_html_fragment(match.group("title")) or "unknown"
                title = re.sub(r"^Stellenbezeichnung\s*", "", title, flags=re.IGNORECASE).strip() or "unknown"
                employer = helpers.strip_html_fragment(match.group("employer")) or source.source
                posted = helpers.normalize_whitespace(helpers.strip_html_fragment(match.group("posted")))
                deadline = helpers.normalize_whitespace(helpers.strip_html_fragment(match.group("deadline")))
                searchable_text = " ".join(part for part in [title, employer, posted, deadline, absolute_url, term] if part)
                matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
                if not should_keep_service_bund_candidate(title, matched_terms, searchable_text):
                    continue
                notes = "service.bund native search"
                if posted:
                    notes = f"{notes}; posted={posted}"
                if deadline:
                    notes = f"{notes}; deadline={deadline}"
                helpers.merge_candidate(
                    candidates_by_url,
                    Candidate(
                        employer=employer,
                        title=title,
                        url=absolute_url,
                        source_url=source.url,
                        matched_terms=matched_terms,
                        notes=notes,
                    ),
                )

            next_match = SERVICE_BUND_NEXT_RE.search(html)
            next_gtp = unescape(next_match.group("gtp")) if next_match else None
            if not next_gtp:
                break
            gtp = next_gtp
            page_num += 1

        if gtp and page_num > max_pages_per_term:
            limitations.append(f"service.bund query '{term}' hit the page cap ({max_pages_per_term}x100 results)")
        result_summaries.append(f"{term}:{page_num}p/{term_raw_count}")

    status = "partial" if limitations else "complete"
    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status=status,
        listing_pages_scanned=listing_pages_scanned,
        search_terms_tried=terms,
        result_pages_scanned=", ".join(result_summaries) if result_summaries else "none",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_seen_ids),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_service_bund_links(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = http.fetch_text(source.url, timeout_seconds)
    candidates_by_url: dict[str, Candidate] = {}
    raw_urls: set[str] = set()

    for match in SERVICE_BUND_DIRECT_LINK_RE.finditer(html):
        absolute_url = helpers.normalize_url_without_fragment(unescape(match.group("href")))
        raw_urls.add(absolute_url)
        title = helpers.strip_html_fragment(match.group("text")) or "unknown"
        searchable_text = " ".join(part for part in [title, source.source, absolute_url] if part)
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not should_keep_service_bund_candidate(
            title,
            matched_terms,
            searchable_text,
            allow_curated_without_term=True,
        ):
            continue
        helpers.merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=title,
                url=absolute_url,
                source_url=source.url,
                matched_terms=matched_terms,
                notes="Direct service.bund job links on source page",
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
        enumerated_jobs=len(raw_urls),
        matched_jobs=len(candidates_by_url),
        limitations=[],
        candidates=list(candidates_by_url.values()),
    )


SOURCES = [
    SourceAdapter(modes=("service_bund_search",), discover=discover_service_bund_search),
    SourceAdapter(modes=("service_bund_links",), discover=discover_service_bund_links),
]
