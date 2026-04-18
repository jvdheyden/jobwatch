"""Public-service deterministic source providers."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from html import unescape
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter
from discover.sources.service_bund import should_keep_service_bund_candidate


VERFASSUNGSSCHUTZ_RSS_URL = "https://www.verfassungsschutz.de/SiteGlobals/Functions/RSSNewsFeed/Stellenangebote.xml"
AUSWAERTIGES_AMT_ACTION_RE = re.compile(
    r'(?:action|dataUrl)="(?P<endpoint>/ajax/json-filterlist/[^"]+)"',
    flags=re.IGNORECASE,
)
BND_RESULT_RE = re.compile(
    r'<a[^>]+href="(?P<href>[^"]*SharedDocs/Stellenangebote/DE/Stellenangebote/[^"]*)"[^>]*class="c-career-item__link"[^>]*>'
    r'\s*<strong[^>]*class="c-career-item__title"[^>]*>(?P<title>.*?)</strong>'
    r"(?P<bubbles>.*?)</a>",
    flags=re.DOTALL | re.IGNORECASE,
)
BND_BUBBLE_RE = re.compile(r'<span[^>]*class="c-bubble"[^>]*>(?P<text>.*?)</span>', flags=re.DOTALL | re.IGNORECASE)


def extract_verfassungsschutz_value(html: str, label: str) -> str:
    patterns = [
        rf'<strong[^>]*class="label"[^>]*>\s*{re.escape(label)}\s*</strong>\s*<span[^>]*class="value"[^>]*>(?P<value>.*?)</span>',
        rf'<span[^>]*class="label"[^>]*>\s*{re.escape(label)}\s*</span>\s*<span[^>]*class="value"[^>]*>(?P<value>.*?)</span>',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if match:
            return helpers.strip_html_fragment(match.group("value"))
    return ""


def extract_verfassungsschutz_section(html: str, *headings: str) -> str:
    for heading in headings:
        pattern = rf'<h2[^>]*>\s*{re.escape(heading)}\s*</h2>\s*(?P<body>.*?)(?=<h2[^>]*>|</main>)'
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if match:
            return helpers.strip_html_fragment(match.group("body"))
    return ""


def fetch_verfassungsschutz_job_details(url: str, timeout_seconds: int) -> dict[str, str]:
    html = http.fetch_text(url, timeout_seconds)

    description = ""
    meta_match = re.search(
        r'<meta[^>]+name="description"[^>]+content="(?P<value>[^"]+)"',
        html,
        re.IGNORECASE,
    )
    if meta_match:
        description = helpers.strip_html_fragment(meta_match.group("value"))

    apply_match = re.search(
        r'<a[^>]+href="(?P<href>[^"]+)"[^>]*class="application-link"',
        html,
        re.IGNORECASE,
    )
    apply_url = ""
    if apply_match:
        apply_url = helpers.normalize_url_without_fragment(urljoin(url, apply_match.group("href")))

    return {
        "description": description,
        "deadline": extract_verfassungsschutz_value(html, "Bewerbungsfrist"),
        "career_track": extract_verfassungsschutz_value(html, "Laufbahn"),
        "working_time": extract_verfassungsschutz_value(html, "Arbeitszeit"),
        "location": extract_verfassungsschutz_value(html, "Arbeitsort"),
        "tasks": extract_verfassungsschutz_section(html, "Ihre Aufgaben", "Aufgaben"),
        "offer": extract_verfassungsschutz_section(html, "Wir bieten"),
        "profile": extract_verfassungsschutz_section(html, "Ihr Profil", "Anforderungen"),
        "apply_url": apply_url,
    }


def discover_verfassungsschutz_rss(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    xml_text = http.fetch_text(VERFASSUNGSSCHUTZ_RSS_URL, timeout_seconds)
    root = ET.fromstring(xml_text)
    items = root.findall("./channel/item")
    candidates_by_url: dict[str, Candidate] = {}
    direct_job_pages_opened = 0
    detail_fetch_failures = 0

    for item in items:
        title = helpers.normalize_whitespace(item.findtext("title") or "") or "unknown"
        link = helpers.normalize_url_without_fragment(item.findtext("link") or source.url)
        description = helpers.strip_html_fragment(item.findtext("description") or "")
        published = helpers.normalize_whitespace(item.findtext("pubDate") or "")
        location = "unknown"
        alternate_url = ""
        note_parts = ["Verfassungsschutz RSS feed"]
        searchable_parts = [title, description, published, link]

        if published:
            note_parts.append(f"published={published}")

        direct_job_pages_opened += 1
        try:
            details = fetch_verfassungsschutz_job_details(link, timeout_seconds)
            if details["location"]:
                location = details["location"]
            if details["apply_url"]:
                alternate_url = details["apply_url"]
            searchable_parts.extend(
                part
                for part in (
                    details["description"],
                    details["deadline"],
                    details["career_track"],
                    details["working_time"],
                    details["location"],
                    details["tasks"],
                    details["offer"],
                    details["profile"],
                    details["apply_url"],
                )
                if part
            )
            if details["description"]:
                note_parts.append(f"Description: {helpers.truncate_text(details['description'], 180)}")
            if details["deadline"]:
                note_parts.append(f"Deadline: {details['deadline']}")
            if details["career_track"]:
                note_parts.append(f"Laufbahn: {details['career_track']}")
            if details["working_time"]:
                note_parts.append(f"Arbeitszeit: {details['working_time']}")
            if details["location"]:
                note_parts.append(f"Location: {details['location']}")
            if details["tasks"]:
                note_parts.append(f"Tasks: {helpers.truncate_text(details['tasks'], 260)}")
            if details["profile"]:
                note_parts.append(f"Profile: {helpers.truncate_text(details['profile'], 260)}")
        except Exception:
            detail_fetch_failures += 1

        searchable_text = " ".join(part for part in searchable_parts if part)
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not should_keep_service_bund_candidate(title, matched_terms, searchable_text):
            continue
        helpers.merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=title,
                url=link,
                source_url=source.url,
                alternate_url=alternate_url,
                location=location,
                matched_terms=matched_terms,
                notes="; ".join(note_parts),
            ),
        )

    limitations: list[str] = []
    status = "complete"
    if detail_fetch_failures:
        status = "partial"
        limitations.append(
            f"detail page enrichment failed for {detail_fetch_failures} of {len(items)} RSS items; affected roles fall back to feed metadata"
        )

    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status=status,
        listing_pages_scanned=1,
        search_terms_tried=terms,
        result_pages_scanned=f"rss_items={len(items)}",
        direct_job_pages_opened=direct_job_pages_opened,
        enumerated_jobs=len(items),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_auswaertiges_amt_json(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = http.fetch_text(source.url, timeout_seconds)
    match = AUSWAERTIGES_AMT_ACTION_RE.search(html)
    if not match:
        return Coverage(
            source=source.source,
            source_url=source.url,
            discovery_mode=source.discovery_mode,
            cadence_group=source.cadence_group,
            last_checked=source.last_checked,
            due_today=False,
            status="partial",
            listing_pages_scanned=1,
            search_terms_tried=terms,
            result_pages_scanned="json_feed=0",
            direct_job_pages_opened=0,
            enumerated_jobs=0,
            matched_jobs=0,
            limitations=["Ausw\u00e4rtiges Amt JSON job-list endpoint was not found in the page HTML."],
            candidates=[],
        )

    endpoint = helpers.normalize_url_without_fragment(urljoin(source.url, unescape(match.group("endpoint"))))
    payload = http.fetch_json(endpoint, timeout_seconds)
    items = payload.get("items") or []
    candidates_by_url: dict[str, Candidate] = {}

    for item in items:
        if not isinstance(item, dict):
            continue
        title = helpers.normalize_whitespace(helpers.join_text(item.get("headline"))) or "unknown"
        link = helpers.normalize_url_without_fragment(urljoin(source.url, helpers.join_text(item.get("link")) or source.url))
        description = helpers.strip_html_fragment(helpers.join_text(item.get("text")))
        location = "; ".join(
            helpers.normalize_whitespace(helpers.join_text(value)) for value in item.get("department") or [] if helpers.join_text(value)
        )
        published = helpers.normalize_whitespace(helpers.join_text(item.get("date")))
        closing = helpers.normalize_whitespace(helpers.join_text(item.get("closingDate")))
        searchable_text = " ".join(part for part in [title, location, description, published, closing, link] if part)
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not should_keep_service_bund_candidate(title, matched_terms, searchable_text):
            continue
        note_parts = ["Ausw\u00e4rtiges Amt JSON listings"]
        if published:
            note_parts.append(f"Published: {published}")
        if closing:
            note_parts.append(f"Deadline: {closing}")
        helpers.merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=title,
                url=link,
                source_url=source.url,
                location=location or "unknown",
                matched_terms=matched_terms,
                notes="; ".join(note_parts),
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
        result_pages_scanned=f"json_items={len(items)}",
        direct_job_pages_opened=0,
        enumerated_jobs=len(items),
        matched_jobs=len(candidates_by_url),
        limitations=[],
        candidates=list(candidates_by_url.values()),
    )


def build_bnd_search_url(source_url: str, term: str, page_num: int) -> str:
    parsed = urlparse(source_url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params["nn"] = params.get("nn") or "415896"
    params["queryResultId"] = "null"
    params["pageNo"] = str(max(page_num - 1, 0))
    params["templateQueryString"] = term
    return parsed._replace(query=urlencode(params), fragment="sprg415980").geturl()


def discover_bnd_career_search(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    candidates_by_url: dict[str, Candidate] = {}
    raw_urls: set[str] = set()
    listing_pages_scanned = 0
    result_summaries: list[str] = []
    limitations: list[str] = []
    errored_terms: list[str] = []
    parsed_source = urlparse(source.url)
    base_url = f"{parsed_source.scheme}://{parsed_source.netloc}/"

    for term in terms:
        try:
            html = http.fetch_text(build_bnd_search_url(source.url, term, 1), timeout_seconds)
        except Exception:
            errored_terms.append(term)
            continue
        listing_pages_scanned += 1
        term_seen = 0
        for match in BND_RESULT_RE.finditer(html):
            absolute_url = helpers.normalize_url_without_fragment(urljoin(base_url, unescape(match.group("href"))))
            raw_urls.add(absolute_url)
            title = helpers.strip_html_fragment(match.group("title")) or "unknown"
            bubbles = [
                helpers.strip_html_fragment(bubble_match.group("text"))
                for bubble_match in BND_BUBBLE_RE.finditer(match.group("bubbles"))
                if helpers.strip_html_fragment(bubble_match.group("text"))
            ]
            location = bubbles[0] if bubbles else "unknown"
            searchable_text = " ".join(part for part in [title, *bubbles] if part)
            matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
            if not should_keep_service_bund_candidate(title, matched_terms, searchable_text):
                continue
            term_seen += 1
            notes = f"BND native career search keyword='{term}'"
            if len(bubbles) > 1:
                notes = f"{notes}; tags={', '.join(bubbles[1:])}"
            helpers.merge_candidate(
                candidates_by_url,
                Candidate(
                    employer=source.source,
                    title=title,
                    url=absolute_url,
                    source_url=source.url,
                    location=location,
                    matched_terms=matched_terms,
                    notes=notes,
                ),
            )
        result_summaries.append(f"{term}:1p/{term_seen}")

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
        listing_pages_scanned=listing_pages_scanned,
        search_terms_tried=terms,
        result_pages_scanned=", ".join(result_summaries) if result_summaries else "none",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_urls),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_bosch_autocomplete(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    candidates_by_url: dict[str, Candidate] = {}
    raw_hit_urls: set[str] = set()
    truncated_terms: list[str] = []
    errored_terms: list[str] = []
    term_summaries: list[str] = []

    for term in terms:
        query = urlencode({"query": term, "locale": "de"})
        endpoint = f"{source.url.rstrip('/')}/api/filter/autocomplete?{query}"
        try:
            payload = http.fetch_json(endpoint, timeout_seconds)
        except Exception:
            errored_terms.append(term)
            term_summaries.append(f"{term}=error")
            continue

        hits = payload.get("hits", [])
        found = int(payload.get("found", 0) or 0)
        term_summaries.append(f"{term}={len(hits)}/{found}")
        if found > len(hits):
            truncated_terms.append(term)

        for hit in hits:
            document = hit.get("document", {})
            data = document.get("data", {})
            content = document.get("content", {})

            title = data.get("title") or "unknown"
            application_url = data.get("applicationUrl") or data.get("jobBoard_link") or source.url
            raw_hit_urls.add(application_url)
            location = ", ".join(part for part in [data.get("city"), data.get("country")] if part) or "unknown"
            remote = data.get("remote") or "unknown"

            searchable_text = " ".join(
                part
                for part in [
                    title,
                    data.get("company"),
                    location,
                    helpers.join_text(data.get("jobField")),
                    helpers.join_text(data.get("entryLevel")),
                    helpers.join_text(data.get("employmentType")),
                    helpers.join_text(content.get("task")),
                    helpers.join_text(content.get("profile")),
                    helpers.join_text(content.get("offer")),
                    helpers.join_text(content.get("business")),
                ]
                if part
            )
            matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
            if not helpers.should_keep_candidate(title, matched_terms, searchable_text):
                continue

            notes = f"Bosch autocomplete hit for '{term}'"
            candidate = Candidate(
                employer=data.get("company") or source.source,
                title=title,
                url=application_url,
                source_url=source.url,
                location=location,
                remote=remote,
                matched_terms=matched_terms,
                notes=notes,
            )
            if application_url not in candidates_by_url:
                candidates_by_url[application_url] = candidate
                continue
            helpers.merge_candidate(candidates_by_url, candidate)

    limitations: list[str] = []
    if truncated_terms:
        limitations.append("Autocomplete is capped at 10 hits per term; truncated terms: " + ", ".join(truncated_terms))
    if errored_terms:
        limitations.append("Errored terms: " + ", ".join(errored_terms))

    status = "partial" if errored_terms or truncated_terms else "complete"
    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status=status,
        listing_pages_scanned=1,
        search_terms_tried=terms,
        result_pages_scanned=", ".join(term_summaries) if term_summaries else "none",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_hit_urls),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCES = [
    SourceAdapter(modes=("verfassungsschutz_rss",), discover=discover_verfassungsschutz_rss),
    SourceAdapter(modes=("auswaertiges_amt_json",), discover=discover_auswaertiges_amt_json),
    SourceAdapter(modes=("bnd_career_search",), discover=discover_bnd_career_search),
    SourceAdapter(modes=("bosch_autocomplete",), discover=discover_bosch_autocomplete),
]
