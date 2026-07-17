"""Generic and filtered static HTML discovery providers."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter

KNDS_SEARCH_API_URL = "https://production.api.recruiting-solutions.org/search"
KNDS_SEARCH_API_HEADERS = {
    "customerId": "knds-prod",
    "x-api-key": "pk_knds-prod_vQoHZUfidPgNIsDClPNzfoBaJvKnKpXCNtxVmSctXTwKEYCbjNuFAnAKcVoJpdpjEpuLDuxCTazaJMEODATzaVvrzWwaZNnb",
    "internal": "false",
    "privateJobBoard": "false",
}
KNDS_SEARCH_FIELDS = "jobId,title,profile,tasks"
KNDS_TERM_ALIASES: dict[str, tuple[str, ...]] = {
    "it security": ("IT-Security",),
    "it-sicherheit": ("IT Sicherheit", "Informationssicherheit"),
}


def is_same_page_link(source_url: str, candidate_url: str) -> bool:
    return helpers.normalize_url_without_fragment(source_url) == helpers.normalize_url_without_fragment(candidate_url)


def looks_like_non_job_link(text: str, href: str) -> bool:
    text_lower = helpers.normalize_whitespace(text).lower()
    href_lower = href.lower()
    if text_lower in {
        "",
        "skip to content",
        "jump to main content.",
        "top of this page",
        "top of page",
        "privacy",
        "privacy policy",
        "impressum",
        "report this content",
        "collapse this bar",
        "customize",
        "accept all",
        "accept selection",
        "decline non-essential cookies",
        "subscribe",
        "subscribed",
    }:
        return True
    return any(
        marker in href_lower
        for marker in (
            "/privacy",
            "/cookie",
            "/impressum",
            "/learn/",
            "/resources/",
            "/resource/",
            "/services/",
            "/abuse/",
        )
    )


def collect_job_links(html: str, base_url: str, path_fragment: str) -> dict[str, str]:
    parser = helpers.LinkCollector()
    parser.feed(html)
    links: dict[str, str] = {}
    for link in parser.links:
        absolute_url = urljoin(base_url, link["href"])
        if path_fragment not in absolute_url:
            continue
        links[absolute_url] = link["text"]
    return links


def is_bwi_job_detail_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc.lower() in {"bwi.de", "www.bwi.de"} and parsed.path.startswith(
        "/karriere/stellenangebote/job/"
    )


def extract_bwi_job_detail(html: str) -> str:
    text = helpers.strip_html_fragment(html)
    marker = re.search(r"\bStellen-ID:\s*\d+\b", text, flags=re.IGNORECASE)
    if not marker:
        return ""
    return helpers.normalize_whitespace(text[marker.start() :])


def extract_bwi_title(detail: str, fallback: str) -> str:
    match = re.match(
        r"Stellen-ID:\s*\d+\s+(.+?)\s+(?:ab sofort\b|Stellenbeschreibung\b)",
        detail,
        flags=re.IGNORECASE,
    )
    return helpers.normalize_whitespace(match.group(1) if match else fallback) or "unknown"


def extract_bwi_location(detail: str, title: str) -> str:
    heading = detail.split("Stellenbeschreibung", 1)[0]
    nationwide = re.search(
        r"\b(bundesweit\s+an\s+einem\s+unserer\s+BWI\s+Standorte)\b",
        heading,
        flags=re.IGNORECASE,
    )
    if nationwide:
        return helpers.normalize_whitespace(nationwide.group(1))
    location_marker = heading.lower().rfind(" in ")
    if location_marker >= 0:
        return helpers.normalize_whitespace(heading[location_marker + 4 :].rstrip(". "))
    title_location = re.search(r"\(m/w/d\)\s+in\s+(.+)$", title, flags=re.IGNORECASE)
    return helpers.normalize_whitespace(title_location.group(1)) if title_location else "unknown"


def discover_bwi_jobboard(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    listing_html = http.fetch_text(source.url, timeout_seconds)
    parser = helpers.LinkCollector()
    parser.feed(listing_html)
    links: dict[str, str] = {}
    for link in parser.links:
        absolute_url = helpers.normalize_url_without_fragment(urljoin(source.url, link["href"]))
        if is_bwi_job_detail_url(absolute_url):
            links.setdefault(absolute_url, helpers.normalize_whitespace(link["text"]))

    candidates: list[Candidate] = []
    limitations: list[str] = []
    opened_pages = 0
    for url, link_text in links.items():
        try:
            detail_html = http.fetch_text(url, timeout_seconds)
        except Exception as exc:
            limitations.append(f"BWI job detail fetch failed for {url}: {exc}")
            continue
        opened_pages += 1
        detail = extract_bwi_job_detail(detail_html)
        if not detail:
            limitations.append(f"BWI job detail marker was missing for {url}")
            continue
        title = extract_bwi_title(detail, link_text)
        searchable_text = f"{title} {detail}"
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not matched_terms or not helpers.should_keep_candidate(title, matched_terms, searchable_text):
            continue
        candidate = Candidate(
            employer=source.source,
            title=title,
            url=url,
            source_url=source.url,
            location=extract_bwi_location(detail, title),
            matched_terms=matched_terms,
            notes=f"BWI vacancy detail: {detail}",
        )
        helpers.set_candidate_description(candidate, detail)
        candidates.append(candidate)

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
        result_pages_scanned=f"bwi_job_details={opened_pages}",
        direct_job_pages_opened=opened_pages,
        enumerated_jobs=len(links),
        matched_jobs=len(candidates),
        limitations=limitations,
        candidates=candidates,
    )


def discover_html(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    if urlparse(source.url).netloc.lower() in {"bwi.de", "www.bwi.de"}:
        return discover_bwi_jobboard(source, terms, timeout_seconds)
    html = http.fetch_text(source.url, timeout_seconds)
    parser = helpers.LinkCollector()
    parser.feed(html)
    candidates: list[Candidate] = []
    seen_urls: set[str] = set()
    for link in parser.links:
        href = link["href"]
        text = helpers.normalize_whitespace(link["text"])
        if href.startswith("#"):
            continue
        absolute_url = helpers.normalize_url_without_fragment(urljoin(source.url, href))
        if absolute_url in seen_urls:
            continue
        if urlparse(absolute_url).scheme not in {"file", "http", "https"}:
            continue
        if looks_like_non_job_link(text, absolute_url):
            continue
        if is_same_page_link(source.url, absolute_url):
            continue
        matched_terms = helpers.match_terms(f"{text} {absolute_url}", terms)
        if not matched_terms and not helpers.looks_like_job_link(text, absolute_url):
            continue
        if matched_terms and not helpers.should_keep_candidate(text or "unknown", matched_terms, f"{text} {absolute_url}"):
            continue
        seen_urls.add(absolute_url)
        candidates.append(
            Candidate(
                employer=source.source,
                title=text or "unknown",
                url=absolute_url,
                source_url=source.url,
                matched_terms=matched_terms,
                notes="Static HTML enumeration",
            )
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
        enumerated_jobs=len(parser.links),
        matched_jobs=len(candidates),
        limitations=[],
        candidates=candidates,
    )


def discover_filtered_html_links(
    source: SourceConfig,
    terms: list[str],
    timeout_seconds: int,
    url_filter: Callable[[str], bool],
    notes: str,
    limitation_if_empty: str | None = None,
) -> Coverage:
    html = http.fetch_text(source.url, timeout_seconds)
    parser = helpers.LinkCollector()
    parser.feed(html)
    raw_urls: set[str] = set()
    candidates_by_url: dict[str, Candidate] = {}

    for link in parser.links:
        absolute_url = helpers.normalize_url_without_fragment(urljoin(source.url, link["href"]))
        if urlparse(absolute_url).scheme not in {"http", "https"}:
            continue
        if not url_filter(absolute_url):
            continue
        raw_urls.add(absolute_url)
        text = helpers.normalize_whitespace(link["text"]) or "unknown"
        visible_lines = helpers.split_visible_lines(link["text"])
        title = visible_lines[0] if visible_lines else text
        searchable_text = f"{title} {text} {absolute_url}"
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not helpers.should_keep_candidate(title, matched_terms, searchable_text):
            continue
        helpers.merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=title,
                url=absolute_url,
                source_url=source.url,
                matched_terms=matched_terms,
                notes=notes,
            ),
        )

    limitations = [limitation_if_empty] if not raw_urls and limitation_if_empty else []
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
        result_pages_scanned="filtered_links=1",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_urls),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_cybernetica_teamdash(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    return discover_filtered_html_links(
        source,
        terms,
        timeout_seconds,
        lambda url: "cyber.teamdash.com/p/job/" in url,
        notes="Enumerated through Teamdash links on the Cybernetica careers page",
        limitation_if_empty="No Teamdash job links were visible on the Cybernetica careers page.",
    )


def discover_secunet_jobboard(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    pattern = re.compile(r"^https://jobs\.secunet\.com/.+-j\d+\.html$")
    return discover_filtered_html_links(
        source,
        terms,
        timeout_seconds,
        lambda url: bool(pattern.match(url)),
        notes="Enumerated through direct secunet job-detail links",
        limitation_if_empty="No secunet job-detail links matching the standard job pattern were visible.",
    )


def is_knds_job_detail_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc == "jobs.knds.de" and (
        parsed.path.startswith("/job/") or parsed.path.startswith("/job-invite/")
    )


def is_knds_listing_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc == "jobs.knds.de" and parsed.path.startswith("/viewalljobs/")


def knds_title_from_url(url: str) -> str:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[0] != "job":
        return "unknown"
    title_part = unquote(parts[1])
    return helpers.normalize_whitespace(re.sub(r"[-_]+", " ", title_part)) or "unknown"


def knds_search_term_variants(terms: list[str]) -> list[str]:
    variants: list[str] = []
    for term in terms:
        for variant in (term, *KNDS_TERM_ALIASES.get(term.lower(), ())):
            if variant not in variants:
                variants.append(variant)
    return variants


def knds_api_search_payload(term: str) -> dict[str, Any]:
    return {
        "count": True,
        "facets": [],
        "filter": "",
        "search": f"/.*{term}.*/",
        "queryType": "full",
        "searchFields": KNDS_SEARCH_FIELDS,
        "skip": 0,
        "top": 50,
    }


def knds_job_location(job: dict[str, Any]) -> str:
    addresses = job.get("addresses")
    if not isinstance(addresses, list):
        return "unknown"
    locations: list[str] = []
    for address in addresses:
        if not isinstance(address, dict):
            continue
        location = helpers.normalize_whitespace(str(address.get("city") or address.get("name") or ""))
        if location and location not in locations:
            locations.append(location)
    return "; ".join(locations) if locations else "unknown"


def knds_job_searchable_text(job: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("title", "externalTitle", "profile", "tasks"):
        value = job.get(key)
        if isinstance(value, str):
            parts.append(helpers.strip_html_fragment(value))
    category = job.get("category")
    if isinstance(category, list):
        parts.extend(str(value) for value in category)
    elif isinstance(category, str):
        parts.append(category)
    return " ".join(parts)


def knds_compact_detail(value: Any, max_length: int = 320) -> str:
    if not isinstance(value, str):
        return ""
    detail = helpers.strip_html_fragment(value)
    if len(detail) <= max_length:
        return detail
    return detail[:max_length].rsplit(" ", 1)[0] + "..."


def knds_role_detail_notes(job: dict[str, Any]) -> str:
    profile = knds_compact_detail(job.get("profile"))
    tasks = knds_compact_detail(job.get("tasks"))
    detail_parts = []
    if profile:
        detail_parts.append(f"Profile: {profile}")
    if tasks:
        detail_parts.append(f"Tasks: {tasks}")
    return "; ".join(detail_parts)


def merge_knds_candidate(
    candidates_by_url: dict[str, Candidate],
    source: SourceConfig,
    title: str,
    url: str,
    terms: list[str],
    searchable_extra: str,
    notes: str,
) -> bool:
    searchable_text = f"{title} {searchable_extra} {url}"
    matched_terms = sorted(set(helpers.match_terms_with_aliases(searchable_text, terms, KNDS_TERM_ALIASES)))
    if not matched_terms:
        return False
    helpers.merge_candidate(
        candidates_by_url,
        Candidate(
            employer=source.source,
            title=title,
            url=url,
            source_url=source.url,
            matched_terms=matched_terms,
            notes=notes,
        ),
    )
    return True


def merge_knds_api_candidate(
    candidates_by_url: dict[str, Candidate],
    source: SourceConfig,
    job: dict[str, Any],
    terms: list[str],
) -> bool:
    title = helpers.normalize_whitespace(str(job.get("title") or job.get("externalTitle") or "unknown"))
    link = helpers.normalize_whitespace(str(job.get("link") or ""))
    if not link and job.get("jobId"):
        link = f"https://jobs.knds.de/job-invite/{job.get('jobId')}/?locale=de_DE"
    absolute_url = helpers.normalize_url_without_fragment(urljoin(source.url, link))
    if not is_knds_job_detail_url(absolute_url):
        return False
    searchable_text = knds_job_searchable_text(job)
    matched_terms = sorted(set(helpers.match_terms_with_aliases(searchable_text, terms, KNDS_TERM_ALIASES)))
    if not matched_terms:
        return False
    helpers.merge_candidate(
        candidates_by_url,
        Candidate(
            employer=source.source,
            title=title,
            url=absolute_url,
            source_url=source.url,
            location=knds_job_location(job),
            matched_terms=matched_terms,
            notes="; ".join(
                part
                for part in [
                    "Enumerated through KNDS Recruiting Solutions search API",
                    knds_role_detail_notes(job),
                ]
                if part
            ),
        ),
    )
    return True


def discover_knds_jobboard(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    first_html = http.fetch_text(source.url, timeout_seconds)
    parser = helpers.LinkCollector()
    parser.feed(first_html)
    pages_by_url: dict[str, str] = {source.url: first_html}
    listing_urls: list[str] = []
    for link in parser.links:
        absolute_url = helpers.normalize_url_without_fragment(urljoin(source.url, link["href"]))
        if absolute_url == source.url:
            continue
        if is_knds_listing_url(absolute_url) and absolute_url not in pages_by_url and absolute_url not in listing_urls:
            listing_urls.append(absolute_url)

    limitations: list[str] = []
    for listing_url in listing_urls[:1]:
        try:
            pages_by_url[listing_url] = http.fetch_text(listing_url, timeout_seconds)
        except Exception as exc:
            limitations.append(f"KNDS listing page fetch failed for {listing_url}: {exc}")

    api_queries_scanned = 0
    raw_urls: set[str] = set()
    candidates_by_url: dict[str, Candidate] = {}
    for page_url, html in pages_by_url.items():
        page_parser = helpers.LinkCollector()
        page_parser.feed(html)
        for link in page_parser.links:
            absolute_url = helpers.normalize_url_without_fragment(urljoin(page_url, link["href"]))
            if not is_knds_job_detail_url(absolute_url):
                continue
            raw_urls.add(absolute_url)
            text = helpers.normalize_whitespace(link["text"])
            title = text or knds_title_from_url(absolute_url)
            merge_knds_candidate(
                candidates_by_url,
                source,
                title,
                absolute_url,
                terms,
                "",
                "Enumerated through KNDS job-detail links",
            )

    static_job_links = len(raw_urls)
    if not candidates_by_url:
        for term in knds_search_term_variants(terms):
            api_queries_scanned += 1
            try:
                payload = knds_api_search_payload(term)
                response = http.post_json(KNDS_SEARCH_API_URL, payload, timeout_seconds, headers=KNDS_SEARCH_API_HEADERS)
            except Exception as exc:
                limitations.append(f"KNDS API search failed for {term}: {exc}")
                continue

            for job in response.get("value", []) if isinstance(response, dict) else []:
                if not isinstance(job, dict):
                    continue
                link = helpers.normalize_whitespace(str(job.get("link") or ""))
                if link:
                    absolute_url = helpers.normalize_url_without_fragment(urljoin(source.url, link))
                elif job.get("jobId"):
                    absolute_url = f"https://jobs.knds.de/job-invite/{job.get('jobId')}?locale=de_DE"
                else:
                    absolute_url = ""
                if is_knds_job_detail_url(absolute_url):
                    raw_urls.add(absolute_url)
                merge_knds_api_candidate(candidates_by_url, source, job, terms)

    if not raw_urls:
        limitations.append("No KNDS job-detail links were visible in static pages or API search results.")
    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="complete",
        listing_pages_scanned=len(pages_by_url),
        search_terms_tried=terms,
        result_pages_scanned=(
            f"knds_static_pages={len(pages_by_url)}; "
            f"knds_static_job_links={static_job_links}; "
            f"knds_api_queries={api_queries_scanned}"
        ),
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_urls),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCES = [
    SourceAdapter(modes=("html", "icims_html"), discover=discover_html),
    SourceAdapter(modes=("cybernetica_teamdash",), discover=discover_cybernetica_teamdash),
    SourceAdapter(modes=("knds_jobboard",), discover=discover_knds_jobboard),
    SourceAdapter(modes=("secunet_jobboard",), discover=discover_secunet_jobboard),
]
